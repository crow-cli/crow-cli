"""
Crow Task MCP - Orchestration tools for agent-to-agent communication.

This MCP server provides tools that enable agents to coordinate with each other
by sending prompts and managing tasks.

Architecture:
- Tools are defined here as schemas for the LLM
- Actual execution happens in crow-cli/tools.py via ACP ext_method calls
- The client (sidex) routes ext_method calls to sidex-acp backend
- Backend methods: _send, _task/read, _task/write, _task/send

Note: Queue operations (_queue/*) are internal client logic and NOT exposed to agents.
"""

from fastmcp import FastMCP

mcp = FastMCP("crow-task-mcp")


@mcp.tool()
def send_prompt(to_session_id: str, blocks: list[dict]) -> str:
    """Send a prompt message to another agent session.
    
    This initiates an async two-step communication:
    1. Returns immediately with status
    2. Backend prompts target session with your message
    3. Target works (react loop, tools, etc.)
    4. Target finishes (prompt response with stopReason)
    5. Backend re-prompts target: "Summarize what you did"
    6. Backend sends _send notification back to you with the summary
    
    Args:
        to_session_id: The session ID of the agent to send the message to
        blocks: Array of content blocks (text, image, etc.)
    
    Returns:
        Status message (actual response comes via _send notification)
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


@mcp.tool()
def task_send(to_session_id: str, tasks: list[dict]) -> dict:
    """Send a batch of tasks to an orchestrator session.
    
    Creates tasks in the target session and sends the first task as a prompt
    to kick off the orchestrator.
    
    Args:
        to_session_id: Session ID of the orchestrator agent
        tasks: Array of task definitions, each with "title" and optional "description"
    
    Returns:
        Dictionary with success status, task count, and target session ID
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
