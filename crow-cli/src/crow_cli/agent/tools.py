import asyncio
from contextlib import suppress
from logging import Logger
from typing import Any

from acp import (
    PROTOCOL_VERSION,
    Agent,
    AuthenticateResponse,
    InitializeResponse,
    LoadSessionResponse,
    NewSessionResponse,
    PromptResponse,
    SetSessionModeResponse,
    run_agent,
    text_block,
    update_agent_message,
    update_agent_thought,
)
from acp.helpers import (
    ToolCallContentVariant,
    start_edit_tool_call,
    start_read_tool_call,
    text_block,
    tool_content,
    tool_diff_content,
    update_tool_call,
)
from acp.interfaces import Client
from acp.schema import (
    AgentCapabilities,
    AgentMessageChunk,
    AudioContentBlock,
    ClientCapabilities,
    EmbeddedResourceContentBlock,
    HttpMcpServer,
    ImageContentBlock,
    Implementation,
    McpServerStdio,
    ResourceContentBlock,
    SseMcpServer,
    TerminalToolCallContent,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
    ToolKind,
)
from fastmcp import Client as MCPClient

from crow_cli.agent.configure import Config
from crow_cli.agent.session import Session


def tool_match(tool_name: str, terms: tuple[str]) -> bool:
    return any([x in tool_name.lower() for x in terms])


def get_tool_kind(tool_name: str) -> ToolKind:
    """Map tool names to ACP ToolKind."""
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
    elif tool_match(tool_name, ("terminal", "bash", "shell", "execute")):
        return "execute"
    else:
        return "other"


async def execute_acp_terminal(
    conn: Client,
    sessions: dict[str, Session],
    turn_id: str,
    session_id: str,
    tool_call_id: str,
    args: dict[str, Any],
    logger: Logger,
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

    # Get session state for cwd
    session = sessions.get(session_id)
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
                title=f"terminal: {command[:50]}{'...' if len(command) > 50 else ''}",
                kind="execute",
                status="pending",
            ),
        )

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
            return (
                f"✅ Command executed successfully{truncated_note}\n\nOutput:\n{output}"
            )

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
    session_id: str,
    tool_call_id: str,
    args: dict[str, Any],
    logger: Logger,
) -> str:
    """
    Write file via ACP client filesystem.

    Args:
        turn_id: Turn ID for ACP tool call IDs
        session_id: ACP session ID
        tool_call_id: LLM tool call ID
        args: Tool arguments from LLM (file_path, content)

    Returns:
        Success message
    """
    path = args.get("file_path", "")
    content = args.get("content", "")

    # Build ACP tool call ID from turn_id + llm tool call id
    acp_tool_call_id = f"{turn_id}/{tool_call_id}"

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
    session_id: str,
    tool_call_id: str,
    args: dict[str, Any],
    logger: Logger,
) -> str:
    """
    Read file via ACP client filesystem.

    Args:
        turn_id: Turn ID for ACP tool call IDs
        session_id: ACP session ID
        tool_call_id: LLM tool call ID
        args: Tool arguments from LLM (file_path, offset, limit)

    Returns:
        File contents with line numbers
    """
    path = args.get("file_path", "")
    offset = args.get("offset", 1)
    limit = args.get("limit", 4000)

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
    config: Config,
    session_id: str,
    tool_call_id: str,
    args: dict[str, Any],
    logger: Logger,
) -> str:
    """
    Edit file with fuzzy matching, sending diff content to ACP client.

    This executes the edit locally (fuzzy matching is agent-side) but
    sends proper diff content for the client to display.

    Args:
        turn_id: Turn ID for ACP tool call IDs
        session_id: ACP session ID
        tool_call_id: LLM tool call ID
        args: Tool arguments from LLM (file_path, old_string, new_string, replace_all)

    Returns:
        Result string from the edit operation
    """
    path = args.get("file_path", "")
    old_text = args.get("old_string", "")
    new_text = args.get("new_string", "")

    # Build ACP tool call ID from turn_id + llm tool call id
    acp_tool_call_id = f"{turn_id}/{tool_call_id}"

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
        result = await mcp_client.call_tool(config.EDIT_TOOL, args)
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
    session_id: str,
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
        session_id: ACP session ID
        tool_call_id: LLM tool call ID
        tool_name: Name of the MCP tool to call
        args: Tool arguments from LLM
        kind: Tool kind for display (search, fetch, other)

    Returns:
        Result string from the tool
    """
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
        result_content = result.content[0].text

        # 4. Send completion update with content
        status = "completed" if "Error" not in result_content else "failed"
        await conn.session_update(
            session_id=session_id,
            update=update_tool_call(
                acp_tool_call_id,
                status=status,
                content=[tool_content(text_block(result_content))],
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
