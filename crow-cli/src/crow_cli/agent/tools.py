"""
Tool execution utilities.

Intercepts terminal commands to enforce --project usage for 'uv' in ephemeral environments.
"""

import asyncio
import json
from contextlib import suppress
from logging import Logger
from typing import Any

from acp import (
    image_block,
    text_block,
)


from acp.helpers import (
    start_edit_tool_call,
    start_read_tool_call,
    tool_content,
    tool_diff_content,
    update_tool_call,
)
from acp.interfaces import Client
from acp.schema import (
    TerminalToolCallContent,
    ToolCallProgress,
    ToolCallStart,
    ToolKind,
)
from fastmcp import Client as MCPClient
from mcp.types import (
    ImageContent,
    TextContent,
)

from crow_cli.agent.configure import Config
from crow_cli.agent.hooks import CommandHook, FileSnapshotHook
from crow_cli.agent.session import AgentSession


def route_to_session_id(agent_id: str) -> str:
    """Strip agent-idx suffix for ACP upstream calls."""
    return agent_id.rsplit("-", 1)[0]


def tool_match(tool_name: str, terms: tuple[str]) -> bool:
    return any([x in tool_name.lower() for x in terms])


def get_tool_kind(tool_name: str) -> ToolKind:
    """Map tool names to ACP ToolKind."""
    # Orchestration tools: exact-match first so the substring rules below don't
    # misclassify them (task_read->read, task_write->edit, send_prompt->execute).
    if tool_name in ("send_prompt", "task_read", "task_write", "task_send"):
        return "other"
    # Common MCP tool patterns
    if tool_match(tool_name, ("read_file", "read", "view", "list_directory", "list")):
        return "read"
    elif tool_match(
        tool_name, ("write_file", "write", "edit", "create", "str_replace")
    ):
        return "edit"
    elif tool_match(tool_name, ("delete", "remove")):
        return "delete"
    elif tool_match(tool_name, ("move", "rename")):
        return "move"
    elif tool_match(tool_name, ("search", "grep", "find")):
        return "search"
    elif tool_match(tool_name, ("fetch", "download")):
        return "fetch"
    elif tool_match(tool_name, ("terminal", "bash", "shell", "execute", "prompt")):
        return "execute"
    else:
        return "other"


def mcp_content_to_acp_blocks(
    mcp_content: list[TextContent | ImageContent],
) -> list:
    """
    Convert MCP content blocks to ACP content blocks.

    Handles TextContent and ImageContent from MCP protocol
    and converts them to appropriate ACP content blocks.

    Args:
        mcp_content: List of content blocks from MCP CallToolResult

    Returns:
        List of ACP tool content blocks wrapped with tool_content()
    """
    acp_blocks = []
    for item in mcp_content:
        if isinstance(item, TextContent):
            acp_blocks.append(tool_content(text_block(item.text)))
        elif isinstance(item, ImageContent):
            # MCP uses mimeType (camelCase), ACP uses mime_type (snake_case)
            acp_blocks.append(
                tool_content(image_block(data=item.data, mime_type=item.mimeType))
            )
        else:
            # Fallback: try to extract text if possible
            if hasattr(item, "text"):
                acp_blocks.append(tool_content(text_block(str(item.text))))
            elif hasattr(item, "data"):
                # Binary data as string representation
                acp_blocks.append(tool_content(text_block(str(item.data))))
            else:
                # Last resort: convert entire object to string
                acp_blocks.append(tool_content(text_block(str(item))))
    return acp_blocks


def mcp_content_to_openai_format(
    mcp_content: list[TextContent | ImageContent],
) -> list | str:
    """
    Convert MCP content blocks to OpenAI-compatible content format.

    Returns a list of content blocks (text + images) so the LLM
    can see images returned by MCP tools (e.g. vision/capture tools).

    Args:
        mcp_content: List of content blocks from MCP CallToolResult

    Returns:
        List of OpenAI content blocks, or plain string if only text.
    """
    if not mcp_content:
        return ""

    blocks = []
    for item in mcp_content:
        if isinstance(item, TextContent):
            blocks.append({"type": "text", "text": item.text})
        elif isinstance(item, ImageContent):
            blocks.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{item.mimeType};base64,{item.data}"},
                }
            )
        else:
            # Fallback: convert to text
            text = getattr(item, "text", str(item))
            blocks.append({"type": "text", "text": text})

    # If only one text block, return plain string for compatibility
    if len(blocks) == 1 and blocks[0]["type"] == "text":
        return blocks[0]["text"]

    return blocks


async def execute_acp_terminal(
    conn: Client,
    sessions: dict[str, AgentSession],
    turn_id: str,
    agent_id: str,
    tool_call_id: str,
    args: dict[str, Any],
    logger: Logger,
    hooks: list[CommandHook],
) -> str:
    """
    Execute terminal command via ACP client terminal.

    Maps the MCP terminal tool args to ACP client terminal:
    - command: The command to run
    - timeout: Max seconds to wait (default 30)
    - is_input: Not supported by ACP terminal (runs single commands)
    - reset: Not needed (ACP terminal is fresh each call)

    Args:
        turn_id: Turn ID for ACP tool call IDs
        session_id: ACP session ID
        tool_call_id: LLM tool call ID
        args: Tool arguments from LLM

    Returns:
        Result string with output and status
    """
    command = args.get("command", "")
    timeout_seconds = float(args.get("timeout") or 30.0)

    # Build ACP tool call ID from turn_id + llm tool call id
    acp_tool_call_id = f"{turn_id}/{tool_call_id}"

    session_id = route_to_session_id(agent_id)

    # Get session state for cwd
    session = sessions.get(agent_id)
    cwd = session.cwd if session and hasattr(session, "cwd") else "/tmp"

    terminal_id: str | None = None
    timed_out = False

    try:
        # 1. Send tool call start
        await conn.session_update(
            session_id=session_id,
            update=ToolCallStart(
                session_update="tool_call",
                tool_call_id=acp_tool_call_id,
                title=command,
                kind="execute",
                status="pending",
            ),
        )

        # --- Command hooks: pre-execution guards ---
        # Ephemeral terminals do not persist cwd or env — hooks enforce policies.
        for hook in hooks:
            rejection = hook(command)
            if rejection is not None:
                return rejection

        # 2. Create terminal via ACP client
        logger.info(f"Creating ACP terminal for command: {command}")
        terminal_response = await conn.create_terminal(
            command=command,
            session_id=session_id,
            cwd=cwd,
            output_byte_limit=100000,  # 100KB limit
        )
        terminal_id = terminal_response.terminal_id
        logger.info(f"Terminal created: {terminal_id}")

        # 3. Send tool call update with terminal content for live display
        await conn.session_update(
            session_id=session_id,
            update=ToolCallProgress(
                session_update="tool_call_update",
                tool_call_id=acp_tool_call_id,
                status="in_progress",
                content=[
                    TerminalToolCallContent(
                        type="terminal",
                        terminal_id=terminal_id,
                    )
                ],
            ),
        )

        # 4. Wait for terminal to exit with timeout
        exit_code = None
        exit_signal = None
        try:
            async with asyncio.timeout(timeout_seconds):
                exit_response = await conn.wait_for_terminal_exit(
                    session_id=session_id,
                    terminal_id=terminal_id,
                )
                exit_code = exit_response.exit_code
                exit_signal = exit_response.signal
                logger.info(
                    f"Terminal exited with code: {exit_code}, signal: {exit_signal}"
                )
        except TimeoutError:
            logger.warning(f"Terminal timed out after {timeout_seconds}s")
            timed_out = True
            await conn.kill_terminal(session_id=session_id, terminal_id=terminal_id)

        # 5. Get final output
        output_response = await conn.terminal_output(
            session_id=session_id, terminal_id=terminal_id
        )
        output = output_response.output

        truncated_note = " Output was truncated." if output_response.truncated else ""

        # 6. Send final tool call update
        final_status = (
            "failed"
            if (exit_code and exit_code != 0) or exit_signal or timed_out
            else "completed"
        )

        await conn.session_update(
            session_id=session_id,
            update=ToolCallProgress(
                session_update="tool_call_update",
                tool_call_id=acp_tool_call_id,
                status=final_status,
            ),
        )

        # 7. Build result message
        if timed_out:
            return f"⏱️ Command killed by timeout ({timeout_seconds}s){truncated_note}\n\nOutput:\n{output}"
        elif exit_signal:
            return f"⚠️ Command terminated by signal: {exit_signal}{truncated_note}\n\nOutput:\n{output}"
        elif exit_code not in (None, 0):
            return f"❌ Command failed with exit code: {exit_code}{truncated_note}\n\nOutput:\n{output}"
        else:
            if truncated_note:
                return f"{output}\n\n{truncated_note.strip()}"
            return output

    except Exception as e:
        logger.error(f"Error executing ACP terminal: {e}", exc_info=True)
        return f"Error: {str(e)}"

    finally:
        # 8. Release terminal if created
        if terminal_id:
            with suppress(Exception):
                await conn.release_terminal(
                    session_id=session_id, terminal_id=terminal_id
                )
                logger.info(f"Released terminal: {terminal_id}")


async def execute_acp_write(
    conn: Client,
    turn_id: str,
    sessions: dict[str, AgentSession],
    agent_id: str,
    tool_call_id: str,
    args: dict[str, Any],
    logger: Logger,
    snapshot_hooks: list[FileSnapshotHook] | None = None,
) -> str:
    """
    Write file via ACP client filesystem.

    Args:
        turn_id: Turn ID for ACP tool call IDs
        sessions: Dict of agent_id -> AgentSession
        agent_id: Agent ID (internal key)
        tool_call_id: LLM tool call ID
        args: Tool arguments from LLM (file_path, content)
        snapshot_hooks: Hooks to capture pre-mutation file state

    Returns:
        Success message
    """
    path = args.get("file_path", "")
    content = args.get("content", "")

    # maximal_deserialize may have decoded JSON strings into dicts/lists.
    # If content is not a string, serialize it back so write_text_file works.
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, indent=2)
    session_id = route_to_session_id(agent_id)

    # Build ACP tool call ID from turn_id + llm tool call id
    acp_tool_call_id = f"{turn_id}/{tool_call_id}"

    # Pre-hook: capture before state for Monaco diffs
    if path and snapshot_hooks:
        session = sessions.get(agent_id)
        if session:
            for hook in snapshot_hooks:
                hook(session, acp_tool_call_id, "write", path, logger)

    try:
        # 1. Send tool call start
        title = f"write: {path}"
        await conn.session_update(
            session_id=session_id,
            update=start_edit_tool_call(
                tool_call_id=acp_tool_call_id,
                title=title,
                path=path,
                content=content,
            ),
        )

        # 2. Send in_progress update with diff content
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(
                acp_tool_call_id,
                status="in_progress",
                content=[tool_diff_content(path=path, new_text=content)],
            ),
        )

        # 3. Write file via ACP client
        logger.info(f"Writing file via ACP: {path}")
        await conn.write_text_file(
            session_id=session_id,
            path=path,
            content=content,
        )

        # 4. Send completion update
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(acp_tool_call_id, status="completed"),
        )

        return f"Successfully wrote to {path}"

    except Exception as e:
        logger.error(f"Error writing file via ACP: {e}", exc_info=True)
        # Send failed status
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(acp_tool_call_id, status="failed"),
        )
        return f"Error writing file: {str(e)}"


async def execute_acp_read(
    conn: Client,
    turn_id: str,
    agent_id: str,
    tool_call_id: str,
    args: dict[str, Any],
    logger: Logger,
) -> str:
    """
    Read file via ACP client filesystem.

    Args:
        turn_id: Turn ID for ACP tool call IDs
        agent_id: Agent ID (internal key)
        tool_call_id: LLM tool call ID
        args: Tool arguments from LLM (file_path, offset, limit)

    Returns:
        File contents with line numbers
    """
    path = args.get("file_path", "")
    offset = args.get("offset", 1)
    limit = args.get("limit", 4000)
    session_id = route_to_session_id(agent_id)

    # Build ACP tool call ID from turn_id + llm tool call id
    acp_tool_call_id = f"{turn_id}/{tool_call_id}"

    try:
        # 1. Send tool call start
        title = f"read: {path}"
        await conn.session_update(
            session_id=session_id,
            update=start_read_tool_call(
                tool_call_id=acp_tool_call_id,
                title=title,
                path=path,
            ),
        )

        # 2. Send in_progress update
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(acp_tool_call_id, status="in_progress"),
        )

        # 3. Read file via ACP client
        logger.info(f"Reading file via ACP: {path}")
        response = await conn.read_text_file(
            session_id=session_id,
            path=path,
            line=offset,
            limit=limit,
        )
        content = response.content or ""

        # 4. Send completion update with file content
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(
                acp_tool_call_id,
                status="completed",
                content=[tool_content(text_block(content))],
            ),
        )

        return content

    except Exception as e:
        logger.error(f"Error reading file via ACP: {e}", exc_info=True)
        # Send failed status
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(acp_tool_call_id, status="failed"),
        )
        return f"Error reading file: {str(e)}"


async def execute_acp_edit(
    conn: Client,
    turn_id: str,
    mcp_clients: dict[str, MCPClient],
    sessions: dict[str, AgentSession],
    agent_id: str,
    tool_call_id: str,
    args: dict[str, Any],
    logger: Logger,
    snapshot_hooks: list[FileSnapshotHook] | None = None,
) -> str:
    """
    Edit file with fuzzy matching, sending diff content to ACP client.

    This executes the edit locally (fuzzy matching is agent-side) but
    sends proper diff content for the client to display.

    Args:
        turn_id: Turn ID for ACP tool call IDs
        sessions: Dict of agent_id -> AgentSession
        agent_id: Agent ID (internal key)
        tool_call_id: LLM tool call ID
        args: Tool arguments from LLM (file_path, old_string, new_string, replace_all)
        snapshot_hooks: Hooks to capture pre-mutation file state

    Returns:
        Result string from the edit operation
    """
    path = args.get("file_path", "")
    old_text = args.get("old_string", "")
    new_text = args.get("new_string", "")
    session_id = route_to_session_id(agent_id)

    # Build ACP tool call ID from turn_id + llm tool call id
    acp_tool_call_id = f"{turn_id}/{tool_call_id}"

    # Pre-hook: capture before state for Monaco diffs
    if path and snapshot_hooks:
        session = sessions.get(agent_id)
        if session:
            for hook in snapshot_hooks:
                hook(session, acp_tool_call_id, "edit", path, logger)

    try:
        # 1. Send tool call start
        title = f"edit: {path}"
        await conn.session_update(
            session_id=session_id,
            update=start_edit_tool_call(
                tool_call_id=acp_tool_call_id,
                title=title,
                path=path,
                content=new_text,
            ),
        )

        # 2. Send in_progress update with diff content
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(
                acp_tool_call_id,
                status="in_progress",
                content=[
                    tool_diff_content(path=path, new_text=new_text, old_text=old_text)
                ],
            ),
        )

        # 3. Execute edit via local MCP tool (fuzzy matching is agent-side)
        logger.info(f"Executing edit via MCP: {path}")
        mcp_client = mcp_clients.get(session_id)
        if not mcp_client:
            raise RuntimeError(f"No MCP client for session {session_id}")
        result = await mcp_client.call_tool("edit", args)

        result_content = result.content[0].text

        # 4. Send completion update
        status = "completed" if "Error" not in result_content else "failed"
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(acp_tool_call_id, status=status),
        )

        return result_content

    except Exception as e:
        logger.error(f"Error executing edit: {e}", exc_info=True)
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(acp_tool_call_id, status="failed"),
        )
        return f"Error: {str(e)}"


async def execute_acp_tool(
    conn: Client,
    turn_id: str,
    mcp_clients: dict[str, MCPClient],
    agent_id: str,
    tool_call_id: str,
    tool_name: str,
    args: dict[str, Any],
    logger: Logger,
) -> str:
    """
    Execute a generic tool via MCP and report with content.

    Used for tools like search, fetch, etc. that return text content
    to display to the user.

    Args:
        turn_id: Turn ID for ACP tool call IDs
        agent_id: Agent ID (internal key)
        tool_call_id: LLM tool call ID
        tool_name: Name of the MCP tool to call
        args: Tool arguments from LLM
        kind: Tool kind for display (search, fetch, other)

    Returns:
        Result string from the tool
    """
    session_id = route_to_session_id(agent_id)
    # Build ACP tool call ID from turn_id + llm tool call id
    acp_tool_call_id = f"{turn_id}/{tool_call_id}"
    kind: ToolKind = get_tool_kind(tool_name)
    try:
        # 1. Send tool call start
        title = f"{tool_name}"
        await conn.session_update(
            session_id=session_id,
            update=ToolCallStart(
                session_update="tool_call",
                tool_call_id=acp_tool_call_id,
                title=title,
                kind=kind,
                status="pending",
            ),
        )

        # 2. Send in_progress update
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(acp_tool_call_id, status="in_progress"),
        )

        # 3. Execute tool via MCP
        logger.info(f"Executing tool via MCP: {tool_name}")
        mcp_client = mcp_clients.get(session_id)
        if not mcp_client:
            raise RuntimeError(f"No MCP client for session {session_id}")
        result = await mcp_client.call_tool(tool_name, args)

        # Convert MCP content to ACP content blocks (for client display)
        acp_content_blocks = mcp_content_to_acp_blocks(result.content)

        # Convert MCP content to OpenAI format (for LLM tool response)
        # This preserves images so the LLM can see them
        result_content = mcp_content_to_openai_format(result.content)

        # 4. Send completion update with content
        status = "completed" if not getattr(result, "isError", False) else "failed"
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(
                acp_tool_call_id,
                status=status,
                content=acp_content_blocks,
            ),
        )

        return result_content

    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(acp_tool_call_id, status="failed"),
        )
        return f"Error: {str(e)}"



async def execute_acp_prompt(
    conn: Client,
    turn_id: str,
    mcp_clients: dict[str, MCPClient],
    agent_id: str,
    tool_call_id: str,
    tool_name: str,
    args: dict[str, Any],
    logger: Logger,
) -> str:
    """
    Execute a the prompt tool after adding session_id to tools args via MCP and report with content.

    Used for prompt tool which sends a message to another agent
    Returns text content to display to the user.

    Args:
        turn_id: Turn ID for ACP tool call IDs
        agent_id: Agent ID (internal key)
        tool_call_id: LLM tool call ID
        tool_name: Name of the MCP tool to call
        args: Tool arguments _from_ LLM
        kind: Tool kind for display (search, fetch, other)

    Returns:
        Result string from the tool
    """
    session_id = route_to_session_id(agent_id)
    # Build ACP tool call ID from turn_id + llm tool call id
    acp_tool_call_id = f"{turn_id}/{tool_call_id}"
    kind: ToolKind = get_tool_kind(tool_name)
    try:
        # 1. Send tool call start
        title = f"{tool_name}"
        await conn.session_update(
            session_id=session_id,
            update=ToolCallStart(
                session_update="tool_call",
                tool_call_id=acp_tool_call_id,
                title=title,
                kind=kind,
                status="pending",
            ),
        )

        # 2. Send in_progress update
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(acp_tool_call_id, status="in_progress"),
        )

        # 3. Execute tool via MCP
        logger.info(f"Executing tool via MCP: {tool_name}")
        mcp_client = mcp_clients.get(session_id)
        if not mcp_client:
            raise RuntimeError(f"No MCP client for session {session_id}")
        args["from_session_id"] = session_id
        result = await mcp_client.call_tool(tool_name, args)

        # Convert MCP content to ACP content blocks (for client display)
        acp_content_blocks = mcp_content_to_acp_blocks(result.content)

        # Convert MCP content to OpenAI format (for LLM tool response)
        # This preserves images so the LLM can see them
        result_content = mcp_content_to_openai_format(result.content)

        # 4. Send completion update with content
        status = "completed" if not getattr(result, "isError", False) else "failed"
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(
                acp_tool_call_id,
                status=status,
                content=acp_content_blocks,
            ),
        )

        return result_content

    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(acp_tool_call_id, status="failed"),
        )
        return f"Error: {str(e)}"


# ─── Orchestration tool execution ──────────────────────────────────────────
# Routes to client via ACP ext_method for agent-to-agent communication
# Backend methods: _send, _task/read, _task/write


async def execute_orchestration_send_prompt(
    conn: Client,
    turn_id: str,
    agent_id: str,
    tool_call_id: str,
    args: dict[str, Any],
    logger: Logger,
) -> str:
    """
    Send a prompt to another agent session via _send ext_method.
    
    Args:
        conn: ACP client connection
        turn_id: Current turn ID
        agent_id: Current agent ID
        tool_call_id: LLM tool call ID
        args: Tool arguments (toSessionId, blocks)
        logger: Logger instance
    
    Returns:
        Result from the client-side operation
    """
    session_id = route_to_session_id(agent_id)
    acp_tool_call_id = f"{turn_id}/{tool_call_id}"
    to_session_id = args.get("to_session_id", "")
    blocks = args.get("blocks", [])
    
    try:
        # 1. Send tool call start
        await conn.session_update(
            session_id=session_id,
            update=ToolCallStart(
                session_update="tool_call",
                tool_call_id=acp_tool_call_id,
                title=f"Send prompt to {to_session_id}",
                kind="other",
                status="pending",
            ),
        )
        
        # 2. Call _send ext_method to route to client
        logger.info(f"Routing _send to client: to={to_session_id}")
        result = await conn.ext_method(
            method="send",
            params={
                "toSessionId": to_session_id,
                "blocks": blocks,
            }
        )
        
        # 3. Send completion
        status_msg = result.get("status", "sent")
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(
                tool_call_id=acp_tool_call_id,
                status="completed",
                content=[tool_content(text_block(f"Message sent: {status_msg}"))],
            ),
        )
        
        return f"Message sent to {to_session_id}: {status_msg}"
        
    except Exception as e:
        logger.error(f"Error in send_prompt: {e}", exc_info=True)
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(acp_tool_call_id, status="failed"),
        )
        return f"Error sending prompt: {str(e)}"


async def execute_orchestration_task_read(
    conn: Client,
    turn_id: str,
    agent_id: str,
    tool_call_id: str,
    args: dict[str, Any],
    logger: Logger,
) -> str:
    """
    Read task list via _task/read ext_method.
    
    Args:
        conn: ACP client connection
        turn_id: Current turn ID
        agent_id: Current agent ID
        tool_call_id: LLM tool call ID
        args: Tool arguments (none needed)
        logger: Logger instance
    
    Returns:
        Task list summary
    """
    session_id = route_to_session_id(agent_id)
    acp_tool_call_id = f"{turn_id}/{tool_call_id}"
    
    try:
        # 1. Send tool call start
        await conn.session_update(
            session_id=session_id,
            update=ToolCallStart(
                session_update="tool_call",
                tool_call_id=acp_tool_call_id,
                title="Read task list",
                kind="other",
                status="pending",
            ),
        )
        
        # 2. Call _task/read ext_method
        logger.info("Routing _task/read to client")
        result = await conn.ext_method(
            method="task/read",
            params={}
        )
        
        # 3. Format result
        summary = result.get("summary", "No tasks")
        tasks = result.get("tasks", [])
        
        tasks_text = summary
        if tasks:
            tasks_text += "\n\n" + "\n".join([
                f"- [{t.get('status', 'pending')}] {t.get('title', 'untitled')} (id: {t.get('id', '?')})"
                for t in tasks
            ])
        
        # 4. Send completion
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(
                tool_call_id=acp_tool_call_id,
                status="completed",
                content=[tool_content(text_block(tasks_text))],
            ),
        )
        
        return tasks_text
        
    except Exception as e:
        logger.error(f"Error in task_read: {e}", exc_info=True)
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(acp_tool_call_id, status="failed"),
        )
        return f"Error reading tasks: {str(e)}"


async def execute_orchestration_task_write(
    conn: Client,
    turn_id: str,
    agent_id: str,
    tool_call_id: str,
    args: dict[str, Any],
    logger: Logger,
) -> str:
    """
    Wholesale-replace the session's task list via _task/write ext_method.

    Args:
        conn: ACP client connection
        turn_id: Current turn ID
        agent_id: Current agent ID
        tool_call_id: LLM tool call ID
        args: Tool arguments (todos: list[dict])
        logger: Logger instance

    Returns:
        Result from the client-side operation
    """
    session_id = route_to_session_id(agent_id)
    acp_tool_call_id = f"{turn_id}/{tool_call_id}"
    todos = args.get("todos", [])

    try:
        # 1. Send tool call start
        await conn.session_update(
            session_id=session_id,
            update=ToolCallStart(
                session_update="tool_call",
                tool_call_id=acp_tool_call_id,
                title=f"Write {len(todos)} todos",
                kind="other",
                status="pending",
            ),
        )

        # 2. Call _task/write ext_method
        logger.info(f"Routing _task/write to client: {len(todos)} todos")
        result = await conn.ext_method(
            method="task/write",
            params={"todos": todos}
        )

        # 3. Format result
        tasks = result.get("tasks", [])
        message = f"Updated task list: {len(tasks)} task(s)"

        # 4. Send completion
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(
                tool_call_id=acp_tool_call_id,
                status="completed",
                content=[tool_content(text_block(message))],
            ),
        )

        return message

    except Exception as e:
        logger.error(f"Error in task_write: {e}", exc_info=True)
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(acp_tool_call_id, status="failed"),
        )
        return f"Error writing task: {str(e)}"


async def execute_orchestration_task_send(
    conn: Client,
    turn_id: str,
    agent_id: str,
    tool_call_id: str,
    args: dict[str, Any],
    logger: Logger,
) -> str:
    """
    Send a batch of tasks to an orchestrator session via _task/send ext_method.
    
    Args:
        conn: ACP client connection
        turn_id: Current turn ID
        agent_id: Current agent ID
        tool_call_id: LLM tool call ID
        args: Tool arguments (to_session_id, tasks)
        logger: Logger instance
    
    Returns:
        Result from the client-side operation
    """
    session_id = route_to_session_id(agent_id)
    acp_tool_call_id = f"{turn_id}/{tool_call_id}"
    to_session_id = args.get("to_session_id", "")
    tasks = args.get("tasks", [])
    
    try:
        # 1. Send tool call start
        await conn.session_update(
            session_id=session_id,
            update=ToolCallStart(
                session_update="tool_call",
                tool_call_id=acp_tool_call_id,
                title=f"Send {len(tasks)} tasks to {to_session_id}",
                kind="other",
                status="pending",
            ),
        )
        
        # 2. Call _task/send ext_method
        logger.info(f"Routing _task/send to client: to={to_session_id}, count={len(tasks)}")
        result = await conn.ext_method(
            method="task/send",
            params={
                "toSessionId": to_session_id,
                "tasks": tasks,
            }
        )
        
        # 3. Format result
        task_count = result.get("taskCount", len(tasks))
        message = f"Sent {task_count} tasks to orchestrator session {to_session_id}"
        
        # 4. Send completion
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(
                tool_call_id=acp_tool_call_id,
                status="completed",
                content=[tool_content(text_block(message))],
            ),
        )
        
        return message
        
    except Exception as e:
        logger.error(f"Error in task_send: {e}", exc_info=True)
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(acp_tool_call_id, status="failed"),
        )
        return f"Error sending tasks: {str(e)}"


async def execute_orchestration_orchestrator_task_read(
    conn: Client,
    turn_id: str,
    agent_id: str,
    tool_call_id: str,
    args: dict[str, Any],
    logger: Logger,
) -> str:
    """Read orchestrator task list via _task/orchestrator/read ext_method."""
    session_id = route_to_session_id(agent_id)
    acp_tool_call_id = f"{turn_id}/{tool_call_id}"

    try:
        await conn.session_update(
            session_id=session_id,
            update=ToolCallStart(
                session_update="tool_call",
                tool_call_id=acp_tool_call_id,
                title="Read orchestrator task list",
                kind="other",
                status="pending",
            ),
        )

        logger.info("Routing _task/orchestrator/read to client")
        result = await conn.ext_method(
            method="task/orchestrator/read",
            params={}
        )

        summary = result.get("summary", "No orchestrator tasks")
        tasks = result.get("tasks", [])

        tasks_text = summary
        if tasks:
            tasks_text += "\n\n" + "\n".join([
                f"- [{t.get('status', 'pending')}] {t.get('title', 'untitled')} (id: {t.get('id', '?')})"
                for t in tasks
            ])

        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(
                tool_call_id=acp_tool_call_id,
                status="completed",
                content=[tool_content(text_block(tasks_text))],
            ),
        )

        return tasks_text

    except Exception as e:
        logger.error(f"Error in orchestrator_task_read: {e}", exc_info=True)
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(acp_tool_call_id, status="failed"),
        )
        return f"Error reading orchestrator tasks: {str(e)}"


async def execute_orchestration_orchestrator_task_write(
    conn: Client,
    turn_id: str,
    agent_id: str,
    tool_call_id: str,
    args: dict[str, Any],
    logger: Logger,
) -> str:
    """Wholesale-replace the orchestrator task list via _task/orchestrator/write ext_method."""
    session_id = route_to_session_id(agent_id)
    acp_tool_call_id = f"{turn_id}/{tool_call_id}"
    todos = args.get("todos", [])

    try:
        await conn.session_update(
            session_id=session_id,
            update=ToolCallStart(
                session_update="tool_call",
                tool_call_id=acp_tool_call_id,
                title=f"Write {len(todos)} orchestrator todos",
                kind="other",
                status="pending",
            ),
        )

        logger.info(f"Routing _task/orchestrator/write to client: {len(todos)} todos")
        result = await conn.ext_method(
            method="task/orchestrator/write",
            params={"todos": todos}
        )

        tasks = result.get("tasks", [])
        message = f"Updated orchestrator task list: {len(tasks)} task(s)"

        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(
                tool_call_id=acp_tool_call_id,
                status="completed",
                content=[tool_content(text_block(message))],
            ),
        )

        return message

    except Exception as e:
        logger.error(f"Error in orchestrator_task_write: {e}", exc_info=True)
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(acp_tool_call_id, status="failed"),
        )
        return f"Error writing orchestrator tasks: {str(e)}"
