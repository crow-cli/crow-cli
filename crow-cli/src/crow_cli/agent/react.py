import asyncio
import json
from asyncio import Event
from logging import Logger
from pathlib import Path
from typing import Any

from acp.interfaces import Client
from acp.schema import (
    ClientCapabilities,
    ToolCallProgress,
)
from fastmcp import Client as MCPClient
from openai import APIConnectionError, APIError, AsyncOpenAI, RateLimitError
from openai._exceptions import APITimeoutError

from crow_cli.agent.compact import compact
from crow_cli.agent.configure import Config
from crow_cli.agent.context import maximal_deserialize
from crow_cli.agent.hooks import CommandHook, FileSnapshotHook
from crow_cli.agent.prompt import normalize_blocks
from crow_cli.agent.session import AgentSession
from crow_cli.agent.tools import (
    execute_acp_edit,
    execute_acp_read,
    execute_acp_terminal,
    execute_acp_tool,
    execute_acp_write,
    execute_acp_prompt,
    execute_orchestration_send_prompt,
    execute_orchestration_task_read,
    execute_orchestration_task_write,
    execute_orchestration_task_send,
    execute_orchestration_orchestrator_task_read,
    execute_orchestration_orchestrator_task_write,
)


def session_from_agent_id(agent_id):
    return agent_id.rsplit("-", 1)[0]


async def send_request(
    llm: AsyncOpenAI,
    session: AgentSession,
    tools: list[dict],
    max_tokens: int,
    max_retries: int = 3,
    retry_delay: float = 1.0,
):
    """
    Send request to LLM with error handling and retry logic.

    Args:
        llm: The async OpenAI client.
        session: The current session containing messages and model identifier.
        tools: List of tool definitions.
        max_retries: Maximum number of retry attempts (default: 3).
        retry_delay: Base delay between retries in seconds (default: 1.0).

    Returns:
        Streaming response from LLM

    Raises:
        APIError: If the API request fails after all retries.
        RateLimitError: If rate limit is exceeded.
        APIConnectionError: If connection to API fails.
    """
    last_exception = None

    for attempt in range(max_retries):
        try:
            # Normalize messages - handle both list format (multimodal) and string format
            normalized_messages = []
            for msg in session.messages:
                normalized_msg = dict(msg)
                content = msg.get("content")
                # If content is a list of content blocks, keep it as-is (for multimodal)
                # But if it's a list with only text blocks and they're in the wrong format, fix it
                if isinstance(content, list):
                    normalized_msg["content"] = normalize_blocks(content)
                normalized_messages.append(normalized_msg)

            return await llm.chat.completions.create(
                model=session.model_identifier,
                messages=normalized_messages,
                tools=tools,
                stream=True,
                max_tokens=max_tokens,
                parallel_tool_calls=True,
                stream_options={"include_usage": True},  # Get usage in final chunk
            )
        except APITimeoutError as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = retry_delay * (2**attempt)  # Exponential backoff
                await asyncio.sleep(delay)
            else:
                raise
        except RateLimitError as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = retry_delay * (2**attempt)  # Exponential backoff
                await asyncio.sleep(delay)
            else:
                raise
        except APIConnectionError as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = retry_delay * (2**attempt)  # Exponential backoff
                await asyncio.sleep(delay)
            else:
                raise
        except APIError as e:
            # For other API errors, check if retryable
            if hasattr(e, "status_code") and e.status_code in [429, 500, 502, 503, 504]:
                if attempt < max_retries - 1:
                    delay = retry_delay * (2**attempt)  # Exponential backoff
                    await asyncio.sleep(delay)
                else:
                    raise
            else:
                # Non-retryable error, raise immediately
                raise
        except asyncio.CancelledError:
            # Don't retry on cancellation
            raise
        except Exception as e:
            # Unexpected error, log and re-raise
            last_exception = e
            raise

    # Should not reach here, but just in case
    raise last_exception


def process_chunk(
    chunk,
    thinking: list[str],
    content: list[str],
    tool_calls: dict,
) -> tuple[list[str], list[str], dict, list[tuple[str | None, Any]]]:
    """
    Process a single streaming chunk.

    Returns:
        Tuple of (thinking, content, tool_calls, new_tokens)
        where new_tokens is a list since a single chunk can contain both
        reasoning_content AND content (e.g. at the transition boundary).
    """
    # Final chunk may have usage but no choices
    if not chunk.choices or len(chunk.choices) == 0:
        return thinking, content, tool_calls, []

    delta = chunk.choices[0].delta
    new_tokens: list[tuple[str | None, Any]] = []

    # Check reasoning_content first
    reasoning_chunk = getattr(delta, "reasoning_content", None)
    if reasoning_chunk is not None and reasoning_chunk != "":
        thinking.append(reasoning_chunk)
        new_tokens.append(("thinking", reasoning_chunk))

    # Check content independently - transition chunks have BOTH
    content_chunk = delta.content
    if content_chunk is not None and content_chunk != "":
        content.append(content_chunk)
        new_tokens.append(("content", content_chunk))

    # Handle tool_calls independently
    if delta.tool_calls:
        for call in delta.tool_calls:
            index = call.index

            if index not in tool_calls:
                tool_calls[index] = {"id": "", "function_name": "", "arguments": []}

            if call.id:
                tool_calls[index]["id"] = call.id
            if call.function and call.function.name:
                tool_calls[index]["function_name"] = call.function.name
                new_tokens.append(
                    ("tool_call", (call.function.name, call.function.arguments or ""))
                )

            if call.function and call.function.arguments:
                arg_fragment = call.function.arguments
                tool_calls[index]["arguments"].append(arg_fragment)
                if not any(t[0] == "tool_call" for t in new_tokens):
                    new_tokens.append(("tool_args", arg_fragment))

    return thinking, content, tool_calls, new_tokens


def process_tool_call_inputs(tool_calls: dict) -> tuple[list[dict], list[bool]]:
    """
    Process tool call inputs into OpenAI format.

    Args:
        tool_calls: Dictionary of tool calls keyed by index

    Returns:
        Tuple of (list of tool call objects, list of booleans indicating if each was repaired)
    """
    tool_call_inputs = []
    repaired_flags = []
    # tool_calls is now a dict keyed by the integer index from the stream
    for index, tool_call in sorted(tool_calls.items()):
        arguments_str = "".join(tool_call["arguments"])
        was_repaired = False

        # Validate and repair JSON if needed
        # This is critical because some models (like qwen3.5-plus) may produce
        # malformed JSON that will cause API errors when sent back
        try:
            json.loads(arguments_str)
        except json.JSONDecodeError, TypeError, ValueError:
            # JSON is invalid, try to repair common issues
            # or default to empty object
            was_repaired = True
            try:
                # Try adding closing braces/brackets if missing
                if arguments_str.count("{") > arguments_str.count("}"):
                    arguments_str = arguments_str + "}" * (
                        arguments_str.count("{") - arguments_str.count("}")
                    )
                if arguments_str.count("[") > arguments_str.count("]"):
                    arguments_str = arguments_str + "]" * (
                        arguments_str.count("[") - arguments_str.count("]")
                    )
                # Validate again after repair attempt
                json.loads(arguments_str)
            except json.JSONDecodeError, TypeError, ValueError:
                # Still invalid, use empty object as fallback
                arguments_str = "{}"

        tool_call_inputs.append(
            dict(
                id=tool_call["id"],
                type="function",
                function=dict(
                    name=tool_call["function_name"],
                    arguments=arguments_str,
                ),
            )
        )
        repaired_flags.append(was_repaired)
    return tool_call_inputs, repaired_flags


def _serialize_chunk(chunk) -> dict:
    """
    Serialize a streaming chunk to a JSON-serializable dict.

    Dumps EVERYTHING from the chunk - we don't assume what's in it.
    Recursively handles nested Pydantic models and lists.
    """

    def _serialize_value(value):
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        if isinstance(value, list):
            return [_serialize_value(v) for v in value]
        if isinstance(value, dict):
            return {k: _serialize_value(v) for k, v in value.items()}
        # Pydantic model or arbitrary object - serialize attributes
        if hasattr(value, "model_dump"):
            return _serialize_value(value.model_dump())
        result = {}
        for attr in dir(value):
            if not attr.startswith("_") and not callable(getattr(value, attr)):
                result[attr] = _serialize_value(getattr(value, attr))
        return result

    return _serialize_value(chunk)


async def process_response(
    response, state_accumulator: dict, chunk_log_path: str | None = None
):
    """
    Process streaming response from LLM.

    Args:
        response: Streaming response from LLM
        state_accumulator: Optional dict to expose partial state externally
        chunk_log_path: Optional path to JSONL file for full chunk logging

    Yields:
        Tuple of (message_type, token) for each chunk

    Returns:
        Tuple of (thinking, content, tool_call_inputs, usage) when done
    """
    thinking, content, tool_calls = [], [], {}
    final_usage = None
    # we need this in case we cancel mid-stream it all gets persisted anyway
    state_accumulator.update(
        {
            "thinking": thinking,
            "content": content,
            "tool_calls": tool_calls,
        }
    )
    chunk_index = 0
    chunk_log_file = None
    if chunk_log_path:
        chunk_log_file = open(chunk_log_path, "a")

    try:
        async for chunk in response:
            chunk_index += 1

            # Check for usage in chunk (litellm returns it in the final chunk with stream_options={"include_usage": True})
            if hasattr(chunk, "usage") and chunk.usage is not None:
                final_usage = {
                    "prompt_tokens": getattr(chunk.usage, "prompt_tokens", None),
                    "completion_tokens": getattr(
                        chunk.usage, "completion_tokens", None
                    ),
                    "total_tokens": getattr(chunk.usage, "total_tokens", None),
                }

            thinking, content, tool_calls, new_tokens = process_chunk(
                chunk, thinking, content, tool_calls
            )
            state_accumulator["thinking"] = thinking
            state_accumulator["content"] = content
            state_accumulator["tool_calls"] = tool_calls

            # Write the ENTIRE raw chunk to JSONL
            if chunk_log_file is not None:
                log_entry = {
                    "chunk_index": chunk_index,
                    "msg_types": [t[0] for t in new_tokens] if new_tokens else None,
                    "chunk": _serialize_chunk(chunk),
                }
                chunk_log_file.write(json.dumps(log_entry) + "\n")
                chunk_log_file.flush()

            # Yield each token from this chunk (handles transition chunks with both)
            for msg_type, token in new_tokens:
                yield msg_type, token
    finally:
        if chunk_log_file:
            chunk_log_file.close()

    # Yield final result as a special chunk
    thinking, content, tool_calls = (
        state_accumulator["thinking"],
        state_accumulator["content"],
        state_accumulator["tool_calls"],
    )
    tool_call_inputs, _ = process_tool_call_inputs(tool_calls)
    yield "final", (thinking, content, tool_call_inputs, final_usage)


async def execute_tool_calls(
    conn: Client,
    client_capabilities: ClientCapabilities,
    turn_id: str,
    config: Config,
    mcp_clients: dict[str, MCPClient],
    sessions: dict[str, AgentSession],
    agent_id: str,
    tool_call_inputs: list[dict],
    logger: Logger,
    hooks: list[CommandHook],
    snapshot_hooks: list[FileSnapshotHook] | None = None,
) -> list[dict]:
    """
    Execute tool calls via MCP or ACP client terminal.

    Args:
        turn_id: Turn ID for ACP tool call IDs
        agent_id: Agent ID (internal key)
        tool_call_inputs: List of tool calls to execute

    Returns:
        List of tool results
    """
    session_id = session_from_agent_id(agent_id)
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
            logger.info(
                f"Raw tool_args type={type(tool_args).__name__} value={tool_args}"
            )
            arg_dict = maximal_deserialize(tool_args)
            if not isinstance(arg_dict, dict):
                # LLM produced malformed JSON for tool arguments.
                # Fix the arguments in-place so the message history
                # doesn't poison future API calls with invalid JSON.
                raw_args = tool_call["function"]["arguments"]
                tool_call["function"]["arguments"] = "{}"
                logger.error(f"Malformed tool arguments for {tool_name}: {raw_args}")
                result_content = (
                    f"Error: Your tool call for '{tool_name}' had malformed arguments "
                    f"that could not be parsed as JSON. Raw arguments: {raw_args!r}\n"
                    f"Please retry with valid JSON arguments matching the tool schema."
                )
                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": llm_tool_call_id,
                        "content": result_content,
                    }
                )
                continue
            if tool_name == "terminal" and use_acp_terminal:
                result_content = await execute_acp_terminal(
                    conn=conn,
                    sessions=sessions,
                    turn_id=turn_id,
                    agent_id=agent_id,
                    tool_call_id=llm_tool_call_id,
                    args=arg_dict,
                    logger=logger,
                    hooks=hooks,
                )
            elif tool_name == "write" and use_acp_write:
                result_content = await execute_acp_write(
                    conn=conn,
                    turn_id=turn_id,
                    sessions=sessions,
                    agent_id=agent_id,
                    tool_call_id=llm_tool_call_id,
                    args=arg_dict,
                    logger=logger,
                    snapshot_hooks=snapshot_hooks,
                )
            elif tool_name == "read" and use_acp_read:
                result_content = await execute_acp_read(
                    conn=conn,
                    turn_id=turn_id,
                    agent_id=agent_id,
                    tool_call_id=llm_tool_call_id,
                    args=arg_dict,
                    logger=logger,
                )
            elif tool_name == "edit":
                result_content = await execute_acp_edit(
                    conn=conn,
                    turn_id=turn_id,
                    mcp_clients=mcp_clients,
                    sessions=sessions,
                    agent_id=agent_id,
                    tool_call_id=llm_tool_call_id,
                    args=arg_dict,
                    logger=logger,
                    snapshot_hooks=snapshot_hooks,
                )
            elif tool_name == "prompt":
                result_content = await execute_acp_prompt(
                    conn=conn,
                    turn_id=turn_id,
                    mcp_clients=mcp_clients,
                    agent_id=agent_id,
                    tool_call_id=llm_tool_call_id,
                    tool_name=tool_name,
                    args=arg_dict,
                    logger=logger,
                )
            elif tool_name == "send_prompt":
                result_content = await execute_orchestration_send_prompt(
                    conn=conn,
                    turn_id=turn_id,
                    agent_id=agent_id,
                    tool_call_id=llm_tool_call_id,
                    args=arg_dict,
                    logger=logger,
                )
            elif tool_name == "task_read":
                result_content = await execute_orchestration_task_read(
                    conn=conn,
                    turn_id=turn_id,
                    agent_id=agent_id,
                    tool_call_id=llm_tool_call_id,
                    args=arg_dict,
                    logger=logger,
                )
            elif tool_name == "task_write":
                result_content = await execute_orchestration_task_write(
                    conn=conn,
                    turn_id=turn_id,
                    agent_id=agent_id,
                    tool_call_id=llm_tool_call_id,
                    args=arg_dict,
                    logger=logger,
                )
            elif tool_name == "task_send":
                result_content = await execute_orchestration_task_send(
                    conn=conn,
                    turn_id=turn_id,
                    agent_id=agent_id,
                    tool_call_id=llm_tool_call_id,
                    args=arg_dict,
                    logger=logger,
                )
            elif tool_name == "orchestrator_task_read":
                result_content = await execute_orchestration_orchestrator_task_read(
                    conn=conn,
                    turn_id=turn_id,
                    agent_id=agent_id,
                    tool_call_id=llm_tool_call_id,
                    args=arg_dict,
                    logger=logger,
                )
            elif tool_name == "orchestrator_task_write":
                result_content = await execute_orchestration_orchestrator_task_write(
                    conn=conn,
                    turn_id=turn_id,
                    agent_id=agent_id,
                    tool_call_id=llm_tool_call_id,
                    args=arg_dict,
                    logger=logger,
                )
            else:
                result_content = await execute_acp_tool(
                    conn=conn,
                    turn_id=turn_id,
                    mcp_clients=mcp_clients,
                    agent_id=agent_id,
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
    sessions: dict[str, AgentSession],
    agent_id: str,
    state_accumulators: dict[str, dict],
    max_turns: int = 50000,
    on_compact: callable = None,
    logger: Logger = None,
    hooks: list[CommandHook] | None = None,
    snapshot_hooks: list[FileSnapshotHook] | None = None,
    chunk_log_dir: str | None = None,
):
    """
    Main ReAct loop with cancellation support.

    Args:
        agent_id: Agent ID (internal key)
        max_turns: Maximum number of turns to execute
        chunk_log_dir: Optional directory to write raw chunk JSONL logs

    Yields:
        Dictionary with 'type' and 'token' or 'messages' keys
    """
    session = sessions.get(agent_id)
    cwd = session.cwd
    session_id = session_from_agent_id(agent_id)
    chunk_index = 0
    for turn in range(max_turns):
        response = await send_request(
            llm,
            session,
            tools,
            config.MAX_TOKENS,
        )
        state_accumulator = state_accumulators.get(
            session_id, {"thinking": [], "content": [], "tool_calls": {}}
        )
        thinking, content, tool_call_inputs, usage = [], [], [], None

        chunk_log_path = None
        if chunk_log_dir:
            chunk_log_path = str(Path(chunk_log_dir) / f"turn-{turn_id}.jsonl")

        try:
            async for msg_type, token in process_response(
                response, state_accumulator, chunk_log_path=chunk_log_path
            ):
                if msg_type == "final":
                    thinking, content, tool_call_inputs, usage = token
                else:
                    yield {"type": msg_type, "token": token}

        except asyncio.CancelledError:
            logger.info("React loop cancelled mid-stream")

            # CRITICAL: NEVER persist tool calls on cancellation
            # Whether tool calls are complete or incomplete, we MUST NOT persist them because:
            # 1. We're about to raise without executing the tools
            # 2. This means no tool responses will be added to history
            # 3. Next API call will fail: "An assistant message with tool_calls must be
            #    followed by tool messages responding to each tool_call_id"
            #
            # Even if the LLM finished streaming complete tool calls with valid JSON,
            # we cannot persist them because we never executed the tools.

            logger.info(
                "Cancellation occurred - not persisting tool calls to history "
                "to avoid breaking conversation (no tool responses would exist)"
            )
            # Don't persist tool calls - just persist thinking/content if any
            session.add_assistant_response(
                state_accumulator["thinking"],
                state_accumulator["content"],
                [],  # Empty tool calls - NEVER persist on cancellation
                logger,
                usage,
            )
            raise

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

            yield {
                "type": "compaction",
                "token": f"\n\nCompaction threshold of {config.MAX_COMPACT_TOKENS} reached — compacting conversation history...\n\n",
            }

            old_agent_id = agent_id
            logger.info(f"Pre-compacted session length: {len(session.messages)}")
            session = await compact(
                session=session,
                llm=llm,
                config=config,
                on_compact=on_compact,
                logger=logger,
            )
            agent_id = session.agent_id  # update agent_id for next turn
            logger.info(f"Post-compacted session length: {len(session.messages)}")
            logger.info("Compaction complete - session updated in-place.")
            # Start fresh turn with compacted session [system, user]
            continue

        # This ends the react loop — NO TOOLS!!
        if not tool_call_inputs and len(content) > 0:
            session.add_assistant_response(
                thinking,
                content,
                [],
                logger,
                usage,
            )
            logger.info(f"Final React Turn Usage: {usage}")
            yield {"type": "final_history", "messages": session.messages}
            # I guess we need to check context length here too?
            return
        # Continue the loop because we have tools to call
        # and miles to go before we sleep
        # and miles to go before we sleep
        else:
            logger.info(f"Pre-Tool ExecutionUsage: {usage}")
            # We've got some tools to execute!
            tool_results = await execute_tool_calls(
                conn=conn,
                client_capabilities=client_capabilities,
                turn_id=turn_id,
                config=config,
                mcp_clients=mcp_clients,
                sessions=sessions,
                agent_id=agent_id,
                tool_call_inputs=tool_call_inputs,
                logger=logger,
                hooks=hooks or [],
                snapshot_hooks=snapshot_hooks,
            )

            session.add_assistant_response(
                thinking,
                content,
                tool_call_inputs,
                logger,
                usage,
            )
            session.add_tool_response(tool_results, logger)
