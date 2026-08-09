# ACP Terminal Architecture

**Date**: Current Session  
**Status**: UNDERSTANDING - How ACP Handles Terminals

---

## The Discovery

The MCP server doesn't have a terminal tool because **ACP CLIENTS PROVIDE THE TERMINAL**.

This is the correct architecture. Here's how it works:

---

## The Protocol Flow

### 1. Agent Requests Terminal from Client

```python
# Agent (crow-ai) code
class Agent(ACPAgent):
    async def prompt(self, prompt, session_id, **kwargs):
        # Agent wants to run a command
        # It asks the CLIENT (Zed/VSCode) for a terminal
        
        terminal = await self._conn.create_terminal(
            command="bash",
            session_id=session_id,
            args=["-c", "npm test"],
            cwd="/workspace"
        )
        
        # Client returns terminal_id
        terminal_id = terminal.terminal_id
```

### 2. Client (Zed/VSCode) Provides Terminal

```python
# Client (Zed) implements:
class ZedClient(Client):
    async def create_terminal(self, command, session_id, ...):
        # Zed creates an actual terminal in its UI
        terminal_id = self.terminal_manager.spawn(command, ...)
        
        # Returns ID to agent
        return CreateTerminalResponse(terminal_id=terminal_id)
```

### 3. Agent References Terminal in Tool Response

```python
# Agent sends tool response back to client
from acp import tool_terminal_ref

# Tell client to display this terminal
terminal_content = tool_terminal_ref(terminal_id)

# This goes in the tool call response
await self._conn.send_tool_result(
    tool_call_id="...",
    content=terminal_content  # type: TerminalToolCallContent
)
```

### 4. Client Displays Terminal UI

```python
# Client (Zed) receives tool result with terminal ref
if content.type == "terminal":
    # Show the terminal that was already created
    self.terminal_manager.show(content.terminal_id)
```

---

## The Architecture

```
┌─────────────┐
│   Zed/IDE   │ ← Has ACTUAL terminal emulator (PTY, rendering, etc.)
│  (Client)   │
└──────┬──────┘
       │ ACP Protocol
       │
       ↓
┌─────────────┐
│  crow-ai    │ ← Requests terminals via create_terminal()
│   (Agent)   │ ← References terminals via tool_terminal_ref()
└──────┬──────┘
       │
       ↓
┌─────────────┐
│  LLM/Tools  │ ← Agent decides when to use terminal
└─────────────┘
```

**Key insight**: The agent doesn't IMPLEMENT terminals. It REQUESTS them from the client.

---

## Why This is Better

### 1. **Separation of Concerns**
- Agent: Decides WHAT commands to run
- Client: Decides HOW to display/run terminals

### 2. **Platform Native**
- Zed: Uses its blazing-fast terminal (Alacritty-based)
- VSCode: Uses its integrated terminal
- Web client: Uses xterm.js

Each client uses its BEST terminal implementation.

### 3. **Security & Permissions**
- Client controls terminal creation
- Can ask user for permission
- Can sandbox/limit terminal access

### 4. **No Duplicate Implementation**
- Don't need MCP terminal tool
- Don't need terminal emulator in agent
- Don't need PTY handling in Python

---

## How Crow Uses This

### The Pattern in crow-core

```python
# crow-core/agent.py
class Agent(ACPAgent):
    _conn: Client  # ACP client connection
    
    async def _execute_terminal_tool(self, command: str, cwd: str = None):
        """
        Execute a terminal command using ACP client's terminal.
        
        This is NOT an MCP tool - it's a built-in ACP capability.
        """
        # Request terminal from client
        terminal = await self._conn.create_terminal(
            command="/bin/bash",
            session_id=self._current_session_id,
            args=["-c", command],
            cwd=cwd or self._cwd
        )
        
        # Wait for command to complete
        result = await self._conn.wait_for_terminal_exit(
            terminal_id=terminal.terminal_id,
            session_id=self._current_session_id
        )
        
        # Get output
        output = await self._conn.terminal_output(
            terminal_id=terminal.terminal_id,
            session_id=self._current_session_id
        )
        
        # Return as tool result
        return tool_terminal_ref(terminal.terminal_id)
```

### The Tool Definition

```python
# When listing tools to LLM, we include terminal as a "virtual" tool:
{
    "type": "function",
    "function": {
        "name": "terminal",
        "description": "Execute a shell command",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "cwd": {"type": "string"}
            },
            "required": ["command"]
        }
    }
}
```

### The Tool Dispatch

```python
async def _execute_tool_call(self, tool_name: str, args: dict):
    """Dispatch tool calls to appropriate handlers"""
    
    if tool_name == "terminal":
        # Use ACP terminal (NOT MCP)
        return await self._execute_terminal_tool(
            command=args["command"],
            cwd=args.get("cwd")
        )
    else:
        # Use MCP tools
        return await self._mcp_client.call_tool(tool_name, args)
```

---

## The Priority System (From Essay 10)

This implements the "Priority: Use ACP terminal over MCP terminal" insight:

```python
# Agent configuration
class Config:
    use_acp_terminal: bool = True  # Default to ACP terminal
    
    # If client doesn't support terminals, fall back to MCP
    fallback_to_mcp_terminal: bool = True
```

**Why ACP terminal is better:**
1. ✅ Native UI in client (faster, better rendering)
2. ✅ Client controls permissions
3. ✅ No PTY handling in Python
4. ✅ Works across all clients (Zed, VSCode, web)
5. ✅ Client can provide better UX (tabs, splits, themes)

---

## Migration Path

### Current State
- MCP server has: file_editor, web_search, web_fetch
- NO terminal tool in MCP

### Future State
- MCP server has: file_editor, web_search, web_fetch
- Agent has built-in: terminal (via ACP)

### How to Test

```python
# Check if client supports terminals
if hasattr(self._conn, 'create_terminal'):
    # Use ACP terminal
    terminal = await self._conn.create_terminal(...)
else:
    # Fallback or error
    raise ValueError("Client doesn't support terminals")
```

---

## Implementation in crow-core

```python
# crow-core/agent.py additions

class Agent(ACPAgent):
    def __init__(self):
        # ... existing init ...
        self._current_session_id: str | None = None
        self._cwd: str | None = None
    
    async def new_session(self, cwd, mcp_servers, **kwargs):
        # ... existing code ...
        self._current_session_id = session.session_id
        self._cwd = cwd
        # ... rest of method ...
    
    async def _get_tool_definitions(self):
        """Get tool definitions including built-in ACP tools"""
        # Get MCP tools
        mcp_tools = await get_tools(self._mcp_client)
        
        # Add ACP terminal tool (virtual tool, handled specially)
        terminal_tool = {
            "type": "function",
            "function": {
                "name": "terminal",
                "description": "Execute a shell command in the workspace",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to execute"
                        },
                        "cwd": {
                            "type": "string",
                            "description": "Working directory (defaults to session cwd)"
                        }
                    },
                    "required": ["command"]
                }
            }
        }
        
        return mcp_tools + [terminal_tool]
    
    async def _execute_tool_call(self, tool_name: str, args: dict):
        """Execute a tool call - dispatches to MCP or ACP"""
        
        if tool_name == "terminal":
            # ACP terminal (not MCP)
            if not hasattr(self._conn, 'create_terminal'):
                raise ValueError("Client doesn't support ACP terminals")
            
            terminal = await self._conn.create_terminal(
                command="/bin/bash",
                session_id=self._current_session_id,
                args=["-c", args["command"]],
                cwd=args.get("cwd", self._cwd)
            )
            
            # Wait for completion
            await self._conn.wait_for_terminal_exit(
                terminal_id=terminal.terminal_id,
                session_id=self._current_session_id
            )
            
            # Reference terminal in response
            return tool_terminal_ref(terminal.terminal_id)
        
        else:
            # MCP tool
            return await self._mcp_client.call_tool(tool_name, args)
```

---

## The Beautiful Architecture

```
Agent Toolkit:
├── MCP Tools (external, pluggable)
│   ├── file_editor (MCP)
│   ├── web_search (MCP)
│   └── web_fetch (MCP)
├── ACP Tools (built-in, client-provided)
│   └── terminal (ACP) ← Client implements, agent requests
└── Future ACP Tools
    ├── read_text_file (ACP) ← Maybe client provides this too?
    └── write_text_file (ACP)

The pattern:
- Complex tools → MCP (file_editor with diffs, web search, etc.)
- Platform-native tools → ACP (terminal, maybe file I/O)
```

---

## Conclusion

**The agent consolidated correctly!** The terminal should NOT be an MCP tool because:

1. ACP already defines terminal protocol
2. Clients (Zed/VSCode) provide native terminal implementations
3. Agent just requests terminals via `client.create_terminal()`
4. Agent references them via `tool_terminal_ref()`

This is the **"Priority: Use ACP terminal over MCP terminal"** principle in action.

**No code needed in crow-mcp-server for terminals.** The terminal support goes in crow-core as a built-in tool that uses ACP client capabilities.

---

## Real-World Implementation: kimi-cli

Looking at `refs/kimi-cli/src/kimi_cli/acp/tools.py`, we see the EXACT pattern for ACP terminal integration.

### The Tool Replacement Pattern

kimi-cli has an existing `Shell` tool, and **replaces** it with an ACP `Terminal` wrapper when the client supports it:

```python
def replace_tools(
    client_capabilities: acp.schema.ClientCapabilities,
    acp_conn: acp.Client,
    acp_session_id: str,
    toolset: KimiToolset,
    runtime: Runtime,
) -> None:
    # Only replace when running locally or under ACP
    current_kaos = get_current_kaos().name
    if current_kaos not in (local_kaos.name, "acp"):
        return
    
    # Check if client supports terminals
    if client_capabilities.terminal and (shell_tool := toolset.find(Shell)):
        # Replace the Shell tool with the ACP Terminal tool
        toolset.add(
            Terminal(
                shell_tool,      # ← Existing Shell tool
                acp_conn,
                acp_session_id,
                runtime.approval,
            )
        )
```

**Key insight**: The `Terminal` wrapper inherits `name`, `description`, and `params` from the existing `Shell` tool. This makes the replacement transparent to the LLM - it sees the same tool definition.

### The Terminal Wrapper Implementation

```python
class Terminal(CallableTool2[ShellParams]):
    def __init__(
        self,
        shell_tool: Shell,          # ← Existing tool to replace
        acp_conn: acp.Client,
        acp_session_id: str,
        approval: Approval,
    ):
        # Inherit from Shell tool (transparent replacement)
        super().__init__(
            shell_tool.name,
            shell_tool.description,
            shell_tool.params
        )
        self._acp_conn = acp_conn
        self._acp_session_id = acp_session_id
        self._approval = approval
    
    async def __call__(self, params: ShellParams) -> ToolReturnValue:
        builder = ToolResultBuilder()
        # Hide tool output (terminal streams directly to user via ACP)
        builder.display(HideOutputDisplayBlock())
        
        if not params.command:
            return builder.error("Command cannot be empty.")
        
        # Request user approval
        if not await self._approval.request(
            self.name,
            "run shell command",
            f"Run command `{params.command}`",
        ):
            return ToolRejectedError()
        
        timeout_seconds = float(params.timeout)
        terminal: acp.TerminalHandle | None = None
        
        try:
            # Create ACP terminal
            term = await self._acp_conn.create_terminal(
                command=params.command,
                session_id=self._acp_session_id,
                output_byte_limit=builder.max_chars,
            )
            terminal = term
            
            # Stream terminal progress to client
            acp_tool_call_id = get_current_acp_tool_call_id_or_none()
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
            
            # Wait for exit with timeout
            try:
                async with asyncio.timeout(timeout_seconds):
                    exit_status = await terminal.wait_for_exit()
            except TimeoutError:
                await terminal.kill()
            
            # Get output
            output_response = await terminal.current_output()
            builder.write(output_response.output)
            
            # Handle exit status
            exit_code = exit_status.exit_code if exit_status else None
            exit_signal = exit_status.signal if exit_status else None
            
            if exit_signal:
                return builder.error(f"Command terminated by signal: {exit_signal}")
            if exit_code not in (None, 0):
                return builder.error(f"Command failed with exit code: {exit_code}")
            return builder.ok("Command executed successfully.")
            
        finally:
            if terminal is not None:
                await terminal.release()
```

### The TerminalHandle API

kimi-cli shows that `create_terminal()` returns a `TerminalHandle` object with methods:

```python
# Create terminal (returns handle, not just ID)
terminal = await self._acp_conn.create_terminal(
    command=params.command,
    session_id=self._acp_session_id,
    output_byte_limit=builder.max_chars,
)

# TerminalHandle methods:
terminal.id                     # Terminal ID
await terminal.wait_for_exit()  # Wait for command to complete
await terminal.current_output() # Get current output
await terminal.kill()           # Kill the terminal
await terminal.release()        # Release resources (cleanup!)
```

**This is richer than the basic ACP schema suggests!** The `TerminalHandle` is a higher-level abstraction.

### Key Patterns from kimi-cli

1. **HideOutputDisplayBlock**: Prevents double-display since terminal streams directly to user via ACP
2. **Approval System**: Ask user before running commands
3. **Timeout Handling**: Use `asyncio.timeout()` with `terminal.kill()` on timeout
4. **Exit Status Handling**: Check both `exit_code` and `signal`
5. **Resource Cleanup**: Always `release()` terminal in `finally` block
6. **Tool Replacement**: Transparently replace MCP/Shell tools with ACP versions when supported

### The Correct Pattern for Crow

```python
# crow-core/agent.py
class Agent(ACPAgent):
    async def _setup_tools(self, session_id: str):
        """Setup tools, replacing with ACP versions when supported"""
        
        # Get MCP tools
        mcp_tools = await get_tools(self._mcp_client)
        
        # Check if client supports ACP terminals
        # (This would come from client_capabilities in initialize())
        if self._client_capabilities.terminal:
            # If we had a terminal MCP tool, we'd replace it here
            # For now, we just add ACP terminal as a new tool
            pass
        
        return mcp_tools
    
    async def _execute_terminal_tool(self, command: str, timeout: float = 30.0):
        """Execute terminal command using ACP"""
        
        # Create terminal (returns TerminalHandle)
        terminal = await self._conn.create_terminal(
            command=command,
            session_id=self._current_session_id,
            output_byte_limit=100000,  # 100KB limit
        )
        
        try:
            # Stream progress to client
            await self._conn.session_update(
                session_id=self._current_session_id,
                update=acp.schema.ToolCallProgress(
                    session_update="tool_call_update",
                    tool_call_id=self._current_tool_call_id,
                    status="in_progress",
                    content=[
                        acp.schema.TerminalToolCallContent(
                            type="terminal",
                            terminal_id=terminal.id,
                        )
                    ],
                ),
            )
            
            # Wait for exit with timeout
            try:
                async with asyncio.timeout(timeout):
                    exit_status = await terminal.wait_for_exit()
            except TimeoutError:
                await terminal.kill()
                return {"error": f"Command timed out after {timeout}s"}
            
            # Get output
            output = await terminal.current_output()
            
            # Return result
            result = {
                "output": output.output,
                "exit_code": exit_status.exit_code if exit_status else None,
                "truncated": output.truncated,
            }
            
            # Return terminal reference for ACP client
            return acp.tool_terminal_ref(terminal.id)
            
        finally:
            await terminal.release()
```

### The Hide Output Pattern

Since ACP terminals stream output directly to the user, we shouldn't double-display in the tool result:

```python
# From kimi-cli
class HideOutputDisplayBlock(DisplayBlock):
    """A special DisplayBlock that indicates output should be hidden in ACP clients."""
    type: str = "acp/hide_output"

# In tool result:
builder.display(HideOutputDisplayBlock())
# This tells the ACP client "don't show tool output, terminal already streams to user"
```

For Crow, we'd return this in the tool response metadata or use a similar pattern.

---

## Summary: The Complete ACP Terminal Pattern

**Architecture:**
1. Client supports terminals → `client_capabilities.terminal == True`
2. Agent creates terminal → `terminal = await conn.create_terminal()`
3. Terminal streams output → Client displays in real-time
4. Agent waits for exit → `await terminal.wait_for_exit()`
5. Agent gets final output → `await terminal.current_output()`
6. Agent releases resources → `await terminal.release()`

**Tool Replacement Pattern:**
1. Have existing Shell/MCP terminal tool
2. Check if client supports ACP terminals
3. If yes, replace with ACP Terminal wrapper (same name/description)
4. Wrapper delegates to ACP instead of local shell

**For Crow:**
- We don't have a terminal MCP tool (correctly!)
- We add ACP terminal as a built-in tool
- We use the `TerminalHandle` API pattern from kimi-cli
- We stream progress to client via `session_update`
- We always cleanup with `terminal.release()`

---

## Resources

- **ACP Protocol Documentation**: https://agentclientprotocol.com/llms.txt
- **kimi-cli Implementation**: refs/kimi-cli/src/kimi_cli/acp/tools.py
- **ACP Python SDK**: refs/python-sdk/

---

**Next Steps:**
1. Implement `_execute_terminal_tool()` using `TerminalHandle` API
2. Add terminal to tool definitions (with proper schema)
3. Add `HideOutputDisplayBlock` or equivalent pattern
4. Test with Zed (should show terminal in UI)
5. Implement approval system (optional but recommended)
6. Document the tool replacement pattern for other ACP tools
