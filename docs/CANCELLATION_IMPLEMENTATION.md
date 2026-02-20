# Cancellation Implementation: Full Persistence Strategy

## The Problem

When cancellation happens mid-stream:
1. Tokens have been received from LLM (thinking, content, tool_calls)
2. They're accumulated inside `_process_response()` generator
3. If we cancel, the generator is abandoned and state is LOST
4. When session resumes, those tokens are gone forever

## Solution: State Accumulator with External Reference

### Pattern Overview

```
┌──────────────────────────────────────────────────────────────────┐
│  _react_loop (async generator)                                   │
│                                                                  │
│  state_accumulator = {"thinking": [], "content": [], ...}       │
│                                                                  │
│  for turn in range(max_turns):                                  │
│      ┌──────────────────────────────────────────────────────┐  │
│      │  _process_response(response, state_accumulator)      │  │
│      │                                                       │  │
│      │  # Updates state_accumulator AFTER EACH CHUNK        │  │
│      │  # External code can always see partial state        │  │
│      └──────────────────────────────────────────────────────┘  │
│                                                                  │
│      # CHECK CANCELLATION HERE                                  │
│      if cancel_event.is_set():                                  │
│          # PERSIST PARTIAL STATE BEFORE RETURNING              │
│          session.add_assistant_response(                        │
│              state_accumulator['thinking'],                     │
│              state_accumulator['content'],                      │
│              state_accumulator['tool_call_inputs'],             │
│              []  # no tool results yet                          │
│          )                                                      │
│          return  # Exit generator                               │
│                                                                  │
│      # Normal flow continues...                                 │
└──────────────────────────────────────────────────────────────────┘
```

## Implementation Details

### Step 1: Modify `_process_response()` to accept state accumulator

```python
def _process_response(self, response, state_accumulator: dict = None):
    """
    Process streaming response from LLM.
    
    Args:
        response: Streaming response from LLM
        state_accumulator: Optional dict to store partial state (for cancellation)
    
    Yields:
        Tuple of (message_type, token) for each chunk
    
    Returns:
        Tuple of (thinking, content, tool_call_inputs, usage) when done
    """
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
        # Capture usage
        if hasattr(chunk, "usage") and chunk.usage:
            final_usage = {
                "prompt_tokens": chunk.usage.prompt_tokens,
                "completion_tokens": chunk.usage.completion_tokens,
                "total_tokens": chunk.usage.total_tokens,
            }
        
        # Process chunk
        thinking, content, tool_calls, tool_call_id, new_token = (
            self._process_chunk(chunk, thinking, content, tool_calls, tool_call_id)
        )
        
        # UPDATE ACCUMULATOR AFTER EACH CHUNK (KEY CHANGE!)
        if state_accumulator is not None:
            state_accumulator['thinking'] = thinking
            state_accumulator['content'] = content
            state_accumulator['tool_calls'] = tool_calls
            # Note: tool_call_inputs computed at end
        
        # Yield for streaming
        msg_type, token = new_token
        if msg_type:
            yield msg_type, token

    # Final update to accumulator
    tool_call_inputs = self._process_tool_call_inputs(tool_calls)
    if state_accumulator is not None:
        state_accumulator['tool_call_inputs'] = tool_call_inputs
    
    return (thinking, content, tool_call_inputs, final_usage)
```

### Step 2: Modify `_react_loop()` to check cancellation and persist

```python
async def _react_loop(self, session_id: str, max_turns: int = 50000):
    """
    Main ReAct loop with cancellation support.
    
    Args:
        session_id: Session ID to get session and tools
        max_turns: Maximum number of turns to execute
    
    Yields:
        Dictionary with 'type' and 'token' or 'messages' keys
    """
    session = self._sessions[session_id]
    cancel_event = self._cancel_events.get(session_id)
    
    # STATE ACCUMULATOR - accessible from outside generator
    state_accumulator = {
        'thinking': [],
        'content': [],
        'tool_call_inputs': []
    }

    for turn in range(max_turns):
        # CHECK AT START OF EACH TURN
        if cancel_event and cancel_event.is_set():
            logger.info(f"Cancelled at start of turn {turn}")
            return
        
        # Send request to LLM
        response = self._send_request(session_id)

        # Process streaming response WITH STATE ACCUMULATOR
        gen = self._process_response(response, state_accumulator)
        while True:
            try:
                msg_type, token = next(gen)
                yield {"type": msg_type, "token": token}
                
                # CHECK AFTER EACH TOKEN (optional, for fast response)
                # Note: This check happens frequently but adds overhead
                # Can remove if performance is critical
                if cancel_event and cancel_event.is_set():
                    logger.info(f"Cancelled mid-stream after token")
                    # PERSIST PARTIAL STATE
                    session.add_assistant_response(
                        state_accumulator['thinking'],
                        state_accumulator['content'],
                        state_accumulator['tool_call_inputs'],
                        []  # no tool results
                    )
                    return
                    
            except StopIteration as e:
                thinking, content, tool_call_inputs, usage = e.value
                break

        # CHECK BEFORE TOOL EXECUTION
        if cancel_event and cancel_event.is_set():
            logger.info(f"Cancelled before tool execution")
            # PERSIST PARTIAL STATE
            session.add_assistant_response(
                state_accumulator['thinking'],
                state_accumulator['content'],
                state_accumulator['tool_call_inputs'],
                []  # no tool results
            )
            return

        # If no tool calls, we're done
        if not tool_call_inputs:
            session.add_assistant_response(thinking, content, [], [])
            yield {"type": "final_history", "messages": session.messages}
            return

        # Execute tools
        tool_results = await self._execute_tool_calls(session_id, tool_call_inputs)
        
        # CHECK AFTER TOOL EXECUTION
        if cancel_event and cancel_event.is_set():
            logger.info(f"Cancelled after tool execution")
            # PERSIST WITH TOOL RESULTS
            session.add_assistant_response(
                thinking,
                content,
                tool_call_inputs,
                tool_results
            )
            return

        # Normal persistence
        session.add_assistant_response(
            thinking, content, tool_call_inputs, tool_results
        )
```

### Step 3: Modify `prompt()` to handle cancelled response

```python
async def prompt(
    self,
    prompt: list[...],
    session_id: str,
    **kwargs: Any,
) -> PromptResponse:
    """Handle prompt request with cancellation support."""
    logger.info("Prompt request for session: %s", session_id)
    
    # Get session
    session = self._sessions.get(session_id)
    if not session:
        logger.error("Session not found: %s", session_id)
        return PromptResponse(stop_reason="cancelled")
    
    # Extract text from prompt blocks
    text_list = []
    for block in prompt:
        # ... existing extraction logic ...
    
    # Add user message to session
    session.add_message("user", " ".join(text_list))
    
    # Get cancel event
    cancel_event = self._cancel_events.get(session_id)
    
    # Run agent loop and stream updates
    try:
        async for chunk in self._react_loop(session_id):
            # Check cancellation periodically
            if cancel_event and cancel_event.is_set():
                logger.info("Cancellation detected in prompt()")
                return PromptResponse(stop_reason="cancelled")
            
            chunk_type = chunk.get("type")
            
            # ... existing chunk handling ...
            
            if chunk_type == "final_history":
                break
        
        # Check if we exited due to cancellation
        if cancel_event and cancel_event.is_set():
            return PromptResponse(stop_reason="cancelled")
        
        return PromptResponse(stop_reason="end_turn")
    
    except Exception as e:
        logger.error("Error in prompt handling: %s", e, exc_info=True)
        # Still check for cancellation on errors
        if cancel_event and cancel_event.is_set():
            return PromptResponse(stop_reason="cancelled")
        return PromptResponse(stop_reason="end_turn")
```

### Step 4: Implement `cancel()` method

```python
async def cancel(self, session_id: str, **kwargs: Any) -> None:
    """Handle cancellation request."""
    logger.info("Cancel request for session: %s", session_id)
    
    cancel_event = self._cancel_events.get(session_id)
    if cancel_event is None:
        logger.warning(f"No cancel event for session: {session_id}")
        return
    
    # Set the event - all checking code will see this
    cancel_event.set()
    logger.info(f"Cancel event set for session: {session_id}")
```

### Step 5: Initialize cancel event in `new_session()`

```python
async def new_session(
    self,
    cwd: str,
    mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio],
    **kwargs: Any,
) -> NewSessionResponse:
    """Create a new session with cancellation support."""
    logger.info("Creating new session in cwd: %s", cwd)
    
    # ... existing MCP client setup ...
    
    session = Session.create(...)
    
    # CREATE CANCEL EVENT
    self._cancel_events[session.session_id] = asyncio.Event()
    
    # ... rest of session setup ...
    
    return NewSessionResponse(session_id=session.session_id, modes=None)
```

## Checkpoint Strategy: Where to Check

We check cancellation at these strategic points:

1. **Start of each turn** - Cheap check, catches cancellations that happened while idle
2. **After each token** (optional) - Fastest response but adds overhead
3. **Before tool execution** - Prevents unnecessary tool calls
4. **After tool execution** - Catches cancellations that happened during tool calls
5. **In prompt() loop** - Catches cancellations between chunks

## Persistence Guarantees

With this implementation:

✅ **No token loss**: Every received token is in `state_accumulator`
✅ **Persisted on cancel**: `session.add_assistant_response()` called before return
✅ **Resumable**: Session can be loaded and continued with all context
✅ **Clean exit**: Returns `stop_reason="cancelled"` per ACP spec

## Testing Strategy

```python
# Test 1: Cancel mid-stream
1. Start prompt
2. Wait for first token to arrive
3. Send cancel request
4. Verify session has partial content persisted
5. Load session and continue
6. Verify no information loss

# Test 2: Cancel during tool execution
1. Start prompt that triggers tool call
2. Send cancel during tool execution
3. Verify partial thinking + content + tool_call persisted
4. Load session and verify tool_result missing (expected)

# Test 3: Rapid cancel
1. Send prompt and cancel immediately
2. Verify clean exit with stop_reason="cancelled"
3. Verify session state is consistent
```

## Implementation Checklist

- [ ] Add `_cancel_events: dict[str, asyncio.Event]` to `__init__`
- [ ] Create event in `new_session()`
- [ ] Implement `cancel()` method
- [ ] Modify `_process_response()` to accept `state_accumulator`
- [ ] Modify `_react_loop()` to:
  - [ ] Create state_accumulator
  - [ ] Pass it to `_process_response()`
  - [ ] Check cancel_event at strategic points
  - [ ] Persist partial state on cancel
- [ ] Modify `prompt()` to check cancellation and return "cancelled"
- [ ] Write tests
- [ ] Test with echo agent first (simpler)
- [ ] Test with AcpAgent (real scenario)
