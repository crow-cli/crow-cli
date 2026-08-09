"""Terminal MCP tool for Crow."""

import os
from logging import getLogger

from crow_mcp.server.main import mcp

from .session import TerminalSession

logger = getLogger(__name__)

# Global terminal instance
_terminal: TerminalSession | None = None


def get_terminal() -> TerminalSession:
    """Get or create the global terminal instance."""
    global _terminal
    if _terminal is None or _terminal.closed:
        work_dir = os.getcwd()
        logger.info(f"Creating new terminal session in {work_dir}")
        _terminal = TerminalSession(
            work_dir=work_dir,
            no_change_timeout_seconds=30,
        )
        _terminal.initialize()
    return _terminal


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
    try:
        # Validate parameters
        if reset and is_input:
            return "Error: Cannot use reset=True with is_input=True"

        # Handle reset
        if reset:
            global _terminal
            if _terminal:
                old_work_dir = _terminal.work_dir
                _terminal.close()
                _terminal = None

            # Create fresh terminal
            term = get_terminal()

            if not command.strip():
                return "Terminal reset successfully. All previous state lost."

        # Get terminal instance
        term = get_terminal()

        # Execute command
        result = term.execute(
            command=command,
            is_input=is_input,
            timeout=timeout,
        )

        # Format output
        output = result["output"]

        if result.get("working_dir"):
            output += f"\n[Current working directory: {result['working_dir']}]"

        if result.get("py_interpreter"):
            output += f"\n[Python interpreter: {result['py_interpreter']}]"

        exit_code = result.get("exit_code", 0)
        if exit_code != -1:
            if exit_code == 0:
                output += f"\n[Command completed with exit code {exit_code}]"
            else:
                output += f"\n[Command failed with exit code {exit_code}]"
        else:
            output += "\n[Process still running (soft timeout)]"

        return output

    except Exception as e:
        logger.error(f"Terminal error: {e}", exc_info=True)
        return f"Error: {e}"
