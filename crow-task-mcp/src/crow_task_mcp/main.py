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
    """Send a prompt to another agent session.

    The backend prompts the target session with your message blocks and
    returns immediately. When the target finishes processing, you will
    receive a notification telling you to call
    `query_session(session_id=<target_session_id>)` to see the
    result. On error, you will also be notified.

    Args:
        to_session_id: The session ID of the agent to send the message to.
            This is a coolname-style slug, e.g.
            "accurate-amethyst-salmon-from-vega".
        blocks: Array of content blocks (text, image, etc.)

    Returns:
        Status message ("sent"); the result is delivered via a
        completion notification, then fetched via query_memory
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
def task_write(todos: list[dict]) -> dict:
    """Wholesale-replace the session's task list with a new set of todos.

    This is your working memory AND your delegation mechanism for your future
    self. Each call replaces the entire list — regenerate the full list with
    updated statuses each time (like OpenCode's TodoWrite). No CRUD actions,
    no action field.

    ## How updating works

    You always send the COMPLETE list, never a delta. To mark a task done,
    copy the whole current list and change that one task's status to
    "completed". To add a task, append it. To drop one, omit it. Every call
    generates fresh IDs internally, so never try to address a task by its ID
    across calls — just reproduce the list with the statuses you want.

    ## How the list keeps the session going

    The orchestration loop runs after each of your turns. It reads the list
    and decides what to prompt you with next:

      - If the current (in_progress) task is done, it promotes the next
        pending task and hands it to you as your new focus.
      - If the current task is NOT done at the end of a turn, you get
        NAGGED: a message lists every still-incomplete task (pending or
        in_progress) and tells you to call task_write to update statuses.
        This nag fires every turn you leave work unfinished — it is the
        loop's way of refusing to let you forget what is not done.
      - The loop only stops (and the session only ends) when there are no
        pending or in_progress tasks left — i.e. the list is empty or every
        task is completed/failed/cancelled.

    So the list is what keeps you alive and on-task: as long as there is
    unfinished work in it, the loop will keep feeding you the next thing or
    nagging you about what's left. An empty list is the only signal that the
    session is truly done.

    ## Delegate to your future self — one task per turn

    The list lets you offload a large body of work onto your future self so
    you can focus on the single task at hand. Lay out the whole plan up
    front: a long list of many tasks, one marked "in_progress" and the rest
    "pending". Then work ONLY on the in_progress task for that turn.

    Do NOT try to burn through the entire list in a single turn. Do one
    task, mark it "completed" via task_write, and end your turn. The loop
    then promotes the next pending task and hands it to you as the new
    focus — or, if you ended the turn with the current task still
    incomplete, it nags you with the full list of unfinished work. This
    turn-by-turn cadence is by design: it keeps each turn focused, keeps
    context manageable, and lets the orchestration layer track real
    progress instead of one giant turn. Let the nag/advance fire between
    tasks; that is the mechanism doing its job.

    ## Clearing the list when done

    When a body of work is finished — all tasks are completed/failed/
    cancelled and there is nothing left — write an empty list to clear it:

        task_write(todos=[])

    An empty list tells the orchestration layer the session is done. The
    task loop exits, and if this session was delegated to via _task/send,
    the caller is notified to pick up results. Completed tasks left sitting
    in the list are noise — they make it harder to see what's pending and
    they keep the loop alive when it should have exited. Don't accumulate
    history; clear the list when the work is done.

    Args:
        todos: Array of todo objects, each with:
            - content (required): Brief description of the task
            - status: "pending", "in_progress", "completed", "failed", "cancelled"
            - priority: "high", "medium", "low"
            Pass an empty array to clear the list when all work is done.

    Returns:
        Dictionary with the updated tasks array
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
