# The Finish Tool

## Overview

The `finish` tool is the only built-in, non-MCP tool in Crow. It handles session completion, learning capture, state updates, and clean shutdown. Unlike framework-specific finish implementations, ours is:

- **MCP-compatible** (can be exposed as an MCP tool)
- **Comprehensive** (captures everything learned, not just done/not-done)
- **Replayable** (can be re-invoked if interrupted)
- **Structured** (well-defined subagent workflow)

## Finish Tool Responsibilities

```python
from typing import Optional
from pydantic import BaseModel

class FinishRequest(BaseModel):
    """Request to finish a task"""
    session_id: str
    success: bool
    summary: str  # What was accomplished
    learned: Optional[list[str]] = None  # What was learned
    skills_used: Optional[list[str]] = None  # Skills that were useful
    new_skills_needed: Optional[list[str]] = None  # Skills we wish we had
    files_modified: Optional[list[str]] = None  # Files that were changed
    next_steps: Optional[str] = None  # What to do next

class FinishResponse(BaseModel):
    """Response from finish tool"""
    session_id: str
    status: "completed" | "cancelled" | "failed"
    summary_updated: bool
    skills_updated: bool
    history_saved: bool
    next_actions: list[str]
```

## Finish Tool Logic

The finish tool triggers a subagent workflow:

```
User calls finish()
    │
    ▼
┌─────────────────────────────────────┐
│  1. Session Summary Generation     │ ← lightweight model, structured extraction
│  - What was the original task?      │
│  - What was actually done?          │
│  - What files were changed?         │
│  - What remains incomplete?         │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  2. Learning Extraction            │ ← analyze conversation for insights
│  - New patterns/techniques learned │
│  - Tool combinations that worked   │
│  - Approaches that failed           │
│  - Domain knowledge gained          │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  3. Skill Assessment               │ ← which skills were useful?
│  - Skills that were invoked        │
│  - Skills that should have been     │
│  - New skills to create            │
│  - Skills to update                │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  4. Persistent State Updates      │ ← SQLite & Qdrant
│  - Session record in SQLite        │
│  - Learning vectors in Qdrant      │
│  - Skill database updates          │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  5. Cleanup and Session Close     │
│  - Close MCP connections           │
│  - Release resources               │
│  - Update session status           │
└─────────────────────────────────────┘
```

## Implementation

```python
from typing import Optional, List
from dataclasses import dataclass
from openai import AsyncOpenAI
import aiosqlite

@dataclass
class FinishContext:
    """Context for finish subagent"""
    session_id: str
    conversation_history: list[dict]
    task_description: str
    execution_metrics: dict  # time, tokens, tool calls, etc.

class FinishSubagent:
    """
    Subagent that handles the finish workflow.
    
    This is "subagent" in the sense that it's a structured workflow
    orchestrated by code, but can invoke an LLM for certain steps.
    It's NOT a general-purpose agent - it has a specific task.
    """
    
    def __init__(
        self,
        llm: AsyncOpenAI,
        persistence: SessionPersistence,
        skill_manager: SkillManager,
        vector_store: 'VectorStore'  # Qdrant
    ):
        self.llm = llm
        self.persistence = persistence
        self.skill_manager = skill_manager
        self.vector_store = vector_store
    
    async def execute(
        self,
        ctx: FinishContext,
        request: FinishRequest
    ) -> FinishResponse:
        """Execute the full finish workflow"""
        
        # Step 1: Generate comprehensive summary
        summary = await self._generate_summary(ctx, request)
        
        # Step 2: Extract learnings
        learnings = await self._extract_learnings(ctx)
        
        # Step 3: Assess skills
        skill_assessment = await self._assess_skills(ctx, request)
        
        # Step 4: Update persistent state
        await self._update_persistent_state(
            ctx,
            summary,
            learnings,
            skill_assessment,
            request
        )
        
        # Step 5: Cleanup
        await self._cleanup_session(ctx)
        
        # Return response
        return FinishResponse(
            session_id=ctx.session_id,
            status="completed" if request.success else ("failed" if request.success is False else "cancelled"),
            summary_updated=True,
            skills_updated=skill_assessment['updated'],
            history_saved=True,
            next_actions=self._generate_next_actions(ctx, summary)
        )
    
    async def _generate_summary(
        self,
        ctx: FinishContext,
        request: FinishRequest
    ) -> dict:
        """Generate comprehensive session summary"""
        
        # Build context for summarizer
        context = {
            'task': ctx.task_description,
            'request_summary': request.summary,
            'conversation': self._format_conversation(ctx.conversation_history[-50:]),  # Last 50 msgs
            'metrics': ctx.execution_metrics
        }
        
        prompt = f"""Generate a structured summary for a completed coding session.

Task: {context['task']}
User's summary: {context['request_summary']}
Metrics: {context['metrics']}

Recent conversation:
{context['conversation']}

Provide a structured summary as JSON:
{{
    "task": "What was being attempted",
    "outcome": "What was accomplished (success, partial, failure)",
    "key_steps": ["Step 1", "Step 2", ...],
    "approaches_tried": ["Approach A", "Approach B", ...],
    "lessons_learned": ["Lesson 1", "Lesson 2", ...],
    "challenges": ["Challenge 1", ...],
    "files_changed": ["file1.py", "file2.py", ...],
    "incomplete_items": ["Still need to do X", ...],
    "suggested_followup": "Brief suggestion for next time"
}}"""
        
        response = await self.llm.chat.completions.create(
            model="gpt-4o-mini",  # Use cheaper model for summarization
            messages=[
                {"role": "system", "content": "You are a documentation assistant that creates structured summaries."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        
        import json
        try:
            summary = json.loads(response.choices[0].message.content)
        except:
            # Fallback if JSON parsing fails
            summary = {
                'task': ctx.task_description,
                'outcome': request.summary,
                'key_steps': [],
                'approaches_tried': [],
                'lessons_learned': [],
                'challenges': [],
                'files_changed': request.files_modified or [],
                'incomplete_items': [],
                'suggested_followup': ''
            }
        
        return summary
    
    async def _extract_learnings(self, ctx: FinishContext) -> list[dict]:
        """Extract learnings from conversation"""
        
        # Use vector similarity to find notable moments
        notable_moments = await self._find_notable_moments(ctx)
        
        # Extract learnings from these moments
        learnings = []
        
        for moment in notable_moments:
            learning = await self._analyze_moment(moment)
            if learning:
                learnings.append(learning)
        
        return learnings
    
    async def _find_notable_moments(
        self,
        ctx: FinishContext
    ) -> list[dict]:
        """Find notable moments using vector search"""
        
        # This would use Qdrant to find moments that:
        # - Represent breakthroughs
        # - Show successful approaches
        # - Document failures
        
        # For now, simple heuristic: look for tool call sequences
        # that led to user confirmation or progress
        
        moments = []
        for i, msg in enumerate(ctx.conversation_history):
            if msg.get('role') == 'assistant':
                # Check if followed by user confirmation
                if i + 1 < len(ctx.conversation_history):
                    next_msg = ctx.conversation_history[i + 1]
                    if (next_msg.get('role') == 'user' and 
                        any(word in next_msg.get('content', '').lower() 
                            for word in ['good', 'yes', 'correct', 'great', 'thanks', 'looks'])):
                        moments.append(msg)
        
        return moments[:10]  # Top 10 moments
    
    async def _analyze_moment(self, moment: dict) -> Optional[dict]:
        """Analyze a notable moment to extract learning"""
        
        if not moment.get('content'):
            return None
        
        prompt = f"""Analyze this interaction and extract what was learned:

Interaction: {moment['content']}

Extract as JSON:
{{
    "learning": "What was learned",
    "tool_or_technique": "Tool or technique used",
    "applicability": "How generally applicable this is",
    "tags": ["tag1", "tag2"]
}}"""
        
        response = await self.llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You extract learnings from interactions."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        
        import json
        try:
            return json.loads(response.choices[0].message.content)
        except:
            return None
    
    async def _assess_skills(
        self,
        ctx: FinishContext,
        request: FinishRequest
    ) -> dict:
        """Assess which skills were useful and which are needed"""
        
        # This would query the skill database for:
        # - Skills that were invoked
        # - Skills that should have been invoked
        # - Skills that don't exist but would be useful
        
        invoked_skills = request.skills_used or []
        
        # Use LLM to suggest skills
        prompt = f"""Based on this coding session, what skills were useful 
or would have been useful?

Task: {ctx.task_description}
Skills used: {', '.join(invoked_skills)}
Summary: {request.summary}

Provide JSON:
{{
    "useful_skills": [{"name": "skill_name", "why": "description"}],
    "missing_skills": [{"name": "potential_skill_name", "why": "would help with X"}],
    "skills_to_create": [{"name": "new_skill_name", "description": "what it should do"}],
    "updated": true/false
}}"""
        
        response = await self.llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You analyze codebases for skill requirements."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4
        )
        
        import json
        try:
            assessment = json.loads(response.choices[0].message.content)
        except:
            assessment = {
                'useful_skills': [],
                'missing_skills': [],
                'skills_to_create': [],
                'updated': False
            }
        
        # Trigger skill updates if needed
        if assessment['skills_to_create']:
            for skill in assessment['skills_to_create']:
                await self.skill_manager.register_skill_placeholder(
                    session_id=ctx.session_id,
                    skill_name=skill['name'],
                    description=skill['description'],
                    from_session=True
                )
        
        return assessment
    
    async def _update_persistent_state(
        self,
        ctx: FinishContext,
        summary: dict,
        learnings: list[dict],
        skill_assessment: dict,
        request: FinishRequest
    ):
        """Update SQLite and Qdrant with all the data"""
        
        async with aiosqlite.connect(self.persistence.db_path) as db:
            # Update session with summary and metadata
            await db.execute(
                """UPDATE sessions 
                   SET title = coalesce(?, title),
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (summary.get('task', ''), ctx.session_id)
            )
            
            # Store summary
            await db.execute(
                """INSERT INTO session_summaries 
                   (session_id, summary_json, created_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)""",
                (ctx.session_id, json.dumps(summary))
            )
            
            # Store learnings
            for learning in learnings:
                await db.execute(
                    """INSERT INTO session_learnings 
                       (session_id, learning, tool_or_technique, applicability, tags)
                       VALUES (?, ?, ?, ?, ?)""",
                    (ctx.session_id, 
                     learning.get('learning', ''),
                     learning.get('tool_or_technique', ''),
                     learning.get('applicability', ''),
                     json.dumps(learning.get('tags', [])))
                )
            
            await db.commit()
        
        # Update vector store for semantic search
        for learning in learnings:
            await self.vector_store.insert(
                collection="learnings",
                point={
                    'id': f"{ctx.session_id}_{learning.get('tool_or_technique', 'learning')}_{asyncio.get_event_loop().time()}",
                    'vector': await self._embed_text(learning.get('learning', '')),
                    'payload': {
                        'session_id': ctx.session_id,
                        'learning': learning.get('learning', ''),
                        'technique': learning.get('tool_or_technique', ''),
                        'tags': learning.get('tags', [])
                    }
                }
            )
    
    async def _cleanup_session(self, ctx: FinishContext):
        """Cleanup and close session resources"""
        
        # Mark session as completed
        async with aiosqlite.connect(self.persistence.db_path) as db:
            await db.execute(
                """UPDATE sessions 
                   SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (ctx.session_id,)
            )
            await db.commit()
        
        # Close any open MCP connections for this session
        # (This would be integrated with MCP client management)
        pass
    
    def _format_conversation(self, messages: list[dict]) -> str:
        """Format messages as text"""
        formatted = []
        for msg in messages:
            role = msg.get('role', 'unknown').upper()
            content = msg.get('content', '')[:500]  # Truncate
            formatted.append(f"{role}: {content}")
        return '\n'.join(formatted)
    
    def _generate_next_actions(
        self,
        ctx: FinishContext,
        summary: dict
    ) -> List[str]:
        """Generate suggested next actions for the user"""
        
        actions = []
        
        # From incomplete items
        for item in summary.get('incomplete_items', []):
            actions.append(f"Complete: {item}")
        
        # From suggested followup
        followup = summary.get('suggested_followup', '')
        if followup:
            actions.append(f"Followup: {followup}")
        
        # Always offer to resume
        actions.append("Resume this session later")
        
        # Offer to start new session in same workspace
        if ctx.execution_metrics.get('workspace_path'):
            actions.append(f"Start new session in {ctx.execution_metrics['workspace_path']}")
        
        return actions
    
    async def _embed_text(self, text: str) -> list[float]:
        """Generate embedding for vector store"""
        # This would call an embedding model
        # For now, return dummy vector
        return [0.0] * 768
```

## Table Schema Updates

```sql
-- Add tables for finish-related data

CREATE TABLE session_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE session_learnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    learning TEXT NOT NULL,
    tool_or_technique TEXT,
    applicability TEXT,
    tags TEXT,  -- JSON array
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE skill_placeholders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT DEFAULT 'placeholder',  -- placeholder, implemented, reviewed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- Update sessions table
ALTER TABLE sessions ADD COLUMN status TEXT DEFAULT 'active';
ALTER TABLE sessions ADD COLUMN completed_at TIMESTAMP;
```

## MCP Integration

The finish tool can be exposed as an MCP tool:

```python
# In the MCP server
@mcp_server.tool()
async def finish(
    session_id: str,
    success: bool,
    summary: str
) -> str:
    """Complete a session and capture learnings
    
    Args:
        session_id: Session to finish
        success: Whether the task was completed successfully
        summary: Summary of what was accomplished
    
    Returns:
        Confirmation with next actions
    """
    request = FinishRequest(
        session_id=session_id,
        success=success,
        summary=summary
    )
    
    # Execute finish subagent
    subagent = FinishSubagent(llm, persistence, skill_manager, vector_store)
    response = await subagent.execute(context_from_session(session_id), request)
    
    return json.dumps({
        "status": response.status,
        "next_actions": response.next_actions,
        "summary": summary
    })
```

## Replayability

The finish tool is designed to be replayable if interrupted:

```python
class ResumeableFinish:
    """Finish that can be resumed if interrupted"""
    
    def __init__(self):
        self.checkpoints: dict[str, dict] = {}
    
    async def execute_with_rollback(
        self,
        ctx: FinishContext,
        request: FinishRequest
    ) -> FinishResponse:
        """Execute with rollback capabilities"""
        
        checkpoints = []
        
        try:
            # Step 1: Generate summary
            summary = await self._generate_summary(ctx, request)
            checkpoints.append(('summary', summary))
            
            # Step 2: Extract learnings
            learnings = await self._extract_learnings(ctx)
            checkpoints.append(('learnings', learnings))
            
            # Step 3: Assess skills
            skill_assessment = await self._assess_skills(ctx, request)
            checkpoints.append(('skills', skill_assessment))
            
            # Step 4: Update persistent state
            await self._update_persistent_state(
                ctx, summary, learnings, skill_assessment, request
            )
            checkpoints.append(('persisted', True))
            
            # Step 5: Cleanup
            await self._cleanup_session(ctx)
            checkpoints.append(('cleanup', True))
            
            # Success
            self.checkpoints[ctx.session_id] = {'success': True, 'steps': [c[0] for c in checkpoints]}
            
            return FinishResponse(
                session_id=ctx.session_id,
                status="completed",
                summary_updated=True,
                skills_updated=True,
                history_saved=True,
                next_actions=self._generate_next_actions(ctx, summary)
            )
        
        except Exception as e:
            # On failure, record where we got to
            self.checkpoints[ctx.session_id] = {
                'success': False,
                'steps': [c[0] for c in checkpoints],
                'error': str(e)
            }
            
            # Can be resumed from last successful checkpoint
            raise
```

## Benefits of Finish Tool

1. **Learning capture**: Never lose insights from a session
2. **Skill discovery**: Automatically identify new skills to build
3. **Searchable history**: Vector store makes past lessons discoverable
4. **Clean shutdown**: Proper resource cleanup and session closure
5. **Reproducible**: Subagent workflow is predictable and testable

## Testing

```python
async def test_finish_workflow():
    """Test the finish tool workflow"""
    
    session_id = await persistence.create_session("/tmp/test")
    
    # Simulate some work
    await persistence.add_message(session_id, 'user', 'Fix the bug in file.py')
    await persistence.add_message(session_id, 'assistant', "I'll check the file...")
    
    # Call finish
    request = FinishRequest(
        session_id=session_id,
        success=True,
        summary='Fixed the bug by adjusting the loop condition',
        skills_used=['python_debugging', 'file_operations']
    )
    
    ctx = FinishContext(
        session_id=session_id,
        conversation_history=await persistence.get_messages(session_id),
        task_description='Fix bug in file.py',
        execution_metrics={}
    )
    
    subagent = FinishSubagent(llm, persistence, mock_skill_manager, mock_vector_store)
    response = await subagent.execute(ctx, request)
    
    assert response.session_id == session_id
    assert response.status == 'completed'
    
    # Verify summary was saved
    summary = await db.execute(
        "SELECT summary_json FROM session_summaries WHERE session_id = ?",
        (session_id,)
    )
    assert summary is not None
```

## References

- OpenHands finish patterns
- Session management best practices
- Learning capture systems
