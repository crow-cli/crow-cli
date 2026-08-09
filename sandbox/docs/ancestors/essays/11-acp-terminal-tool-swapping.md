# 11. The Critical Importance of ACP Terminal Tool Swapping

## 1. The Problem: Non-Persistent Terminals Suck

When building an ACP-native agent, there's a fundamental architectural decision that determines whether your agent feels like a modern interactive tool or a frustrating, broken experience:

**Do you use the client's terminal, or do you spawn your own subprocess?**

The answer is not just important—it's **existential**. If you spawn your own subprocess for shell commands, you get:

- **Fresh shell every time** - No persistent state between commands
- **No PTY support** - No proper terminal features (colors, prompts, etc.)
- **Broken interactive commands** - `vim`, `top`, `htop`, `ssh`, etc. all fail
- **No job control** - Can't use `Ctrl+Z`, `fg`, `bg`, etc.
- **No tab completion** - Users hate typing full paths
- **No history** - Can't use up arrow to repeat commands
- **No terminal size awareness** - Commands break in weird ways

This is the **exact problem** we saw with the old Crow agent based on OpenHands. Every time the agent ran a shell command, it spawned a fresh subprocess that died immediately. No state, no interactivity, just a one-shot command execution.

## 2. The Solution: ACP Terminal Protocol

The ACP protocol has a **terminal capability** that allows clients to provide their own terminal implementation. When the client supports it, the agent should:

1. **Detect terminal capability** - Check `client_capabilities.terminal`
2. **Swap out local shell tool** - Replace your subprocess-based shell tool
3. **Use ACP terminal tool** - Create and manage terminals via ACP protocol
4. **Stream output in real-time** - Use `ToolCallProgress` with `TerminalToolCallContent`

This is exactly what Kimi-cli does (see `kimi_cli/acp/tools.py`), and it's what your agent **must** do.

## 3. How Kimi-cli Does It

Kimi-cli has a beautiful pattern for terminal tool swapping:

```python
def replace_tools(
    client_capabilities: acp.schema.ClientCapabilities,
    acp_conn: acp.Client,
    acp_session_id: str,
    toolset: KimiToolset,
    runtime: Runtime,
) -> None:
    current_kaos = get_current_kaos().name
    if current_kaos not in (local_kaos.name, "acp"):
        return

    if client_capabilities.terminal and (shell_tool := toolset.find(Shell)):
        toolset.add(
            Terminal(
                shell_tool,
                acp_conn,
                acp_session_id,
                runtime.approval,
            )
        )
```

The key insight: **The `Terminal` tool wraps the original `Shell` tool**. It:

1. **Hides output** via `HideOutputDisplayBlock()` - The client shows the terminal
2. **Creates ACP terminal** via `acp_conn.create_terminal()`
3. **Streams progress** via `ToolCallProgress` with `TerminalToolCallContent`
4. **Waits for exit** via `terminal.wait_for_exit()`
5. **Returns result** - But the user already saw it in the terminal

## 4. Why This Matters for Crow

Your new Crow Agent SDK in `/home/thomas/src/projects/mcp-testing/src/crow/agent/` currently has **no terminal tool swapping**. This means:

- If you're running in Zed (or any ACP client), shell commands will **suck**
- Users will see broken, non-interactive terminal output
- Interactive commands will fail or hang
- The agent will feel like a 2020-era tool instead of a modern agent

This is **not acceptable**. The whole point of ACP is to give clients control over the UI. If you ignore the terminal capability, you're saying "I know better than the client how to show terminal output" - which is arrogant and wrong.

## 5. Implementation Plan for Crow

Here's what needs to happen:

### Step 1: Add Terminal Tool to MCP

Your MCP server (`crow-mcp-server/main.py`) currently has a `shell` tool that uses `subprocess.run()`. This is fine for local use, but **must be replaced** when ACP terminal is available.

### Step 2: Detect Client Capability

In your agent's `initialize` or `new_session` handler:

```python
async def new_session(
    self, 
    cwd: str, 
    mcp_servers: list[MCPServer], 
    **kwargs: Any
) -> acp.NewSessionResponse:
    # ... existing code ...
    
    # Check if client supports terminal
    if self.client_capabilities and self.client_capabilities.terminal:
        self.use_acp_terminal = True
    else:
        self.use_acp_terminal = False
    
    # ... rest of session creation ...
```

### Step 3: Swap Tools Based on Capability

When setting up the agent's toolset:

```python
def setup_tools(self):
    tools = []
    
    if self.use_acp_terminal:
        # Add ACP terminal tool instead of subprocess shell
        tools.append(ACPTerminalTool(
            shell_command=self.shell_command,
            approval=self.approval,
            acp_conn=self.acp_conn,
            session_id=self.session_id,
        ))
    else:
        # Use subprocess-based shell for local/non-ACP clients
        tools.append(SubprocessShellTool(
            shell_command=self.shell_command,
        ))
    
    return tools
```

### Step 4: Implement ACP Terminal Tool

```python
class ACPTerminalTool:
    def __init__(
        self,
        shell_command: str,
        approval: Approval,
        acp_conn: acp.Client,
        session_id: str,
    ):
        self.shell_command = shell_command
        self.approval = approval
        self.acp_conn = acp_conn
        self.session_id = session_id
    
    async def __call__(self, command: str, timeout: int = 60) -> str:
        # Request approval
        if not await self.approval.request("Terminal", "run command", command):
            return "Command rejected by user"
        
        # Create ACP terminal
        terminal = await self.acp_conn.create_terminal(
            command=command,
            session_id=self.session_id,
        )
        
        # Stream progress
        await self.acp_conn.session_update(
            session_id=self.session_id,
            update=acp.schema.ToolCallProgress(
                tool_call_id=get_current_tool_call_id(),
                status="in_progress",
                content=[
                    acp.schema.TerminalToolCallContent(
                        terminal_id=terminal.id,
                    )
                ],
            ),
        )
        
        # Wait for exit
        try:
            async with asyncio.timeout(timeout):
                exit_status = await terminal.wait_for_exit()
        except TimeoutError:
            await terminal.kill()
            return f"Command killed by timeout ({timeout}s)"
        
        # Get output
        output_response = await terminal.current_output()
        
        # Release terminal
        await terminal.release()
        
        # Return result
        if exit_status.exit_code == 0:
            return f"Command executed successfully:\n{output_response.output}"
        else:
            return f"Command failed with exit code {exit_status.exit_code}:\n{output_response.output}"
```

## 6. The Bigger Picture: Client Control

This isn't just about terminals. This is about **trusting the client**:

- **File operations** - Let the client show file diffs, not your agent spamming content
- **Terminal operations** - Let the client show interactive terminals, not your agent spawning subprocesses
- **Prompt operations** - Let the client handle prompts, not your agent guessing
- **Session operations** - Let the client manage sessions, not your agent reinventing the wheel

The ACP protocol is a **contract** between client and agent. The client says "I can do X, Y, Z" and the agent says "Great! I'll use your X, Y, Z instead of doing it myself."

**Ignoring the terminal capability breaks this contract.** It says "I don't trust you to provide a terminal, so I'll do it myself" - which is the opposite of what ACP is about.

## 7. Real-World Impact

When you get this right:

- **Zed users** get a proper terminal in Zed's terminal panel
- **VS Code users** get a proper terminal in VS Code's terminal panel
- **Custom client users** get a proper terminal in their custom terminal panel
- **Interactive commands** work (`vim`, `ssh`, `top`, etc.)
- **Job control** works (`Ctrl+Z`, `fg`, `bg`)
- **Tab completion** works
- **History** works

When you get this wrong:

- **Everything sucks**
- **Users hate your agent**
- **Agent feels broken**
- **Agent feels like a toy**

## 8. Conclusion

**Terminal tool swapping is not optional.** It's a **requirement** for any ACP-native agent that wants to provide a good user experience.

The pattern is clear (see Kimi-cli), the implementation is straightforward, and the payoff is massive.

**Do it.** Your users will thank you.
