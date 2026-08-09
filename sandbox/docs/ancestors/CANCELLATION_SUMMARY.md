# Cancellation Implementation: Final Summary

## The Core Problem

When cancelling an async generator mid-stream, **partial state is trapped inside the generator** and lost.

## The Solution: State Accumulator Pattern

```python
# Create mutable dict outside generator
state_accumulator = {'thinking': [], 'content': [], 'tool_call_inputs': []}

# Pass to generator
gen = process_response(response, state_accumulator)

# Generator updates it after each chunk
async for msg_type, token in gen:
    # state_accumulator always has partial state
    if cancel_event.is_set():
        # PERSIST BEFORE RETURNING
        save_state(state_accumulator)
        return
```

## Implementation for AcpAgent

### 1. Update `_process_response()` to accept state_accumulator

```python
def _process_response(self, response, state_accumulator: dict = None):
    thinking, content, tool_calls, tool_call_id = [], [], {}, None
    final_usage = None
    
    # Initialize accumulator if provided
    if state_accumulator is not None:
        state_accumulator.update({
            'thinking': thinking,
            'content': content,
            'tool_calls': tool_calls,
            'tool_call_inputs': []
        })

    for chunk in response:
        # ... process chunk ...
        
        # UPDATE ACCUMULATOR AFTER EACH CHUNK
        if state_accumulator is not None:
            state_accumulator['thinking'] = thinking
            state_accumulator['content'] = content
            state_accumulator['tool_calls'] = tool_calls
        
        yield msg_type, token

    # Final update
    tool_call_inputs = self._process_tool_call_inputs(tool_calls)
    if state_accumulator is not None:
        state_accumulator['tool_call_inputs'] = tool_call_inputs
    
    return (thinking, content, tool_call_inputs, final_usage)
```

### 2. Update `_react_loop()` to use state_accumulator

```python
async def _react_loop(self, session_id: str, max_turns: int = 50000):
    session = self._sessions[session_id]
    cancel_event = self._cancel_events.get(session_id)
    
    # STATE ACCUMULATOR
    state_accumulator = {
        'thinking': [],
        'content': [],
        'tool_call_inputs': []
    }

    for turn in range(max_turns):
        # Check at start
        if cancel_event and cancel_event.is_set():
            return
        
        response = self._send_request(session_id)
        gen = self._process_response(response, state_accumulator)
        
        while True:
            try:
                msg_type, token = next(gen)
                yield {"type": msg_type, "token": token}
                
                # Check after each token
                if cancel_event and cancel_event.is_set():
                    # PERSIST PARTIAL STATE
                    session.add_assistant_response(
                        state_accumulator['thinking'],
                        state_accumulator['content'],
                        state_accumulator['tool_call_inputs'],
                        []
                    )
                    return
                    
            except StopIteration as e:
                thinking, content, tool_call_inputs, usage = e.value
                break

        # Check before tools
        if cancel_event and cancel_event.is_set():
            session.add_assistant_response(thinking, content, tool_call_inputs, [])
            return

        if not tool_call_inputs:
            session.add_assistant_response(thinking, content, [], [])
            yield {"type": "final_history", "messages": session.messages}
            return

        tool_results = await self._execute_tool_calls(session_id, tool_call_inputs)
        
        # Check after tools
        if cancel_event and cancel_event.is_set():
            session.add_assistant_response(thinking, content, tool_call_inputs, tool_results)
            return

        session.add_assistant_response(thinking, content, tool_call_inputs, tool_results)
```

### 3. Initialize cancel event in `new_session()`

```python
async def new_session(self, ..., **kwargs) -> NewSessionResponse:
    # ... existing code ...
    session_id = session.session_id
    
    # CREATE CANCEL EVENT
    self._cancel_events[session_id] = asyncio.Event()
    
    return NewSessionResponse(session_id=session_id)
```

### 4. Implement `cancel()` method

```python
async def cancel(self, session_id: str, **kwargs: Any) -> None:
    cancel_event = self._cancel_events.get(session_id)
    if cancel_event:
        cancel_event.set()
```

### 5. Handle cancelled response in `prompt()`

```python
async def prompt(self, ..., session_id: str) -> PromptResponse:
    # ... existing code ...
    
    cancel_event = self._cancel_events.get(session_id)
    
    try:
        async for chunk in self._react_loop(session_id):
            if cancel_event and cancel_event.is_set():
                return PromptResponse(stop_reason="cancelled")
            # ... yield chunks ...
        
        if cancel_event and cancel_event.is_set():
            return PromptResponse(stop_reason="cancelled")
        
        return PromptResponse(stop_reason="end_turn")
    except Exception:
        if cancel_event and cancel_event.is_set():
            return PromptResponse(stop_reason="cancelled")
        return PromptResponse(stop_reason="end_turn")
```

## Checkpoint Locations

1. **Start of each turn** - Catches cancellations while idle
2. **After each token** - Fastest response (optional, adds overhead)
3. **Before tool execution** - Saves unnecessary work
4. **After tool execution** - Catches cancellations during tools
5. **In prompt() loop** - Between chunks

## Persistence Guarantees

✅ **No token loss** - Every received token is in state_accumulator
✅ **Persisted on cancel** - session.add_assistant_response() called before return
✅ **Resumable** - Session can be loaded with all partial context
✅ **Clean exit** - Returns stop_reason="cancelled"

## Files to Modify

```
crow-acp/src/crow_acp/agent.py:
  - __init__: Add _cancel_events dict
  - new_session: Create asyncio.Event
  - cancel: Set the event
  - _process_response: Add state_accumulator parameter
  - _react_loop: Create state_accumulator, check cancel, persist on cancel
  - prompt: Check cancel and return "cancelled"
```

## Testing

```bash
# Test with sandbox version first
cd sandbox/async-react
python streaming_async_react_with_cancellation.py --test-cancel

# Then test with AcpAgent
cd ../..
pytest tests/test_cancellation.py
```
