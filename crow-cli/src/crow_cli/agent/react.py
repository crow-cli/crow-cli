import asyncio
from asyncio import Event
from typing import Any

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
)
from fastmcp import Client as MCPClient
from openai import AsyncOpenAI

from crow_cli.agent.compact import compact
from crow_cli.agent.config import Config
from crow_cli.agent.context import maximal_deserialize
from crow_cli.agent.session import Session
from crow_cli.agent.tools import (
    execute_acp_edit,
    execute_acp_read,
    execute_acp_terminal,
    execute_acp_tool,
    execute_acp_write,
)


async def send_request(
    llm: AsyncOpenAI,
    session: Session,
    tools: list[dict],
):
    """
    Send request to LLM.

    Args:
        llm: The async OpenAI client.
        session: The current session containing messages and model identifier.
        tools: List of tool definitions.

    Returns:
        Streaming response from LLM
    """
    return await llm.chat.completions.create(
        model=session.model_identifier,
        messages=session.messages,
        tools=tools,
        stream=True,
        parallel_tool_calls=True,
    )


def process_chunk(
    chunk,
    thinking: list[str],
    content: list[str],
    tool_calls: dict,
    tool_call_id: str | None,
) -> tuple[list[str], list[str], dict, str | None, tuple[str | None, Any]]:
    """
    Process a single streaming chunk.

    Args:
        chunk: Streaming chunk from LLM
        thinking: Accumulated thinking tokens
        content: Accumulated content tokens
        tool_calls: Accumulated tool calls
        tool_call_id: Current tool call ID

    Returns:
        Tuple of (thinking, content, tool_calls, tool_call_id, new_token)
    """
    delta = chunk.choices[0].delta
    new_token = (None, None)
    if not delta.tool_calls:
        if not hasattr(delta, "reasoning_content"):
            verbal_chunk = delta.content
            if verbal_chunk:
                content.append(verbal_chunk)
                new_token = ("content", verbal_chunk)
        else:
            reasoning_chunk = delta.reasoning_content
            if reasoning_chunk:
                thinking.append(reasoning_chunk)
                new_token = ("thinking", reasoning_chunk)
    else:
        for call in delta.tool_calls:
            if call.id is not None:
                tool_call_id = call.id
                if call.id not in tool_calls:
                    tool_calls[call.id] = {
                        "function_name": call.function.name,
                        "arguments": [call.function.arguments],
                    }
                    new_token = (
                        "tool_call",
                        (call.function.name, call.function.arguments),
                    )
            else:
                arg_fragment = call.function.arguments
                tool_calls[tool_call_id]["arguments"].append(arg_fragment)
                new_token = ("tool_args", arg_fragment)

    return thinking, content, tool_calls, tool_call_id, new_token


def process_tool_call_inputs(tool_calls: dict) -> list[dict]:
    """
    Process tool call inputs into OpenAI format.

    Args:
        tool_calls: Dictionary of tool calls

    Returns:
        List of tool call objects in OpenAI format
    """
    tool_call_inputs = []
    for tool_call_id, tool_call in tool_calls.items():
        tool_call_inputs.append(
            {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": tool_call["function_name"],
                    "arguments": "".join(tool_call["arguments"]),
                },
            }
        )
    return tool_call_inputs


async def process_response(response, state_accumulator: dict):
    """
    Process streaming response from LLM.

    Args:
        response: Streaming response from LLM
        state_accumulator: Optional dict to expose partial state externally

    Yields:
        Tuple of (message_type, token) for each chunk

    Returns:
        Tuple of (thinking, content, tool_call_inputs, usage) when done
    """
    thinking, content, tool_calls, tool_call_id = [], [], {}, None
    final_usage = None
    # we need this in case we cancel mid-stream it all gets persisted anyway
    state_accumulator.update(
        {
            "thinking": thinking,
            "content": content,
            "tool_calls": tool_calls,
            "tool_call_inputs": [],
        }
    )
    async for chunk in response:
        if hasattr(chunk, "usage") and chunk.usage:
            final_usage = {
                "prompt_tokens": chunk.usage.prompt_tokens,
                "completion_tokens": chunk.usage.completion_tokens,
                "total_tokens": chunk.usage.total_tokens,
            }
        thinking, content, tool_calls, tool_call_id, new_token = process_chunk(
            chunk, thinking, content, tool_calls, tool_call_id
        )
        state_accumulator["thinking"] = thinking
        state_accumulator["content"] = content
        state_accumulator["tool_calls"] = tool_calls
        msg_type, token = new_token
        if msg_type:
            yield msg_type, token
    tool_call_inputs = process_tool_call_inputs(tool_calls)
    state_accumulator["tool_call_inputs"] = tool_call_inputs
    yield "final", (thinking, content, tool_call_inputs, final_usage)


async def execute_tool_calls(
    conn: Client,
    client_capabilities: ClientCapabilities,
    turn_id: str,
    config: Config,
    mcp_clients: dict[str, MCPClient],
    sessions: dict[str, Session],
    session_id: str,
    tool_call_inputs: list[dict],
    logger: Logger,
) -> list[dict]:
    """
    Execute tool calls via MCP or ACP client terminal.

    Args:
        turn_id: Turn ID for ACP tool call IDs
        session_id: Session ID to get MCP client
        tool_call_inputs: List of tool calls to execute

    Returns:
        List of tool results
    """
    tool_results = []
    use_acp_terminal = client_capabilities and getattr(
        client_capabilities, "terminal", False
    )
    fs_caps = getattr(client_capabilities, "fs", None) if client_capabilities else None
    use_acp_write = fs_caps and getattr(fs_caps, "write_text_file", False)
    use_acp_read = fs_caps and getattr(fs_caps, "read_text_file", False)
    for tool_call in tool_call_inputs:
        tool_name = tool_call["function"]["name"]
        tool_args = tool_call["function"]["arguments"]
        llm_tool_call_id = tool_call["id"]
        acp_tool_call_id = (
            f"{turn_id}/{llm_tool_call_id}" if turn_id else llm_tool_call_id
        )

        try:
            arg_dict = maximal_deserialize(tool_args)
            if tool_name == config.TERMINAL_TOOL and use_acp_terminal:
                result_content = await execute_acp_terminal(
                    conn=conn,
                    sessions=sessions,
                    turn_id=turn_id,
                    session_id=session_id,
                    tool_call_id=llm_tool_call_id,
                    args=arg_dict,
                    logger=logger,
                )
            elif tool_name == config.WRITE_TOOL and use_acp_write:
                result_content = await execute_acp_write(
                    conn=conn,
                    turn_id=turn_id,
                    session_id=session_id,
                    tool_call_id=llm_tool_call_id,
                    args=arg_dict,
                    logger=logger,
                )
            elif tool_name == config.READ_TOOL and use_acp_read:
                result_content = await execute_acp_read(
                    conn=conn,
                    turn_id=turn_id,
                    session_id=session_id,
                    tool_call_id=llm_tool_call_id,
                    args=arg_dict,
                    logger=logger,
                )
            elif tool_name == config.EDIT_TOOL:
                result_content = await execute_acp_edit(
                    conn=conn,
                    turn_id=turn_id,
                    mcp_clients=mcp_clients,
                    config=config,
                    session_id=session_id,
                    tool_call_id=llm_tool_call_id,
                    args=arg_dict,
                    logger=logger,
                )
            else:
                result_content = await execute_acp_tool(
                    conn=conn,
                    turn_id=turn_id,
                    mcp_clients=mcp_clients,
                    session_id=session_id,
                    tool_call_id=llm_tool_call_id,
                    tool_name=tool_name,
                    args=arg_dict,
                    logger=logger,
                )
            tool_results.append(
                {
                    "role": "tool",
                    "tool_call_id": llm_tool_call_id,
                    "content": result_content,
                }
            )
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
            await conn.session_update(
                session_id=session_id,
                update=ToolCallProgress(
                    session_update="tool_call_update",
                    tool_call_id=acp_tool_call_id,
                    status="failed",
                ),
            )
            tool_results.append(
                {
                    "role": "tool",
                    "tool_call_id": llm_tool_call_id,
                    "content": f"Error: {str(e)}",
                }
            )
    return tool_results


async def react_loop(
    conn: Client,
    config: Config,
    client_capabilities: ClientCapabilities,
    turn_id: str,
    mcp_clients: dict[str, MCPClient],
    llm: AsyncOpenAI,
    tools: list[dict],
    sessions: dict[str, Session],
    cancel_event: Event,
    session_id: str,
    state_accumulators: dict[str, dict],
    max_turns: int = 50000,
    on_compact: callable = None,
    logger: Logger = None,
):
    """
    Main ReAct loop with cancellation support.

    Args:
        session_id: Session ID to get session and tools
        max_turns: Maximum number of turns to execute

    Yields:
        Dictionary with 'type' and 'token' or 'messages' keys
    """
    session = sessions.get(session_id)
    cwd = session.cwd
    for turn in range(max_turns):
        if cancel_event and cancel_event.is_set():
            logger.info(f"Cancelled at start of turn {turn}")
            return

        response = await send_request(
            llm,
            session,
            tools,
        )
        state_accumulator = state_accumulators.get(
            session_id, {"thinking": [], "content": [], "tool_call_inputs": []}
        )
        thinking, content, tool_call_inputs, usage = [], [], [], None
        try:
            async for msg_type, token in process_response(response, state_accumulator):
                if msg_type == "final":
                    thinking, content, tool_call_inputs, usage = token
                else:
                    yield {"type": msg_type, "token": token}

        except asyncio.CancelledError:
            logger.info("React loop cancelled mid-stream")
            session.add_assistant_response(
                state_accumulator["thinking"],
                state_accumulator["content"],
                state_accumulator["tool_call_inputs"],
                [],
                usage,
            )
            raise

        if cancel_event and cancel_event.is_set():
            logger.info("Cancelled before tool execution")
            session.add_assistant_response(
                thinking, content, tool_call_inputs, [], usage
            )
            return

        ################################################
        # okay the llm has responded let's check usage
        #
        ################################################
        #####################################
        # This is a great place to check
        # if the context has gone over limi
        # and to compact it
        #####################################
        logger.info(f"Pre-Tool ExecutionUsage: {usage}")

        # 1. Check your token threshold
        if usage and usage["total_tokens"] > config.MAX_COMPACT_TOKENS:
            logger.info("Token threshold crossed. Initiating compaction...")

            # Compact updates the session in-place, so all references
            # (including the dictionary and local variables) automatically
            # see the new compacted state - no manual reference updates needed!
            logger.info(f"Pre-compacted session length: {len(session.messages)}")
            session = await compact(
                session=session,
                llm=llm,
                cwd=session.cwd,
                on_compact=on_compact,
            )
            logger.info(f"Post-compacted session length: {len(session.messages)}")
            logger.info("Compaction complete - session updated in-place.")

        # This ends the react loop
        if not tool_call_inputs:
            session.add_assistant_response(thinking, content, [], [], usage)
            logger.info(f"Final React Turn Usage: {usage}")
            yield {"type": "final_history", "messages": session.messages}
            # I guess we need to check context length here too?
            return

        #####################################
        # This is a great place to check
        # if the context has gone over limi
        # and to compact it
        #####################################
        logger.info(f"Pre-Tool ExecutionUsage: {usage}")
        # We've got some tools to execute!
        tool_results = await execute_tool_calls(
            conn=conn,
            client_capabilities=client_capabilities,
            turn_id=turn_id,
            config=config,
            mcp_clients=mcp_clients,
            sessions=sessions,
            session_id=session_id,
            tool_call_inputs=tool_call_inputs,
            logger=logger,
        )
        if cancel_event and cancel_event.is_set():
            logger.info("Cancelled after tool execution")
            session.add_assistant_response(
                thinking, content, tool_call_inputs, tool_results, usage
            )
            return

        #####################################
        #
        #####################################

        session.add_assistant_response(
            thinking, content, tool_call_inputs, tool_results, usage
        )
