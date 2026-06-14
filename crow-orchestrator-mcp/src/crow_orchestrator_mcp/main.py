"""
Crow Orchestrator MCP - Send batches of tasks to agent sessions.

This MCP server provides the task_send tool for orchestrators to delegate
work to other agents. It's separate from crow-task-mcp because task_send
is only needed by orchestrator agents, not regular worker agents.

Architecture:
- Tool schema defined here for the LLM
- Actual execution happens in crow-cli/tools.py via ACP ext_method call
- The client (sidex) routes ext_method calls to sidex-acp backend
- Backend method: _task/send
"""

from fastmcp import FastMCP

mcp = FastMCP("crow-orchestrator-mcp")


@mcp.tool()
def task_send(to_session_id: str, tasks: list[dict]) -> dict:
    """Send a batch of tasks to an orchestrator session.
    
    Creates tasks in the target session and sends the first task as a prompt
    to kick off the orchestrator. Use this to delegate work to worker agents.
    
    Args:
        to_session_id: Session ID of the orchestrator agent to receive tasks
        tasks: Array of task definitions, each with:
            - title (required): Human-readable task description
            - description (optional): Detailed instructions for the task
    
    Returns:
        Dictionary with:
            - success: Whether the operation succeeded
            - taskCount: Number of tasks created
            - toSessionId: Target session ID
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
