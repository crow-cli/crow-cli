# Cancellation: A Solid Plan

## The Problem

User sends `{"sessionId": "abc123"}` to `session/cancel`. We need to break out of whatever the agent is doing and return `PromptResponse(stop_reason="cancelled")`.

## The Pattern (3 Parts)

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  new_session    │     │     prompt       │     │     cancel      │
│                 │     │                  │     │                 │
│  Create Event   │────►│  Wait on Event   │◄────│   Set Event     │
│                 │     │  with timeout    │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

### Part 1: Store Events

```python
class Agent:
    _cancel_events: dict[str, asyncio.Event] = {}
    
    async def new_session(self, ...) -> NewSessionResponse:
        session_id = uuid4().hex
        self._cancel_events[session_id] = asyncio.Event()
        return NewSessionResponse(session_id=session_id)
```

### Part 2: Check in prompt()

```python
async def prompt(self, ..., session_id: str) -> PromptResponse:
    cancel_event = self._cancel_events.get(session_id)
    
    try:
        # Wait for cancel OR timeout
        await asyncio.wait_for(cancel_event.wait(), timeout=30.0)
        return PromptResponse(stop_reason="cancelled")  # was cancelled
    except asyncio.TimeoutError:
        pass  # normal flow continues
    
    # ... rest of prompt handling
```

### Part 3: Trigger in cancel()

```python
async def cancel(self, session_id: str) -> None:
    cancel_event = self._cancel_events.get(session_id)
    if cancel_event:
        cancel_event.set()
```

## Echo Agent: The Learning Ground

The echo agent has **one await point** - the sleep. Simple.

```python
# sandbox/crow-acp-learning/echo_agent.py
async def prompt(self, ...):
    cancel_event = self._cancel_events.get(session_id)
    
    try:
        await asyncio.wait_for(cancel_event.wait(), timeout=30.0)
        return PromptResponse(stop_reason="cancelled")
    except asyncio.TimeoutError:
        pass  # delay complete, continue
    
    # echo the text back...
```

## Real Agent: Multiple Await Points

The ACP agent has **multiple await points**:

1. `_execute_tool_calls()` - each MCP tool call
2. `session_update()` - streaming chunks to client  
3. The react loop itself (many iterations)

### Strategy: Check at Loop Start

```python
async def _react_loop(self, session_id: str):
    cancel_event = self._cancel_events.get(session_id)
    
    for turn in range(max_turns):
        # CHECK AT START OF EACH TURN
        if cancel_event and cancel_event.is_set():
            yield {"type": "cancelled"}
            return
        
        # ... normal react loop stuff
```

### Implementation for AcpAgent

```python
class AcpAgent(Agent):
    def __init__(self, ...):
        # ... existing init ...
        self._cancel_events: dict[str, asyncio.Event] = {}
    
    async def new_session(self, ...):
        session_id = session.session_id
        self._cancel_events[session_id] = asyncio.Event()
        # ... rest of session setup ...
    
    async def cancel(self, session_id: str) -> None:
        event = self._cancel_events.get(session_id)
        if event:
            event.set()
    
    async def _react_loop(self, session_id: str, ...):
        cancel_event = self._cancel_events.get(session_id)
        
        for _ in range(max_turns):
            if cancel_event and cancel_event.is_set():
                return  # breaks the loop
            
            # ... existing react loop code ...
```

Then in `prompt()`:

```python
async def prompt(self, ..., session_id: str) -> PromptResponse:
    try:
        async for chunk in self._react_loop(session_id):
            # ... yield chunks ...
        
        # Check if we exited due to cancel
        cancel_event = self._cancel_events.get(session_id)
        if cancel_event and cancel_event.is_set():
            return PromptResponse(stop_reason="cancelled")
        
        return PromptResponse(stop_reason="end_turn")
    except Exception as e:
        return PromptResponse(stop_reason="end_turn")
```

## Progression

```
echo_agent.py (simple)     AcpAgent (real)
─────────────────────     ────────────────
1 await point         →   multiple await points
wait_for()            →   check at loop start
single delay          →   react loop iterations
```

## Files to Modify

1. `crow-acp/src/crow_acp/agent.py`:
   - Add `_cancel_events` dict
   - Create event in `new_session()`
   - Implement `cancel()` 
   - Check event in `_react_loop()`
   - Handle cancelled return in `prompt()`

## Testing

1. Start echo agent with delay
2. Send prompt
3. Send cancel before delay completes
4. Verify `stop_reason="cancelled"` returned
