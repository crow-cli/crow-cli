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
def orchestrator_task_read() -> dict:
    """Read the orchestrator task list for the current session.

    Returns:
        Dictionary with tasks array and summary string
    """
    raise NotImplementedError(
        "Orchestration tools are executed by crow-cli via ACP ext_method. "
        "This schema is for LLM tool selection only."
    )


@mcp.tool()
def orchestrator_task_write(todos: list[dict]) -> dict:
    """Wholesale-replace the session's orchestrator task list.

    This is the orchestrator's own task tracker. It supports the same
    statuses as the worker task_write plus a special "delegated" status.

    The orchestration loop promotes the FIRST non-completed task in list
    order as the "current" task and nags the orchestrator to act on it.
    Task order matters: you control which task is current by reordering
    the list (todos are processed top-to-bottom, completed items skipped).
    If the current task is `pending` or `in_progress`, the loop nags you
    to make progress on it. If the current task is marked `delegated`, the
    loop pauses and waits for the worker to finish before nagging again.

    Practical implication: the nag keeps firing as long as the first
    non-completed task is NOT `delegated` — even if a `delegated` task
    exists further down the list. So while waiting on a delegated task,
    reorder so the `delegated` task is the first non-completed task (move
    it ahead of any `in_progress`/`pending` items), or the loop will keep
    nagging about a different task that sits ahead of it.

    Args:
        todos: Array of todo objects, each with:
            - content (required): Brief description of the task
            - status: "pending", "in_progress", "delegated", "completed",
                "failed", "cancelled"
            - priority: "high", "medium", "low"
            Pass an empty array to clear the list when all work is done.

    Returns:
        Dictionary with the updated orchestrator tasks array
    """
    raise NotImplementedError(
        "Orchestration tools are executed by crow-cli via ACP ext_method. "
        "This schema is for LLM tool selection only."
    )


@mcp.tool()
def task_send(to_session_id: str, tasks: list[dict]) -> dict:
    """Delegate a batch of tasks to another agent session.

    Populates the target session's task list, records this session as the
    caller, and kicks off the target's task loop. The loop promotes the
    first Pending task and prompts the target with it, then advances
    through the list. When the loop exits normally (all tasks done or the
    list is empty), the backend sends a canned completion message back to
    this session telling you to call
    `query_session(session_id=<worker_session_id>)` for the
    target's final summary.

    Orchestrator-only: use this to delegate work to worker agents. Workers
    do not advertise it. Load this server alongside crow-task-mcp (which
    provides send_prompt, task_read, task_write).

    Args:
        to_session_id: Session ID of the agent to receive the tasks
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
