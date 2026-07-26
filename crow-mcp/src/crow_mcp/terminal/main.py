"""Terminal MCP tool for Crow."""

from crow_mcp.server.main import mcp



@mcp.tool
async def terminal(
    command: str,
    is_input: bool = False,
    timeout: float | None = None,
    reset: bool = False,
) -> str:
    """Execute a bash command in a shell session.

    IMPORTANT: Each call starts a FRESH shell at the original working directory.
    Working directory, environment variables, and virtual environments do NOT
    persist between calls. Always chain commands with && or ; in a single call.

    Args:
        command: The bash command to execute. Can be:
            - Regular command: "npm install"
            - Empty string "": Check on running process
            - Special keys: "C-c" (Ctrl+C), "C-z" (Ctrl+Z), "C-d" (Ctrl+D)
        is_input: If True, send command as STDIN to running process.
                  If False (default), execute as new command.
        timeout: Max seconds to wait. If omitted, uses soft timeout
                 (pauses after 30s of no output and asks to continue).
        reset: If True, kill terminal and start fresh. Use if you think
               the terminal tool is broken for the session. Cannot use with is_input.

    Returns:
        Command output with metadata (exit code, working directory, etc.)

    Examples:
        # Basic command
        terminal("ls -la")

        # WRONG - directory change does NOT persist
        terminal("cd /tmp")
        terminal("pwd")  # Shows ORIGINAL directory, NOT /tmp

        # CORRECT - chain commands in one call
        terminal("cd /tmp && pwd")  # Shows /tmp

        # Set environment variable and use it (same call)
        terminal("export MY_VAR=hello && echo $MY_VAR")

        # Activate venv and run command (same call)
        terminal("source .venv/bin/activate && which python")

        # Long-running command with timeout
        terminal("npm install", timeout=120)

        # Interrupt running command
        terminal("C-c")

        # Reset terminal
        terminal("", reset=True)
    """
    raise NotImplementedError(
        "Terminal tool is executed by crow-cli via the client-side terminal. "
        "This schema is for LLM tool selection only."
    )