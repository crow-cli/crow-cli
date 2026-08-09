# Async Tool Hanging: Debug Thoughts Before Resolution

## Context

When we moved to a fully async generator-based approach in crow-acp, the terminal tool appeared to hang while the file_editor tool continued working. This essay documents the debugging thought process before we discovered the issue was not actually reproducible.

## The Symptom

The terminal tool would hang when called through the crow-acp agent via FastMCP, but the file_editor tool worked fine. Both tools are defined as `async def` functions that ultimately call synchronous code internally.

## The Investigation Trail

### 1. Comparing the Two Tools

Both tools share the same pattern:

```python
# file_editor/main.py
@mcp.tool
async def file_editor(...) -> str:
    editor = get_editor()  # synchronous
    # ... synchronous operations ...
    return output

# terminal/main.py
@mcp.tool
async def terminal(...) -> str:
    term = get_terminal()  # synchronous
    result = term.execute(...)  # synchronous, blocking call
    return output
```

Both are `async def` but call synchronous code. So why would one hang and not the other?

### 2. FastMCP's Async Handling

Looking at FastMCP's tool execution path:

```python
# mcp/server/fastmcp/tools/base.py
async def run(self, arguments, context=None, convert_result=False):
    result = await self.fn_metadata.call_fn_with_arg_validation(
        self.fn,
        self.is_async,
        arguments,
        ...
    )
    return result
```

And in `func_metadata.py`:

```python
async def call_fn_with_arg_validation(self, fn, fn_is_async, ...):
    ...
    if fn_is_async:
        return await fn(**arguments_parsed_dict)
    else:
        return fn(**arguments_parsed_dict)
```

FastMCP correctly detects `async def` functions and `await`s them. The async tool runs in the event loop where it belongs.

### 3. The Real Question: What Blocks the Event Loop?

The key insight is that `async def` functions that call synchronous blocking code will **block the event loop**. When the terminal tool's `execute()` method runs its polling loop:

```python
def _execute_command(self, command, timeout):
    while True:
        output = self.backend.read_screen()
        # ... check for completion ...
        time.sleep(POLL_INTERVAL)  # BLOCKING!
```

The `time.sleep()` is synchronous and blocks the entire event loop. If something else needs to happen (like reading from the MCP transport), it can't.

### 4. Why File Editor Doesn't Have This Problem

The file_editor tool does quick, bounded operations:
- Read a file
- Write a file
- Replace a string

These complete quickly and return. The terminal tool, however, has an unbounded polling loop that could run for seconds or minutes.

### 5. The Async Generator Connection

The user mentioned "async generator based approach." If the calling code changed from:

```python
result = await mcp_client.call_tool(...)
```

To something that iterates over results as they come in (streaming), there might be a mismatch. If `call_tool` now returns an async generator but we're still treating it as a coroutine, we'd get a generator object back instead of the actual result.

### 6. The Hang Theory

The terminal tool might hang because:

1. **Event loop blocking**: The synchronous `time.sleep()` in the polling loop blocks the event loop, preventing the MCP server from reading incoming messages or sending responses.

2. **Transport deadlock**: If the transport needs to read/write while the event loop is blocked by the terminal polling, we get a deadlock.

3. **Missing `await`**: If there's a code path where we forget to `await` something, we'd get a coroutine object instead of the result, and the actual work would never happen.

## The Solution (That Wasn't Needed)

The fix would be to make the terminal tool truly async:

```python
@mcp.tool
async def terminal(...) -> str:
    term = get_terminal()
    result = await asyncio.to_thread(term.execute, ...)
    return output
```

Or better, rewrite the polling loop to use async primitives:

```python
async def _execute_command(self, command, timeout):
    while True:
        output = await self._read_screen_async()
        if self._is_complete(output):
            break
        await asyncio.sleep(POLL_INTERVAL)
```

## The Actual Resolution

Upon testing with `crow-acp/scripts/client.py`, the terminal tool worked fine. The hanging was either:
- A transient issue during development
- Related to how the previous calling code handled async
- A fluke of the specific testing environment

## Lessons Learned

1. **Always verify reproducibility** before deep investigation
2. **Synchronous blocking in async functions** is a real concern for long-running operations
3. **FastMCP handles async tools correctly** - the issue was elsewhere
4. **The `asyncio.to_thread()` pattern** is valuable for wrapping synchronous code in async contexts

## Future Considerations

If the terminal tool does hang again, consider:
1. Using `asyncio.to_thread()` to run the synchronous polling in a thread pool
2. Converting the polling loop to use `asyncio.sleep()` and async I/O
3. Adding timeout handling at the MCP client level as a safety net

---

*Written after investigating a suspected async issue that turned out to be non-reproducible. The thought process remains valuable for future async debugging.*
