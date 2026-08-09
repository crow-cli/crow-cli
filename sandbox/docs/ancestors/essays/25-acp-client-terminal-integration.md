# ACP Client Terminal Integration

*How to use the ACP client's terminal capability to stream live command output in the client UI.*

---

## 1. Context and Motivation

We want to make our ACP agent tools return rich, typed content that the client can render beautifully:

- **Terminal commands** → Live streaming terminal in client UI
- **File edits** → Diff highlighting with file locations

This essay documents our progress on the **terminal** piece.

---

## 2. The Discovery: ACP Client Terminals

The key insight came from studying `refs/kimi-cli/src/kimi_cli/acp/tools.py`:

**The ACP client can provide terminal capabilities.** When the agent creates a terminal via the ACP connection, the client (Zed, etc.) renders a **live terminal** in the UI.

This means:
- No backend PTY needed
- Output streams live in the client
- User sees real-time command execution

---

## 3. The Pattern from kimi-cli

```python
# 1. Create terminal via ACP connection
terminal = await self._acp_conn.create_terminal(
    command=params.command,
    session_id=self._acp_session_id,
    output_byte_limit=builder.max_chars,
)

# 2. Send tool call update with TerminalToolCallContent
await self._acp_conn.session_update(
    session_id=self._acp_session_id,
    update=acp.schema.ToolCallProgress(
        session_update="tool_call_update",
        tool_call_id=acp_tool_call_id,
        status="in_progress",
        content=[
            acp.schema.TerminalToolCallContent(
                type="terminal",
                terminal_id=terminal.id,
            )
        ],
    ),
)

# 3. Wait for exit ON THE TERMINAL HANDLE
exit_status = await terminal.wait_for_exit()

# 4. Get output
output_response = await terminal.current_output()

# 5. Release terminal
await terminal.release()
```

**Critical detail:** They call `terminal.wait_for_exit()`, not `conn.wait_for_terminal_exit(terminal_id)`.

---

## 4. The TerminalHandle Object

The `create_terminal()` call returns a `TerminalHandle` object (not just an ID). This handle has methods:

| Method | Purpose |
|--------|---------|
| `wait_for_exit()` | Wait for command to complete |
| `current_output()` | Get current output buffer |
| `kill()` | Kill the running command |
| `release()` | Release terminal resources |

The `TerminalHandle` wraps the terminal ID and session context, so you don't need to pass them separately.

---

## 5. Our Implementation Attempt

We created `sandbox/crow-acp-learning/terminal_agent.py`:

```python
class TerminalAgent(Agent):
    async def prompt(self, prompt, session_id, **kwargs):
        # Extract command from prompt
        command = " ".join(text_list).strip()
        
        # Generate tool call ID
        tool_call_id = f"{turn_id}/terminal"
        
        # Send tool call start
        await self._conn.session_update(
            session_id=session_id,
            update=ToolCallStart(
                session_update="tool_call",
                tool_call_id=tool_call_id,
                title=f"terminal: {command}",
                kind="execute",
                status="pending",
            ),
        )
        
        # Create terminal
        terminal_response = await self._conn.create_terminal(
            command=command,
            session_id=session_id,
            cwd=cwd,
            output_byte_limit=100000,
        )
        terminal_id = terminal_response.terminal_id
        
        # Send terminal content for live display
        await self._conn.session_update(
            session_id=session_id,
            update=ToolCallProgress(
                session_update="tool_call_update",
                tool_call_id=tool_call_id,
                status="in_progress",
                content=[
                    TerminalToolCallContent(
                        type="terminal",
                        terminalId=terminal_id,
                    )
                ],
            ),
        )
        
        # Wait for exit - THIS IS WHERE WE GOT STUCK
        # ...
```

---

## 6. The Bug We Hit

When we called `conn.wait_for_terminal_exit(terminal_id=terminal_id)`, we got:

```
Error: AgentSideConnection.wait_for_terminal_exit() missing 1 required positional argument: 'session_id'
```

The fix: **Use the TerminalHandle object returned by create_terminal(), not the raw connection method.**

The kimi-cli code shows:

```python
terminal = await self._acp_conn.create_terminal(...)
# terminal is a TerminalHandle

exit_status = await terminal.wait_for_exit()  # No session_id needed!
```

---

## 7. What We Need to Fix

Our current implementation gets the `terminal_id` from the response but doesn't use the handle properly:

```python
# WRONG (what we did)
terminal_response = await self._conn.create_terminal(...)
terminal_id = terminal_response.terminal_id
exit_response = await self._conn.wait_for_terminal_exit(terminal_id=terminal_id)  # ERROR

# RIGHT (what kimi-cli does)
terminal = await self._acp_conn.create_terminal(...)  # Returns TerminalHandle
exit_status = await terminal.wait_for_exit()  # Uses handle method
```

---

## 8. Session Context Tracking

Another pattern from kimi-cli: tracking tool call IDs with context variables:

```python
# Context var for turn ID
_current_turn_id: ContextVar[str | None] = ContextVar("turn_id", default=None)

# In prompt()
turn_id = str(uuid.uuid4())
token = _current_turn_id.set(turn_id)

# Build ACP tool call ID as "{turn_id}/{llm_tool_call_id}"
def get_acp_tool_call_id(llm_tool_call_id: str) -> str:
    turn_id = _current_turn_id.get()
    return f"{turn_id}/{llm_tool_call_id}"
```

This ensures unique tool call IDs per turn, even if the LLM reuses IDs.

---

## 9. Progress Summary

### Completed
1. ✅ Research on llms.txt and Agent Skills (essay written)
2. ✅ Explored ~/.crow/crow.db to understand session history
3. ✅ Compared search patterns - first agent to use parallel queries extensively
4. ✅ Created plan for ACP tool enhancements (`docs/plans/acp-tool-enhancements.md`)
5. ✅ Started `terminal_agent.py` in sandbox

### In Progress
6. 🔄 Fix terminal_agent.py to use TerminalHandle correctly

### Next Steps
7. Test terminal_agent.py with a real ACP client (Zed)
8. Port the pattern to `crow-acp/src/crow_acp/agent.py`
9. Add file editor diff support

---

## 10. Key Files

| File | Purpose |
|------|---------|
| `refs/kimi-cli/src/kimi_cli/acp/tools.py` | Reference implementation of Terminal wrapper |
| `refs/kimi-cli/src/kimi_cli/acp/session.py` | Tool call ID context tracking |
| `sandbox/crow-acp-learning/terminal_agent.py` | Our learning implementation |
| `docs/plans/acp-tool-enhancements.md` | Full implementation plan |
| `crow-acp/src/crow_acp/agent.py` | Target for final integration |

---

## 11. The Fix

Update `terminal_agent.py` to use the TerminalHandle:

```python
# In prompt():
terminal = None
try:
    # create_terminal returns TerminalHandle (or response with handle)
    result = await self._conn.create_terminal(
        command=command,
        session_id=session_id,
        cwd=cwd,
        output_byte_limit=100000,
    )
    
    # Check if result is a handle or response with handle
    if hasattr(result, 'wait_for_exit'):
        terminal = result
    else:
        # It's a response, get the handle or ID
        terminal_id = result.terminal_id
        # Need to get handle from somewhere...
    
    # Use handle methods
    if terminal:
        exit_status = await terminal.wait_for_exit()
        output_response = await terminal.current_output()
finally:
    if terminal:
        await terminal.release()
```

---

## 12. Conclusion

The ACP client terminal feature is powerful - it lets the client handle terminal rendering while the agent just coordinates. The key is using the `TerminalHandle` object's methods rather than raw connection methods.

Next session: fix `terminal_agent.py`, verify it works with Zed, then port to the main `crow-acp` agent.
