"""
Crow Task MCP - Orchestration tools for agent-to-agent communication.

This MCP server provides tools that enable agents to coordinate with each other
by sending prompts and managing tasks.

Architecture:
- Tools are defined here as schemas for the LLM
- Actual execution happens in crow-cli/tools.py via ACP ext_method calls
- The client (sidex) routes ext_method calls to sidex-acp backend
- Backend methods: _send, _task/read, _task/write
- task_send (_task/send) lives in crow-orchestrator-mcp, loaded only by orchestrators

Note: Queue operations (_queue/*) are internal client logic and NOT exposed to agents.
"""

from fastmcp import FastMCP

mcp = FastMCP("crow-task-mcp")


@mcp.tool()
def send_prompt(to_session_id: str, blocks: list[dict]) -> str:
    """Send a prompt to another agent session (fire-and-forget).

    The backend prompts the target session with your message blocks and
    returns immediately. There is no summary re-prompt and no callback —
    the target works through its react loop on its own. Retrieve the
    target's response later by calling query_memory with
    session_id="<to_session_id>" and limit=1.

    Args:
        to_session_id: The session ID of the agent to send the message to
        blocks: Array of content blocks (text, image, etc.)

    Returns:
        Status message ("sent"); the actual response is fetched via query_memory
    """
    raise NotImplementedError(
        "Orchestration tools are executed by crow-cli via ACP ext_method. "
        "This schema is for LLM tool selection only."
    )


@mcp.tool()
def task_read() -> dict:
    """Read the task list for the current session.
    
    Returns:
        Dictionary with tasks array and summary string
    """
    raise NotImplementedError(
        "Orchestration tools are executed by crow-cli via ACP ext_method. "
        "This schema is for LLM tool selection only."
    )


@mcp.tool()
def task_write(
    action: str,
    title: str | None = None,
    description: str | None = None,
    task_id: str | None = None,
    status: str | None = None,
    assigned_to: str | None = None
) -> dict:
    """Create, update, or delete tasks in the session's task list.
    
    Args:
        action: One of "create", "update", or "delete"
        title: Task title (required for create)
        description: Task description (optional for create)
        task_id: Task ID (required for update/delete)
        status: Task status (optional for update): "pending", "in_progress", "completed", "failed"
        assigned_to: Session ID of assigned agent (optional for update)
    
    Returns:
        Dictionary with task object or success status
    """
    raise NotImplementedError(
        "Orchestration tools are executed by crow-cli via ACP ext_method. "
        "This schema is for LLM tool selection only."
    )


def main():
    """Entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
