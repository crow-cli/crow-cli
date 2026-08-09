# Session Persistence and Compaction

## Overview

Crow maintains persistent state in SQLite to enable session resumption, conversation history reconstruction, and efficient context management through compaction.

## SQLite Schema

### Core Tables

```sql
-- Sessions are the top-level container
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    title TEXT,  -- Auto-generated or user-provided
    workspace_path TEXT,  -- Working directory for this session
    metadata JSON  -- Extra structured data
);

-- Messages within a session
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,  -- 'user', 'assistant', 'tool', 'system'
    content TEXT NOT NULL,
    tool_call_id TEXT,  -- For tool response messages
    tool_name TEXT,  -- Associated tool call
    tool_args JSON,  -- Tool arguments (for tool calls)
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- Tool execution results (detailed tracking)
CREATE TABLE tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    message_id INTEGER NOT NULL,  -- The assistant message that made the call
    tool_name TEXT NOT NULL,
    tool_args JSON,
    result TEXT,
    success BOOLEAN,
    duration_ms INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
);

-- Skills loaded during session
CREATE TABLE session_skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    skill_content TEXT NOT NULL,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- Compaction events (for debugging and rollback)
CREATE TABLE compaction_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    before_message_count INTEGER NOT NULL,
    after_message_count INTEGER NOT NULL,
    summary TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX idx_messages_session_time ON messages(session_id, timestamp);
CREATE INDEX idx_tool_calls_session ON tool_calls(session_id);
CREATE INDEX idx_compaction_session ON compaction_history(session_id);
```

## Persistence Layer

```python
import sqlite3
import json
from datetime import datetime
from typing import Optional, List
import aiosqlite  # For async operations

class SessionPersistence:
    """Manages SQLite persistence for Crow sessions"""
    
    def __init__(self, db_path: str = "crow_sessions.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA)
    
    async def create_session(
        self, 
        workspace_path: str,
        title: Optional[str] = None
    ) -> str:
        """Create a new session"""
        async with aiosqlite.connect(self.db_path) as db:
            session_id = f"sess_{datetime.now().timestamp()}"
            await db.execute(
                "INSERT INTO sessions (id, workspace_path, title) VALUES (?, ?, ?)",
                (session_id, workspace_path, title)
            )
            await db.commit()
            return session_id
    
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_call_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        tool_args: Optional[dict] = None
    ) -> int:
        """Add a message to the session"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """INSERT INTO messages 
                   (session_id, role, content, tool_call_id, tool_name, tool_args)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, role, content, tool_call_id, tool_name, 
                 json.dumps(tool_args) if tool_args else None)
            )
            await db.commit()
            return cursor.lastrowid
    
    async def record_tool_call(
        self,
        session_id: str,
        message_id: int,
        tool_name: str,
        tool_args: dict,
        result: str,
        success: bool,
        duration_ms: int
    ):
        """Record a tool execution"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO tool_calls 
                   (session_id, message_id, tool_name, tool_args, result, success, duration_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, message_id, tool_name, json.dumps(tool_args),
                 result, success, duration_ms)
            )
            await db.commit()
    
    async def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[dict]:
        """Retrieve messages for a session"""
        async with aiosqlite.connect(self.db_path) as db:
            query = "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp"
            params = [session_id]
            
            if limit:
                query += " DESC LIMIT ?"
                params.append(limit)
            
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            
            return [
                {
                    'id': row['id'],
                    'role': row['role'],
                    'content': row['content'],
                    'tool_call_id': row.get('tool_call_id'),
                    'tool_name': row.get('tool_name'),
                    'tool_args': json.loads(row['tool_args']) if row.get('tool_args') else None,
                    'timestamp': row['timestamp']
                }
                for row in reversed(rows)
            ]
    
    async def get_openai_messages(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[dict]:
        """Get messages formatted for OpenAI API"""
        messages = await self.get_messages(session_id, limit)
        
        # Convert to OpenAI format
        openai_msgs = []
        for msg in messages:
            oai_msg = {'role': msg['role'], 'content': msg['content']}
            
            # Add tool calls for assistant messages
            if msg['role'] == 'assistant' and msg['tool_name']:
                oai_msg['tool_calls'] = [{
                    'id': msg['tool_call_id'] or f"call_{msg['id']}",
                    'type': 'function',
                    'function': {
                        'name': msg['tool_name'],
                        'arguments': json.dumps(msg['tool_args'])
                    }
                }]
            
            openai_msgs.append(oai_msg)
        
        return openai_msgs
    
    async def list_sessions(self) -> List[dict]:
        """List all sessions with metadata"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT id, title, created_at, updated_at, workspace_path,
                          (SELECT COUNT(*) FROM messages WHERE session_id = sessions.id) as message_count
                   FROM sessions
                   ORDER BY updated_at DESC"""
            )
            rows = await cursor.fetchall()
            
            return [
                {
                    'id': row['id'],
                    'title': row['title'],
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at'],
                    'workspace_path': row['workspace_path'],
                    'message_count': row['message_count']
                }
                for row in rows
            ]
    
    async def update_session_timestamp(self, session_id: str):
        """Update the last activity timestamp"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (session_id,)
            )
            await db.commit()
```

## Conversation Compaction

### When to Compact

Compaction occurs when:
- Conversation reaches a token threshold (e.g., 50k tokens)
- Session finishes naturally (via `finish` tool)
- User explicitly requests compaction

### Compaction Strategy

```python
class ConversationCompactor:
    """Compresses conversation history while preserving context"""
    
    def __init__(self, persistence: SessionPersistence, llm: OpenAI):
        self.persistence = persistence
        self.llm = llm
    
    async def should_compact(
        self,
        session_id: str,
        token_limit: int = 50000,
        keep_last_n: int = 10
    ) -> bool:
        """Check if conversation needs compaction"""
        messages = await self.persistence.get_messages(session_id)
        
        # Simple heuristic: count estimated tokens
        # 1 token ≈ 4 characters for English text
        total_chars = sum(len(msg['content']) for msg in messages)
        estimated_tokens = total_chars // 4
        
        return estimated_tokens > token_limit
    
    async def compact(
        self,
        session_id: str,
        keep_last_n: int = 10,
        model: str = "gpt-4o-mini"  # Use cheaper model for compaction
    ) -> str:
        """
        Compact conversation by summarizing older messages.
        
        Returns:
            Summary text that replaces older messages
        """
        # Get all messages
        all_messages = await self.persistence.get_messages(session_id)
        
        if len(all_messages) <= keep_last_n * 2:
            return ""  # Nothing to compact
        
        # Split into "to summarize" and "to keep"
        to_summarize = all_messages[:-keep_last_n]
        to_keep = all_messages[-keep_last_n:]
        
        # Create summary prompt
        summary_prompt = self._create_summary_prompt(to_summarize)
        
        # Get summary from LLM
        summary = await self._generate_summary(summary_prompt, model)
        
        # Record compaction event
        await self._record_compaction(
            session_id,
            len(to_summarize),
            len(to_keep) + 1,  # +1 for the summary message
            summary
        )
        
        # Replace old messages with summary
        # First, delete old messages (except system messages)
        await self._delete_messages_before(session_id, to_keep[0]['id'])
        
        # Insert summary as system message
        await self.persistence.add_message(
            session_id,
            role='system',
            content=f"[SUMMARY OF PREVIOUS CONVERSATION]\n{summary}\n"
                    f"This summary replaces {len(to_summarize)} previous messages."
        )
        
        return summary
    
    def _create_summary_prompt(self, messages: List[dict]) -> str:
        """Create a prompt for summarizing conversation"""
        # Format messages for the LLM
        formatted = "\n\n".join([
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in messages
        ])
        
        return f"""Summarize the following conversation history concisely (200-300 words).
Focus on:
1. What the user asked for
2. What was accomplished
3. Key decisions made
4. Current state of work
5. Any important context for future turns

Do NOT include complete code snippets or tool outputs. Just capture the essence.

{formatted}

Provide a clear, well-structured summary."""
    
    async def _generate_summary(self, prompt: str, model: str) -> str:
        """Generate summary using LLM"""
        response = await self.llm.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes conversations."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    
    async def _record_compaction(
        self,
        session_id: str,
        before_count: int,
        after_count: int,
        summary: str
    ):
        """Record compaction event for debugging"""
        async with aiosqlite.connect(self.persistence.db_path) as db:
            await db.execute(
                """INSERT INTO compaction_history 
                   (session_id, before_message_count, after_message_count, summary)
                   VALUES (?, ?, ?, ?)""",
                (session_id, before_count, after_count, summary[:500])  # Truncate for DB
            )
            await db.commit()
    
    async def _delete_messages_before(self, session_id: str, keep_from_id: int):
        """Delete messages before a certain ID (except system messages)"""
        async with aiosqlite.connect(self.persistence.db_path) as db:
            await db.execute(
                """DELETE FROM messages 
                   WHERE session_id = ? AND id < ? AND role != 'system'""",
                (session_id, keep_from_id)
            )
            await db.commit()
```

## Integration with ReAct Loop

```python
class CrowAgent:
    """Main agent with persistence and compaction"""
    
    def __init__(self, llm: OpenAI, mcp_client: Client):
        self.llm = llm
        self.mcp_client = mcp_client
        self.persistence = SessionPersistence()
        self.compactor = ConversationCompactor(self.persistence, llm)
    
    async def process_turn(self, session_id: str, user_message: str):
        """Process a user turn with automatic compaction"""
        # Add user message
        await self.persistence.add_message(session_id, 'user', user_message)
        
        # Check compaction
        if await self.compactor.should_compact(session_id):
            print("\n[Compacting conversation history...]")
            await self.compactor.compact(session_id)
        
        # Get messages for LLM
        messages = await self.persistence.get_openai_messages(session_id)
        
        # Process turn (parallel tool execution, streaming, etc.)
        updated_messages = await process_turn(messages, self.mcp_client)
        
        # Save assistant message and tool responses
        for msg in updated_messages[len(messages):]:
            await self._save_message(session_id, msg)
        
        # Update session timestamp
        await self.persistence.update_session_timestamp(session_id)
    
    async def _save_message(self, session_id: str, msg: dict):
        """Save a message from LLM to persistence"""
        tool_call_id = None
        tool_name = None
        tool_args = None
        
        if msg.get('tool_calls'):
            for tc in msg['tool_calls']:
                tool_call_id = tc['id']
                tool_name = tc['function']['name']
                tool_args = json.loads(tc['function']['arguments'])
        
        await self.persistence.add_message(
            session_id,
            msg['role'],
            msg['content'] or "",
            tool_call_id,
            tool_name,
            tool_args
        )
```

## Session Resumption

```python
async def resume_session(session_id: str):
    """Resume an existing session"""
    # Get all messages (they're already in OpenAI format)
    messages = await persistence.get_openai_messages(session_id)
    
    # Continue processing as normal
    while True:
        user_input = await get_user_input()
        await agent.process_turn(session_id, user_input)
```

## Open Questions

- Should we use a vector store (Qdrant) for semantic search over past sessions?
- How do we handle skill loading/unloading during compaction?
- Should we store the KV cache state for faster resumption with local models?
