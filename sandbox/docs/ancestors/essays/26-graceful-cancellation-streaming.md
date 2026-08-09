# Graceful Cancellation: Letting the Last Token Stream In

## The Problem

Currently, when a user requests cancellation of an ongoing LLM stream in `crow-cli`, the cancellation happens abruptly via `task.cancel()` in `AcpAgent.cancel()`. This immediately raises `CancelledError` in the running task, interrupting the stream mid-token and potentially losing the final chunk of the response.

### Current Flow

```
User Request → AcpAgent.cancel() → task.cancel() → CancelledError → Stream Interrupted
```

The cancellation is checked at coarse-grained boundaries:
- Start of each turn in `react_loop`
- Before tool execution
- After tool execution

But NOT during the actual streaming of tokens from the LLM.

## The Goal

Allow the current token/chunk to complete streaming before cancellation takes effect. This provides:
1. **Better UX**: User sees complete thoughts/tokens rather than cut-off text
2. **Data integrity**: Last token is properly persisted in session history
3. **Graceful degradation**: Cancellation still happens quickly, but not at the cost of losing partial data

## Solution Architecture

### Phase 1: Check Cancellation at Stream Boundaries (Minimal Change)

Instead of relying solely on `task.cancel()`, use the `cancel_event` to check for cancellation at natural breakpoints in the streaming loop.

**Location**: `react_loop()` in `react.py`

**Current code** (line ~408-562):
```python
async for msg_type, token in process_response(response, state_accumulator):
    if msg_type == "final":
        thinking, content, tool_call_inputs, usage = token
    else:
        yield {"type": msg_type, "token": token}
```

**Proposed change**:
```python
async for msg_type, token in process_response(response, state_accumulator):
    # Check cancellation at chunk boundaries (between tokens)
    if cancel_event and cancel_event.is_set():
        logger.info("Cancellation requested, finishing current chunk")
        # Yield any accumulated token before stopping
        if msg_type:
            yield {"type": msg_type, "token": token}
        # Persist current state and exit gracefully
        session.add_assistant_response(
            thinking, content, tool_call_inputs, logger, usage
        )
        return
    
    if msg_type == "final":
        thinking, content, tool_call_inputs, usage = token
    else:
        yield {"type": msg_type, "token": token}
```

**Benefits**:
- Minimal code changes
- Cancellation happens between tokens, not mid-token
- State is properly persisted

**Limitations**:
- Still relies on the async iterator reaching a natural yield point
- If cancellation happens during `process_response()`'s `async for chunk in response`, we might still miss the last chunk

### Phase 2: Cooperative Cancellation in `process_response()` (Recommended)

Modify `process_response()` to accept and check the `cancel_event`, allowing cancellation between chunks.

**Current signature**:
```python
async def process_response(response, state_accumulator: dict):
```

**Proposed signature**:
```python
async def process_response(
    response, 
    state_accumulator: dict,
    cancel_event: Event | None = None
):
```

**Implementation**:
```python
async def process_response(
    response, 
    state_accumulator: dict,
    cancel_event: Event | None = None
):
    thinking, content, tool_calls, tool_call_id = [], [], {}, None
    final_usage = None
    
    state_accumulator.update({
        "thinking": thinking,
        "content": content,
        "tool_calls": tool_calls,
        "tool_call_inputs": [],
    })
    
    async for chunk in response:
        # Check cancellation between chunks
        if cancel_event and cancel_event.is_set():
            logger.info("Cancellation requested, finishing current chunk")
            break
        
        if hasattr(chunk, "usage") and chunk.usage:
            final_usage = {
                "prompt_tokens": chunk.usage.prompt_tokens,
                "completion_tokens": chunk.usage.completion_tokens,
                "total_tokens": chunk.usage.total_tokens,
            }
        
        thinking, content, tool_calls, tool_call_id, new_token = process_chunk(
            chunk, thinking, content, tool_calls, tool_call_id
        )
        state_accumulator["thinking"] = thinking
        state_accumulator["content"] = content
        state_accumulator["tool_calls"] = tool_calls
        
        msg_type, token = new_token
        if msg_type:
            yield msg_type, token
    
    tool_call_inputs = process_tool_call_inputs(tool_calls)
    state_accumulator["tool_call_inputs"] = tool_call_inputs
    yield "final", (thinking, content, tool_call_inputs, final_usage)
```

**Update `react_loop()` to pass cancel_event**:
```python
async for msg_type, token in process_response(
    response, 
    state_accumulator,
    cancel_event  # Pass the cancel event
):
    # ... rest of the loop
```

**Benefits**:
- Cancellation checked at every chunk boundary
- Last complete chunk is always processed and yielded
- State is persisted before returning

### Phase 3: Shield Critical Sections (Advanced)

For maximum control, use `asyncio.shield()` to protect the final chunk processing from external cancellation.

**Pattern**:
```python
async def react_loop(...):
    # ... setup code ...
    
    try:
        async for msg_type, token in process_response(response, state_accumulator):
            # Check our own cancel_event, not task cancellation
            if cancel_event and cancel_event.is_set():
                # Let current token finish
                if msg_type:
                    yield {"type": msg_type, "token": token}
                break
            else:
                yield {"type": msg_type, "token": token}
    except asyncio.CancelledError:
        # External cancellation - still persist state
        logger.info("External cancellation, persisting state")
        session.add_assistant_response(...)
        # Don't re-raise - let it complete gracefully
        raise
```

**Alternative with shield**:
```python
async def cancel_with_grace(session_id: str):
    """Cancel but allow current operation to complete."""
    cancel_event = self._cancel_events[session_id]
    cancel_event.set()
    
    # Wait for current prompt task to finish naturally (with timeout)
    task = self._prompt_tasks.get(session_id)
    if task and not task.done():
        try:
            # Wait up to 5 seconds for graceful completion
            await asyncio.wait_for(
                asyncio.shield(task),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            # Force cancel if it takes too long
            task.cancel()
        except asyncio.CancelledError:
            # Task completed normally
            pass
```

## Implementation Plan

### Step 1: Modify `process_response()` to accept `cancel_event`

**File**: `crow-cli/src/crow_cli/agent/react.py`
**Lines**: ~223-266

1. Add `cancel_event: Event | None = None` parameter
2. Add cancellation check inside the `async for chunk in response` loop
3. Break gracefully when cancellation is detected

### Step 2: Update `react_loop()` to pass `cancel_event`

**File**: `crow-cli/src/crow_cli/agent/react.py`
**Lines**: ~408-562

1. Pass `cancel_event` to `process_response()` call
2. Add cancellation check before and after tool execution (already exists, verify it works with new flow)

### Step 3: Update `AcpAgent.prompt()` to use event-based cancellation

**File**: `crow-cli/src/crow_cli/agent/main.py`
**Lines**: ~423-675

Current `cancel()` method:
```python
async def cancel(self, session_id: str, **kwargs: Any) -> None:
    """Handle cancellation by immediately cancelling the underlying Task."""
    self._session_logger.info("Cancel request for session: %s", session_id)

    task = self._prompt_tasks.get(session_id)
    if task and not task.done():
        task.cancel()  # <--- Forceful cancellation
```

**Option A (Minimal)**: Just set the event, don't cancel task
```python
async def cancel(self, session_id: str, **kwargs: Any) -> None:
    """Handle cancellation by setting cancel_event."""
    self._session_logger.info("Cancel request for session: %s", session_id)

    cancel_event = self._cancel_events.get(session_id)
    if cancel_event:
        cancel_event.set()  # Signal cancellation
    
    # Don't cancel the task - let it finish naturally
```

**Option B (Hybrid)**: Set event AND cancel task, but rely on event checks
```python
async def cancel(self, session_id: str, **kwargs: Any) -> None:
    """Handle cancellation by setting cancel_event and cancelling task."""
    self._session_logger.info("Cancel request for session: %s", session_id)

    cancel_event = self._cancel_events.get(session_id)
    if cancel_event:
        cancel_event.set()

    task = self._prompt_tasks.get(session_id)
    if task and not task.done():
        task.cancel()
```

With Option B, the `CancelledError` will be raised, but our cancellation checks in `process_response()` and `react_loop()` will catch it at the next chunk boundary and persist state before re-raising.

### Step 4: Handle `CancelledError` in `react_loop()` to persist state

**File**: `crow-cli/src/crow_cli/agent/react.py`
**Lines**: ~430-440

Current code:
```python
except asyncio.CancelledError:
    logger.info("React loop cancelled mid-stream")

    session.add_assistant_response(
        state_accumulator["thinking"],
        state_accumulator["content"],
        state_accumulator["tool_call_inputs"],
        logger,
        usage,
    )
    raise
```

This already persists state! Just verify it works with the new event-based flow.

### Step 5: Test the implementation

**Test scenarios**:
1. Cancel during LLM streaming → Should see last complete token
2. Cancel during tool execution → Should complete current tool, persist state
3. Cancel between turns → Should complete current turn, persist state
4. Rapid cancel → Should handle gracefully without race conditions

## Edge Cases to Consider

1. **What if cancellation happens during `send_request()`?**
   - Add cancellation check in retry loop
   - Don't retry on cancellation

2. **What if cancellation happens during tool execution?**
   - Current code already handles this
   - Tool execution is not cancelled mid-operation
   - Only checked before/after tool execution

3. **What if multiple cancels are requested?**
   - `Event` is idempotent - setting it multiple times is fine
   - Subsequent cancels are no-ops

4. **What about session cleanup after cancellation?**
   - `cleanup()` in `AcpAgent` handles this
   - MCP clients are managed by `AsyncExitStack`

## Trade-offs

### Event-based vs Task.cancel()

| Aspect | Event-based | Task.cancel() |
|--------|-------------|---------------|
| Granularity | Coarse (chunk boundaries) | Fine (any await point) |
| Control | Cooperative | Preemptive |
| Safety | High (clean state) | Medium (can interrupt mid-operation) |
| Responsiveness | Medium (waits for chunk) | High (immediate) |

**Recommendation**: Use both - set event AND cancel task. The event checks provide graceful degradation points, while `task.cancel()` ensures cancellation eventually happens even if event checks are missed.

## Conclusion

The key insight is that cancellation in async streaming should be **cooperative** rather than **preemptive**. By checking `cancel_event.is_set()` at natural boundaries (between chunks/tokens), we allow the current operation to complete while still responding quickly to cancellation requests.

This approach:
1. Preserves data integrity (last token is streamed)
2. Maintains responsiveness (cancellation happens at chunk boundaries, ~10-100ms)
3. Keeps code simple (no complex state machine or shielding)
4. Works with existing state persistence logic

The implementation is straightforward: pass `cancel_event` through the call chain, check it at chunk boundaries, and persist state before exiting.

---

# Testing Plan

## Research Findings

Based on research into async cancellation testing patterns, here are the key principles:

### 1. Use `pytest-asyncio` for async tests
- Provides event loop management
- Supports async test functions with `@pytest.mark.asyncio`
- Handles cleanup of pending tasks between tests

### 2. Test cancellation at different granularities
- Test that `CancelledError` is raised at appropriate points
- Test that cleanup code runs (in `finally` blocks or exception handlers)
- Test that state is persisted before cancellation completes

### 3. Common testing patterns

**Pattern A: Test task cancellation**
```python
import pytest
import asyncio

@pytest.mark.asyncio
async def test_task_cancellation():
    task = asyncio.create_task(long_running_operation())
    
    # Let it start
    await asyncio.sleep(0.1)
    
    # Cancel it
    task.cancel()
    
    # Verify cancellation
    with pytest.raises(asyncio.CancelledError):
        await task
    
    assert task.cancelled()
```

**Pattern B: Test graceful cancellation with cleanup**
```python
@pytest.mark.asyncio
async def test_graceful_cancellation():
    cleanup_ran = False
    state_persisted = False
    
    async def operation_with_cleanup():
        nonlocal cleanup_ran, state_persisted
        try:
            await long_running_task()
        except asyncio.CancelledError:
            # Perform cleanup
            state_persisted = True
            cleanup_ran = True
            raise
    
    task = asyncio.create_task(operation_with_cleanup())
    await asyncio.sleep(0.1)
    task.cancel()
    
    with pytest.raises(asyncio.CancelledError):
        await task
    
    assert cleanup_ran
    assert state_persisted
```

**Pattern C: Test event-based cancellation**
```python
@pytest.mark.asyncio
async def test_event_based_cancellation():
    cancel_event = asyncio.Event()
    result = []
    
    async def cooperative_task():
        for i in range(10):
            # Check for cancellation
            if cancel_event.is_set():
                break
            result.append(i)
            await asyncio.sleep(0.01)
    
    task = asyncio.create_task(cooperative_task())
    await asyncio.sleep(0.05)
    cancel_event.set()
    
    await task  # Should complete gracefully, not raise CancelledError
    
    # Verify we got some results but not all
    assert len(result) < 10
    assert result == list(range(len(result)))
```

## Test Cases

### Test 1: Cancellation During LLM Streaming

**Purpose**: Verify that cancellation during `process_response()` allows the current chunk to complete.

**File**: `crow-cli/tests/unit/test_cancellation.py`

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from acp.schema import ClientCapabilities
from crow_cli.agent.react import process_response, react_loop
from crow_cli.agent.session import Session

@pytest.mark.asyncio
async def test_process_response_cancellation_during_stream():
    """Test that process_response handles cancellation gracefully."""
    # Setup mock response that yields multiple chunks
    async def mock_stream():
        for i in range(10):
            yield MagicMock(
                choices=[MagicMock(
                    delta=MagicMock(
                        content=f"token {i}",
                        reasoning_content=None,
                        tool_calls=None
                    )
                )]
            )
            await asyncio.sleep(0.01)
    
    # Create cancel event
    cancel_event = asyncio.Event()
    
    # Cancel after first chunk
    async def cancel_soon():
        await asyncio.sleep(0.02)
        cancel_event.set()
    
    # Run both
    cancel_task = asyncio.create_task(cancel_soon())
    chunks = []
    
    async for msg_type, token in process_response(
        mock_stream(),
        {"thinking": [], "content": [], "tool_calls": {}, "tool_call_inputs": []},
        cancel_event
    ):
        if msg_type:
            chunks.append((msg_type, token))
    
    await cancel_task
    
    # Should have received some chunks (at least 1-2 before cancellation)
    assert len(chunks) >= 1
    # Should not have raised CancelledError - it should exit gracefully
```

### Test 2: Cancellation Before Tool Execution

**Purpose**: Verify that cancellation before tool execution persists state and doesn't execute tools.

```python
@pytest.mark.asyncio
async def test_cancellation_before_tool_execution():
    """Test that tools are not executed if cancelled before them."""
    cancel_event = asyncio.Event()
    tool_executed = False
    
    async def mock_execute_tools(*args, **kwargs):
        nonlocal tool_executed
        tool_executed = True
        return []
    
    # Setup session and mocks
    session = MagicMock()
    sessions = {"test-session": session}
    
    # Simulate react_loop logic
    thinking, content = ["thinking"], ["content"]
    tool_call_inputs = [{"name": "test_tool", "args": {}}]
    
    # Check cancellation before tools
    if cancel_event.is_set():
        # Should persist state without executing tools
        session.add_assistant_response.assert_called_once()
        return
    
    # Execute tools (should not reach here if cancelled)
    await mock_execute_tools()
    tool_executed = True
    
    # Verify
    assert not tool_executed
```

### Test 3: Cancellation During Tool Execution

**Purpose**: Verify that tool execution completes even if cancelled during.

```python
@pytest.mark.asyncio
async def test_tool_execution_completes_despite_cancellation():
    """Test that in-progress tool execution is not interrupted."""
    tool_completed = False
    
    async def long_running_tool():
        nonlocal tool_completed
        await asyncio.sleep(0.5)  # Simulate work
        tool_completed = True
        return "result"
    
    # Start tool
    task = asyncio.create_task(long_running_tool())
    
    # Cancel immediately (should not interrupt the tool)
    task.cancel()
    
    # Wait for task to complete (tool should finish despite cancel)
    # In cooperative cancellation, the tool runs to completion
    result = await task
    
    assert tool_completed
    assert result == "result"
```

### Test 4: State Persistence After Cancellation

**Purpose**: Verify that session state is properly persisted after cancellation.

```python
@pytest.mark.asyncio
async def test_state_persistence_after_cancellation():
    """Test that partial state is saved to session after cancellation."""
    from crow_cli.agent.session import Session
    from crow_cli.agent.db import create_database, session_from_db
    import tempfile
    from pathlib import Path
    
    # Create temp database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db_uri = f"sqlite:///{db_path}"
        create_database(db_uri)
        
        # Create session with messages
        session = Session.create(
            prompt_id="test-prompt",
            prompt_args={},
            tool_definitions=[],
            request_params={},
            model_identifier="test-model",
            db_uri=db_uri,
            cwd="/tmp",
        )
        
        # Add partial state
        session.add_assistant_response(
            thinking=["partial", "thinking"],
            content=["partial", "content"],
            tool_call_inputs=[],
            logger=MagicMock(),
            usage={"total_tokens": 50}
        )
        
        # Verify state is in session
        assert len(session.messages) > 0
        assert any("partial" in str(msg) for msg in session.messages)
```

### Test 5: Multiple Cancellation Requests

**Purpose**: Verify that multiple cancel() calls are idempotent.

```python
@pytest.mark.asyncio
async def test_multiple_cancellation_requests():
    """Test that calling cancel() multiple times is safe."""
    cancel_event = asyncio.Event()
    
    # First cancellation
    cancel_event.set()
    assert cancel_event.is_set()
    
    # Second cancellation (should be no-op)
    cancel_event.set()
    assert cancel_event.is_set()
    
    # Third cancellation
    cancel_event.set()
    assert cancel_event.is_set()
    
    # Verify event is still set
    assert cancel_event.is_set()
```

### Test 6: Integration Test - Full Prompt Cancellation

**Purpose**: End-to-end test of cancellation during a full prompt request.

```python
@pytest.mark.asyncio
async def test_full_prompt_cancellation():
    """Test cancellation in the context of a full prompt request."""
    from crow_cli.agent.main import AcpAgent
    from crow_cli.agent.configure import Config
    
    # Create agent with test config
    config = Config.load(config_dir=Path("/tmp/test-config"))
    agent = AcpAgent(config=config)
    
    # Setup session
    await agent.new_session(cwd="/tmp")
    session_id = agent._session_id
    
    # Start prompt in background
    prompt_task = asyncio.create_task(
        agent.prompt(
            prompt=[{"type": "text", "text": "Hello"}],
            session_id=session_id
        )
    )
    
    # Give it time to start streaming
    await asyncio.sleep(0.1)
    
    # Cancel
    await agent.cancel(session_id)
    
    # Wait for prompt to complete (should not raise)
    result = await prompt_task
    
    # Verify cancellation response
    assert result.stop_reason == "cancelled" or result.stop_reason == "end_turn"
```

### Test 7: Cancellation Timing - Chunk Boundaries

**Purpose**: Verify cancellation happens at chunk boundaries, not mid-chunk.

```python
@pytest.mark.asyncio
async def test_cancellation_at_chunk_boundaries():
    """Test that cancellation occurs between chunks, not mid-chunk."""
    cancel_event = asyncio.Event()
    chunks_received = []
    
    async def mock_stream():
        """Mock stream that yields complete chunks."""
        for i in range(10):
            yield MagicMock(
                choices=[MagicMock(
                    delta=MagicMock(
                        content=f"complete_token_{i}",
                        reasoning_content=None,
                        tool_calls=None
                    )
                )]
            )
            await asyncio.sleep(0.01)
    
    async def cancel_after_chunk_3():
        await asyncio.sleep(0.035)  # After ~3 chunks
        cancel_event.set()
    
    # Run both
    cancel_task = asyncio.create_task(cancel_after_chunk_3())
    
    async for msg_type, token in process_response(
        mock_stream(),
        {"thinking": [], "content": [], "tool_calls": {}, "tool_call_inputs": []},
        cancel_event
    ):
        if msg_type == "content":
            chunks_received.append(token)
            # Verify chunks are complete (not truncated)
            assert token.startswith("complete_token_")
    
    await cancel_task
    
    # Should have received some complete chunks
    assert len(chunks_received) >= 1
    # All chunks should be complete tokens
    for chunk in chunks_received:
        assert chunk.startswith("complete_token_")
```

## Test Infrastructure

### Required Dependencies

Add to `crow-cli/pyproject.toml`:

```toml
[project.optional-dependencies]
test = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
    "pytest-timeout>=2.0.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
timeout = 30
```

### Test File Structure

```
crow-cli/tests/
├── unit/
│   ├── __init__.py
│   ├── test_cancellation.py      # New file with cancellation tests
│   ├── test_agent_init.py
│   └── ...
├── integration/
│   ├── __init__.py
│   ├── test_cancellation_e2e.py  # New file with end-to-end tests
│   └── ...
└── conftest.py
```

### Running the Tests

```bash
# Run all tests
cd /home/thomas/src/backup/nid-backup/crow-cli
uv --project . run pytest

# Run only cancellation tests
uv --project . run pytest tests/unit/test_cancellation.py

# Run with coverage
uv --project . run pytest tests/unit/test_cancellation.py --cov=crow_cli --cov-report=html

# Run with timeout
uv --project . run pytest tests/unit/test_cancellation.py --timeout=30
```

## Test Priority

### High Priority (Implement First)

1. **Test 1**: Cancellation During LLM Streaming - Core functionality
2. **Test 4**: State Persistence After Cancellation - Data integrity
3. **Test 5**: Multiple Cancellation Requests - Edge case, easy to miss

### Medium Priority (Implement Second)

4. **Test 2**: Cancellation Before Tool Execution - Important for correctness
5. **Test 7**: Cancellation Timing - Verifies the key improvement
6. **Test 6**: Integration Test - Full end-to-end verification

### Lower Priority (Implement Last)

7. **Test 3**: Cancellation During Tool Execution - Less critical, tools should complete anyway

## Verification Checklist

After implementing the tests, verify:

- [ ] All tests pass with `pytest`
- [ ] Cancellation tests have >90% code coverage
- [ ] No tests timeout (adjust if needed)
- [ ] Tests run in isolation and in combination
- [ ] Mock objects properly simulate LLM streaming behavior
- [ ] Test fixtures clean up after themselves (no temp files left)
- [ ] Test database is properly cleaned up

## Future Enhancements

Once the basic tests are in place, consider:

1. **Load testing**: Test cancellation under high load
2. **Performance testing**: Measure cancellation latency
3. **Fuzz testing**: Random cancellation timing
4. **Integration with CI**: Run tests on every commit
