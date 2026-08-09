# Agent Loop Detection and Monitoring

## Overview

Agent loops occur when agents get stuck in repetitive patterns - executing the same tool call repeatedly, failing in the same way, or generating monologues without progress. Crow implements a lightweight, multi-agent approach to detect and break these loops.

## Loop Patterns

### 1. Repeating Action-Observation Cycles

The agent executes the same action and gets the same results repeatedly (4+ times).

```
Action: ls
Observation: file1.py file2.py

Action: ls
Observation: file1.py file2.py

Action: ls
Observation: file1.py file2.py  ← Loop detected
```

### 2. Repeating Action-Error Cycles

The same action fails with the same error repeatedly (3+ times).

```
Action: import non_existent_module
Error: ModuleNotFoundError: No module named 'non_existent_module'

Action: import non_existent_module
Error: ModuleNotFoundError: No module named 'non_existent_module'  ← Loop detected
```

### 3. Agent Monologue

The agent sends multiple consecutive messages without user input or tool execution (3+ messages).

```
I should check the file structure.
Actually, let me think about the architecture.
Hmm, I should also consider the requirements.  ← Loop detected
```

### 4. Alternating Patterns

Two different action-observation pairs alternate in a ping-pong pattern (6+ cycles).

```
Action: cd /tmp
Observation: Working dir: /tmp

Action: cd /home
Observation: Working dir: /home

Action: cd /tmp
Observation: Working dir: /tmp

Action: cd /home
Observation: Working dir: /home  ← Alternating loop detected
```

### 5. Context Window Errors

Repeated attempts to process input that exceeds context limits.

## Multi-Agent Monitoring Architecture

### Primary Agent

The main agent doing the actual work (GLM-4.7, local models, etc.).

### Loop Detector Agent

A lightweight secondary agent with a short context window that monitors for stuck patterns.

```
┌─────────────────────────────────────┐
│         User Input                  │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│         Primary Agent               │
│  - Full context                     │
│  - Tool execution                   │
│  - Complex reasoning                │
└──────┬──────────────────────┬───────┘
       │                      │
       │ Every output          │
       │                      │
       ▼                      │
┌─────────────────────────────┐│
│      Loop Detector Agent    ││
│  - Lightweight model       ││
│  - Short context            ││
│  - Pattern recognition     ││
└──────┬──────────────────────┘│
       │                       │
       │ If loop detected      │
       │                       │
       ▼                       │
┌─────────────────────────────┐│
│   Recovery Handler          ││
│  - Alternative strategies    ││
│  - Meta-prompting           ││
│  - User notification        ││
└─────────────────────────────┘
```

## Implementation

### LoopDetector Class

```python
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List
import asyncio
from openai import AsyncOpenAI

class LoopType(Enum):
    REPEATING_ACTION = "repeating_action"
    REPEATING_ERROR = "repeating_error"
    MONOLOGUE = "monologue"
    ALTERNATING = "alternating"
    CONTEXT_ERROR = "context_error"

@dataclass
class LoopDetectionResult:
    """Result of loop detection analysis"""
    is_stuck: bool
    loop_type: Optional[LoopType] = None
    cycle_count: int = 0
    pattern_description: str = ""
    suggestion: str = ""
    confidence: float = 0.0  # 0.0 to 1.0

class LoopDetector:
    """
    Lightweight agent that monitors for stuck patterns.
    
    Uses a cheaper model with shorter context to detect loops
    without consuming too many resources.
    """
    
    def __init__(self, llm: AsyncOpenAI, detection_model: str = "gpt-4o-mini"):
        """
        Args:
            llm: OpenAI client
            detection_model: Model to use for detection (should be fast/cheap)
        """
        self.llm = llm
        self.detection_model = detection_model
    
    async def detect_loop(
        self,
        session_id: str,
        recent_events: List[dict],
        threshold_cycles: int = 3
    ) -> LoopDetectionResult:
        """
        Analyze recent events to detect loop patterns.
        
        Args:
            session_id: Session identifier
            recent_events: Last N events (actions, observations, messages)
            threshold_cycles: Minimum cycles to consider it a loop
            
        Returns:
            LoopDetectionResult with analysis
        """
        if len(recent_events) < 2 * threshold_cycles:
            return LoopDetectionResult(is_stuck=False)
        
        # Check each pattern type
        checks = [
            self._check_repeating_action(recent_events, threshold_cycles),
            self._check_repeating_error(recent_events, 3),
            self._check_monologue(recent_events, 3),
            self._check_alternating(recent_events, threshold_cycles + 3),
            self._check_context_errors(recent_events)
        ]
        
        # Run all checks in parallel
        results = await asyncio.gather(*checks, return_exceptions=True)
        
        # Find the most confident stuck result
        stuck_results = [r for r in results if isinstance(r, LoopDetectionResult) and r.is_stuck]
        
        if stuck_results:
            # Return the most confident stuck result
            return max(stuck_results, key=lambda r: r.confidence)
        
        return LoopDetectionResult(is_stuck=False)
    
    async def _check_repeating_action(
        self,
        events: List[dict],
        threshold: int
    ) -> LoopDetectionResult:
        """Check if same action produces same result repeatedly"""
        actions = [e for e in events if e['type'] == 'action']
        
        if len(actions) < threshold:
            return LoopDetectionResult(is_stuck=False)
        
        # Check last N actions for exact repetition
        last_n = actions[-threshold:]
        first_action = last_n[0]
        
        all_same = all(
            self._actions_equivalent(a, first_action)
            for a in last_n
        )
        
        if all_same:
            return LoopDetectionResult(
                is_stuck=True,
                loop_type=LoopType.REPEATING_ACTION,
                cycle_count=threshold,
                pattern_description=f"Executed action '{first_action.get('tool_name', 'unknown')}' {threshold} times with identical results",
                suggestion="Try a different approach or tool",
                confidence=0.9
            )
        
        return LoopDetectionResult(is_stuck=False)
    
    async def _check_repeating_error(
        self,
        events: List[dict],
        threshold: int
    ) -> LoopDetectionResult:
        """Check if same error occurs repeatedly"""
        errors = [e for e in events if e['type'] == 'error']
        
        if len(errors) < threshold:
            return LoopDetectionResult(is_stuck=False)
        
        last_n = errors[-threshold:]
        first_error = last_n[0]
        
        all_same = all(
            e['error_message'] == first_error['error_message']
            for e in last_n
        )
        
        if all_same:
            return LoopDetectionResult(
                is_stuck=True,
                loop_type=LoopType.REPEATING_ERROR,
                cycle_count=threshold,
                pattern_description=f"Error '{first_error['error_message']}' occurred {threshold} times",
                suggestion=f"Fix the error causing: {first_error['error_message'][:100]}...",
                confidence=0.95
            )
        
        return LoopDetectionResult(is_stuck=False)
    
    async def _check_monologue(
        self,
        events: List[dict],
        threshold: int
    ) -> LoopDetectionResult:
        """Check for consecutive messages without user input or tool calls"""
        messages = [e for e in events if e['type'] == 'message' and e['role'] == 'assistant']
        
        if len(messages) < threshold:
            return LoopDetectionResult(is_stuck=False)
        
        # Check if there are tool calls or user input between
        last_n = messages[-threshold:]
        messages_with_tools = sum(1 for m in last_n if m.get('tool_calls'))
        messages_between_user = any(
            e['type'] == 'message' and e['role'] == 'user'
            for e in events
            if events.index(e) >= events.index(last_n[0])
        )
        
        if not messages_between_user and messages_with_tools == 0:
            return LoopDetectionResult(
                is_stuck=True,
                loop_type=LoopType.MONOLOGUE,
                cycle_count=threshold,
                pattern_description=f"Agent sent {threshold} consecutive messages without action",
                suggestion="Either execute a tool or ask the user for clarification",
                confidence=0.85
            )
        
        return LoopDetectionResult(is_stuck=False)
    
    async def _check_alternating(
        self,
        events: List[dict],
        threshold: int
    ) -> LoopDetectionResult:
        """Check for alternating pattern between two actions"""
        if len(events) < threshold * 2:
            return LoopDetectionResult(is_stuck=False)
        
        # Look for pattern A, B, A, B, A, B...
        actions = [e for e in events if e['type'] == 'action']
        
        if len(actions) < threshold * 2:
            return LoopDetectionResult(is_stuck=False)
        
        # Check for ABAB pattern
        if self._is_alternating_pattern(actions[:threshold * 2]):
            action_a = actions[0]
            action_b = actions[1]
            
            return LoopDetectionResult(
                is_stuck=True,
                loop_type=LoopType.ALTERNATING,
                cycle_count=threshold,
                pattern_description=f"Alternating between '{action_a.get('tool_name')}' and '{action_b.get('tool_name')}'",
                suggestion="Break the cycle by trying a different strategy",
                confidence=0.8
            )
        
        return LoopDetectionResult(is_stuck=False)
    
    def _is_alternating_pattern(self, actions: List[dict]) -> bool:
        """Check if actions alternate between two patterns"""
        if len(actions) < 4:
            return False
        
        pattern = [self._actions_equivalent(actions[i], actions[i % 2]) for i in range(len(actions))]
        
        # Should be True, True, True, True...
        # Meaning action 0 == action 2 == action 4...
        # And action 1 == action 3 == action 5...
        return all(pattern)
    
    async def _check_context_errors(
        self,
        events: List[dict]
    ) -> LoopDetectionResult:
        """Check for repeated context window errors"""
        context_errors = [
            e for e in events
            if e.get('error_type') == 'context_length_exceeded'
            or 'context' in e.get('error_message', '').lower()
        ]
        
        if len(context_errors) >= 2:
            return LoopDetectionResult(
                is_stuck=True,
                loop_type=LoopType.CONTEXT_ERROR,
                cycle_count=len(context_errors),
                pattern_description=f"Context window exceeded {len(context_errors)} times",
                suggestion="Use conversation compaction to reduce context size",
                confidence=0.95  # Very confident this is a real problem
            )
        
        return LoopDetectionResult(is_stuck=False)
    
    def _actions_equivalent(self, a1: dict, a2: dict) -> bool:
        """
        Compare two actions for semantic equivalence.
        
        Ignores IDs, timestamps, and minor formatting differences.
        Compares tool name, tool arguments, and thought content.
        """
        # Same tool?
        if a1.get('tool_name') != a2.get('tool_name'):
            return False
        
        # Same arguments (normalized)?
        args1 = a1.get('tool_args', {})
        args2 = a2.get('tool_args', {})
        
        # Simple normalization: sort keys and compare JSON
        import json
        try:
            normalized1 = json.dumps(args1, sort_keys=True)
            normalized2 = json.dumps(args2, sort_keys=True)
            return normalized1 == normalized2
        except:
            return False
```

### AI-Augmented Detection

For more sophisticated detection, use the lightweight agent:

```python
async def detect_with_ai(
    self,
    events: List[dict]
) -> LoopDetectionResult:
    """Use AI to analyze events for stuck patterns"""
    
    # Format events for the AI
    event_strings = []
    for e in events[-20:]:  # Last 20 events
        if e['type'] == 'action':
            event_strings.append(f"Action: {e.get('tool_name')}({e.get('tool_args', {})})")
        elif e['type'] == 'observation':
            event_strings.append(f"Observation: {e.get('content', '')[:100]}...")
        elif e['type'] == 'error':
            event_strings.append(f"Error: {e.get('error_message')}")
        elif e['type'] == 'message':
            event_strings.append(f"{e['role']}: {e['content'][:100]}...")
    
    event_text = "\n".join(event_strings)
    
    prompt = f"""Analyze the following event sequence and determine if the agent is stuck in a loop.

Events:
{event_text}

Identify:
1. Is there a loop? Yes/No
2. What type of loop (repeating action, repeating error, monologue, alternating)?
3. How many cycles have occurred?
4. Brief explanation of the pattern
5. Suggestion for breaking the loop

Format your response as JSON:
{{
    "is_stuck": true/false,
    "loop_type": "repeating_action|repeating_error|monologue|alternating|null",
    "cycle_count": number,
    "explanation": string,
    "suggestion": string,
    "confidence": 0.0-1.0
}}"""
    
    response = await self.llm.chat.completions.create(
        model=self.detection_model,
        messages=[
            {"role": "system", "content": "You analyze agent behavior for stuck patterns."},
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )
    
    # Parse JSON response
    import json
    try:
        result = json.loads(response.choices[0].message.content)
        
        if result.get('is_stuck', False):
            return LoopDetectionResult(
                is_stuck=True,
                loop_type=LoopType(result.get('loop_type')) if result.get('loop_type') else None,
                cycle_count=result.get('cycle_count', 0),
                pattern_description=result.get('explanation', ''),
                suggestion=result.get('suggestion', ''),
                confidence=result.get('confidence', 0.7)
            )
    except:
        pass
    
    return LoopDetectionResult(is_stuck=False)
```

### Recovery Strategies

```python
class LoopRecovery:
    """Strategies to break agent loops"""
    
    def __init__(self, llm: AsyncOpenAI):
        self.llm = llm
    
    async def recover_from_loop(
        self,
        loop_result: LoopDetectionResult,
        session_id: str,
        original_task: str
    ) -> str:
        """Generate recovery guidance for the agent"""
        
        if not loop_result.is_stuck:
            return ""
        
        recovery_prompts = {
            LoopType.REPEATING_ACTION: f"""You have been attempting the same action repeatedly with identical results.

Original task: {original_task}

You have executed '{loop_result.pattern_description}' {loop_result.cycle_count} times.

Please:
1. Stop this action
2. Reflect on why this approach isn't working
3. Try a completely different strategy
4. If stuck, ask the user for guidance

DO NOT repeat this action again.""",
            
            LoopType.REPEATING_ERROR: f"""The same error is occurring repeatedly.

Error: {loop_result.pattern_description}

The operation has failed {loop_result.cycle_count} times.

Please:
1. Analyze the error message carefully
2. Identify what is causing it
3. Fix the underlying issue
4. If you cannot fix it, explain to the user what needs to be done

DO NOT retry the same failing operation.""",
            
            LoopType.MONOLOGUE: f"""You have sent {loop_result.cycle_count} consecutive messages without taking action.

Original task: {original_task}

Please:
1. Either execute a tool to make progress
2. Or ask the user a specific question
3. Do not continue sending messages without action

You need to DO something, not just TALK.""",
            
            LoopType.ALTERNATING: f"""You are stuck alternating between two actions.

{loop_result.pattern_description}

Alternating {loop_result.cycle_count} times without progress.

Please:
1. Break the cycle
2. Try a different approach
3. Consider neither of these two actions

The current pattern is unproductive.""",
            
            LoopType.CONTEXT_ERROR: f"""The conversation has grown too large.

{loop_result.pattern_description}

The system will now compress the conversation history. Please continue your work after the compression."""
        }
        
        recovery_message = recovery_prompts.get(
            loop_result.loop_type,
            f"Detected stuck pattern: {loop_result.pattern_description}\n\n{loop_result.suggestion}"
        )
        
        # For context errors, actually trigger compaction
        if loop_result.loop_type == LoopType.CONTEXT_ERROR:
            # This would call the compactor
            pass
        
        return recovery_message
```

## Integration with ReAct Loop

```python
class CrowAgent:
    """Agent with loop detection"""
    
    def __init__(self, llm, mcp_client):
        self.llm = llm
        self.mcp_client = mcp_client
        
        # Lightweight model for loop detection
        self.detector_llm = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL")
        )
        
        self.loop_detector = LoopDetector(self.detector_llm)
        self.recovery = LoopRecovery(self.llm)
        
        # Track events for detection
        self.event_history: dict[str, List[dict]] = {}
    
    async def process_turn_with_monitoring(
        self,
        session_id: str,
        user_message: str
    ):
        """Process with automatic loop detection"""
        
        # Initialize event history if needed
        if session_id not in self.event_history:
            self.event_history[session_id] = []
        
        # Add user message to history
        self.event_history[session_id].append({
            'type': 'message',
            'role': 'user',
            'content': user_message,
            'timestamp': asyncio.get_event_loop().time()
        })
        
        # Process the turn normally
        messages = await self.persistence.get_openai_messages(session_id)
        
        # Track events during generation
        async def track_events():
            async for event in self._process_turn_internal(messages):
                # Record event
                if event.get('type') in ['action', 'observation', 'error']:
                    self.event_history[session_id].append(event)
                
                # Check for loops every 3 events
                if len(self.event_history[session_id]) % 3 == 0:
                    loop_result = await self.loop_detector.detect_loop(
                        session_id,
                        self.event_history[session_id][-20:]
                    )
                    
                    if loop_result.is_stuck:
                        # Generate recovery message
                        recovery = await self.recovery.recover_from_loop(
                            loop_result,
                            session_id,
                            user_message
                        )
                        
                        # Inject recovery as a system message
                        await self.persistence.add_message(
                            session_id,
                            role='system',
                            content=f"[LOOP DETECTED]\n{recovery}"
                        )
                        
                        print(f"\n[Loop detected: {loop_result.loop_type.value}]")
                        print(f"[Recovery: {loop_result.suggestion}]")
                        
                        # For certain loop types, force a user interaction
                        if loop_result.loop_type in [
                            LoopType.REPEATING_ERROR,
                            LoopType.CONTEXT_ERROR
                        ]:
                            print("\n[Pausing due to loop. Please provide guidance or press Enter to continue.]")
                            input()  # Wait for user
                
                yield event
        
        async for result in track_events():
            yield result
```

## Performance Considerations

1. **Detection frequency**: Check every N events (3-5) to balance detection speed vs. overhead
2. **Event history limit**: Only keep last 20-50 events for detection
3. **Model choice**: Use cheap/fast model (GPT-4o-mini) for detection
4. **Early exit**: If not stuck after 2 checks, increase interval

## Testing

```python
import pytest

async def test_repeating_action_detection():
    """Test detection of repeating action loop"""
    detector = LoopDetector(mock_llm)
    
    # Create event sequence with repeating ls
    events = [
        {'type': 'action', 'tool_name': 'shell', 'tool_args': {'command': 'ls'}},
        {'type': 'observation', 'content': 'file1 file2'},
        {'type': 'action', 'tool_name': 'shell', 'tool_args': {'command': 'ls'}},
        {'type': 'observation', 'content': 'file1 file2'},
        {'type': 'action', 'tool_name': 'shell', 'tool_args': {'command': 'ls'}},
        {'type': 'observation', 'content': 'file1 file2'},
        {'type': 'action', 'tool_name': 'shell', 'tool_args': {'command': 'ls'}},
        {'type': 'observation', 'content': 'file1 file2'},
    ]
    
    result = await detector.detect_loop(session_id, events)
    
    assert result.is_stuck
    assert result.loop_type == LoopType.REPEATING_ACTION
    assert result.cycle_count == 4
```

## References

- OpenHands StuckDetector: https://docs.openhands.dev/sdk/guides/agent-stuck-detector
- Multi-agent coordination patterns
