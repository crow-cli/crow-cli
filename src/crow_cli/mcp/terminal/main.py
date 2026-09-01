"""Terminal MCP tool for Crow."""

import os
from logging import getLogger

from fastmcp import Context

from crow_cli.mcp.server.app import mcp

from .session import TerminalSession

logger = getLogger(__name__)

# Terminal sessions keyed by working directory: every session's shells start
# fresh in its directory, and a running process is kept per directory.
_terminals: dict[str, TerminalSession] = {}


def get_terminal(work_dir: str) -> TerminalSession:
    """Get or create the terminal session for a working directory."""
    term = _terminals.get(work_dir)
    if term is None or term.closed:
        logger.info(f"Creating new terminal session in {work_dir}")
        term = TerminalSession(
            work_dir=work_dir,
            no_change_timeout_seconds=30,
        )
        term.initialize()
        _terminals[work_dir] = term
    return term


def _work_dir_from_context(ctx: Context) -> tuple[str, str | None]:
    """The caller-injected context: cwd and session id from the call's `_meta`.

    The agent injects these (``execute_acp_terminal``) so shells run in the
    ACP session's working directory, not this server process's. The Context
    parameter is filtered out of the LLM-facing schema, so the model never
    sees — and cannot forge — either value. No meta means a bare caller:
    fall back to the server process's cwd.
    """
    meta = ctx.request_context.meta if ctx.request_context else None
    return (
        getattr(meta, "cwd", None) or os.getcwd(),
        getattr(meta, "session_id", None),
    )


@mcp.tool
async def terminal(
    ctx: Context,
    command: str,
    is_input: bool = False,
    timeout: float | None = None,
    reset: bool = False,
) -> str:
    """Execute a bash command in a shell session.

    IMPORTANT: Each call starts a FRESH shell at the session's working
    directory. Working directory changes, environment variables, and virtual
    environments do NOT persist between calls. Always chain commands with
    && or ; in a single call.

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
               the terminal tool is broken for the session. Cannot be used with is_input.

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

        # Set environment variable and run command (same call)
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
        work_dir, session_id = _work_dir_from_context(ctx)
        if session_id:
            logger.info(
                f"terminal tool: session {session_id} in {work_dir}"
            )

        # Validate parameters
        if reset and is_input:
            return "Error: Cannot use reset=True with is_input=True"

        # Handle reset
        if reset:
            term = _terminals.pop(work_dir, None)
            if term:
                term.close()

            if not command.strip():
                return "Terminal reset successfully. All previous state lost."

        # Get terminal instance
        term = get_terminal(work_dir)

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
