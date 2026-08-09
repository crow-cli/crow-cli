# Cancellation: Sandbox vs AcpAgent Pattern Comparison

## Current Patterns

### Sandbox Pattern (Cleaner)
```python
async def process_response(response):
    thinking, content, tool_calls, tool_call_id = [], [], {}, None
    async for chunk in response:
        thinking, content, tool_calls, tool_call_id, new_token = process_chunk(
            chunk, thinking, content, tool_calls, tool_call_id
        )
        msg_type, token = new_token
        if msg_type:
            yield msg_type, token
    # Yield final result as a special chunk
    yield "final", (thinking, content, process_tool_call_inputs(tool_calls))

async def react_loop(...):
    for _ in range(max_turns):
        response = await send_request(messages, model, tools, lm)
        gen = process_response(response)
        thinking, content, tool_call_inputs = [], [], []
        async for msg_type, token in gen:
            if msg_type == "final":
                thinking, content, tool_call_inputs = token
            else:
                yield {"type": msg_type, "token": token}
```

**Pros:**
- Cleaner - no `try/except StopIteration`
- All state flows through same loop
- Uses `async for` naturally

**Cons:**
- State still trapped in generator until "final" chunk
- If cancelled mid-stream, partial state is LOST

### AcpAgent Pattern (Current)
```python
def _process_response(self, response):
    thinking, content, tool_calls, tool_call_id = [], [], {}, None
    for chunk in response:  # sync generator
        # ... process chunk ...
        yield msg_type, token
    return (thinking, content, tool_call_inputs, final_usage)  # via StopIteration

async def _react_loop(self, session_id):
    for _ in range(max_turns):
        response = self._send_request(session_id)
        gen = self._process_response(response)
        while True:
            try:
                msg_type, token = next(gen)
                yield {"type": msg_type, "token": token}
            except StopIteration as e:
                thinking, content, tool_call_inputs, usage = e.value
                break
```

**Pros:**
- Returns usage stats via StopIteration

**Cons:**
- Clunky `try/except StopIteration` pattern
- State trapped until generator completes
- If cancelled mid-stream, partial state is LOST

## Hybrid Solution: Best of Both

Combine:
1. **Clean "final" yield pattern** from sandbox
2. **State accumulator pattern** for cancellation

```python
async def process_response(response, state_accumulator: dict = None):
    """
    Process streaming response with state accumulator for cancellation.
    
    Args:
        response: Streaming response from LLM
        state_accumulator: Optional dict to expose partial state externally
    
    Yields:
        - (msg_type, token) for each streaming chunk
        - ("final", (thinking, content, tool_call_inputs, usage)) when done
    """
    thinking, content, tool_calls, tool_call_id = [], [], {}, None
    final_usage = None
    
    # Initialize state accumulator if provided
    if state_accumulator is not None:
        state_accumulator.update({
            'thinking': thinking,
            'content': content,
            'tool_calls': tool_calls,
            'tool_call_inputs': []
        })

    async for chunk in response:
        # Capture usage
        if hasattr(chunk, "usage") and chunk.usage:
            final_usage = {
                "prompt_tokens": chunk.usage.prompt_tokens,
                "completion_tokens": chunk.usage.completion_tokens,
                "total_tokens": chunk.usage.total_tokens,
            }
        
        # Process chunk
        thinking, content, tool_calls, tool_call_id, new_token = process_chunk(
            chunk, thinking, content, tool_calls, tool_call_id
        )
        
        # *** KEY: UPDATE ACCUMULATOR AFTER EACH CHUNK ***
        if state_accumulator is not None:
            state_accumulator['thinking'] = thinking
            state_accumulator['content'] = content
            state_accumulator['tool_calls'] = tool_calls
        
        # Yield for streaming
        msg_type, token = new_token
        if msg_type:
            yield msg_type, token

    # Compute final tool_call_inputs
    tool_call_inputs = process_tool_call_inputs(tool_calls)
    
    # Final update to accumulator
    if state_accumulator is not None:
        state_accumulator['tool_call_inputs'] = tool_call_inputs
    
    # Yield final result (cleaner than StopIteration)
    yield "final", (thinking, content, tool_call_inputs, final_usage)


async def react_loop(messages, mcp_client, lm, model, tools, cancel_event=None, session=None, max_turns=50000):
    """
    React loop with cancellation support.
    
    Args:
        messages: Conversation history
        mcp_client: MCP client for tool execution
        lm: Language model client
        model: Model identifier
        tools: Available tools
        cancel_event: asyncio.Event for cancellation signalling
        session: Session object for persistence (optional)
        max_turns: Maximum iterations
    """
    for turn in range(max_turns):
        # Check at start of turn
        if cancel_event and cancel_event.is_set():
            return
        
        # Send request
        response = await send_request(messages, model, tools, lm)
        
        # STATE ACCUMULATOR - for cancellation
        state_accumulator = {
            'thinking': [],
            'content': [],
            'tool_call_inputs': []
        }
        
        # Process streaming response
        gen = process_response(response, state_accumulator)
        thinking, content, tool_call_inputs, usage = [], [], [], None
        
        async for msg_type, token in gen:
            if msg_type == "final":
                thinking, content, tool_call_inputs, usage = token
            else:
                # Check cancellation after each token
                if cancel_event and cancel_event.is_set():
                    # *** PERSIST PARTIAL STATE ***
                    if session:
                        session.add_assistant_response(
                            state_accumulator['thinking'],
                            state_accumulator['content'],
                            state_accumulator['tool_call_inputs'],
                            []  # no tool results
                        )
                    return
                
                yield {"type": msg_type, "token": token}
        
        # Check before tool execution
        if cancel_event and cancel_event.is_set():
            if session:
                session.add_assistant_response(
                    thinking, content, tool_call_inputs, []
                )
            return
        
        # If no tool calls, we're done
        if not tool_call_inputs:
            messages = add_response_to_messages(messages, thinking, content, [], [])
            yield {"type": "final_history", "messages": messages}
            return
        
        # Execute tools
        tool_results = await execute_tool_calls(mcp_client, tool_call_inputs, verbose=False)
        
        # Check after tool execution
        if cancel_event and cancel_event.is_set():
            if session:
                session.add_assistant_response(
                    thinking, content, tool_call_inputs, tool_results
                )
            return
        
        # Normal flow
        messages = add_response_to_messages(
            messages, thinking, content, tool_call_inputs, tool_results
        )
```

## Migration Path

### Step 1: Update `process_response()` signature
- Add `state_accumulator` parameter
- Update state after each chunk
- Change `return` to `yield "final"`

### Step 2: Update `_react_loop()` 
- Create state_accumulator
- Pass to process_response
- Check cancel_event and persist on cancellation

### Step 3: Wire up cancel_event
- Create in `new_session()`
- Check in `prompt()`
- Set in `cancel()`

## Key Benefits

✅ **Cleaner code** - No more `try/except StopIteration`
✅ **Full persistence** - State accumulator captures partial state
✅ **Fast response** - Check after each token
✅ **Consistent pattern** - All state flows through same loop

## Testing Strategy

```python
# Test partial state persistence
async def test_cancel_mid_stream():
    cancel_event = asyncio.Event()
    session = Session.create(...)
    
    async def cancel_after_first_token():
        await asyncio.sleep(0.1)  # Let first token through
        cancel_event.set()
    
    asyncio.create_task(cancel_after_first_token())
    
    chunks = []
    async for chunk in react_loop(..., cancel_event=cancel_event, session=session):
        chunks.append(chunk)
    
    # Verify session has partial content
    messages = session.messages
    assert len(messages) > 0
    assert messages[-1]['role'] == 'assistant'
    assert len(messages[-1].get('content', '')) > 0  # Has some content
```
