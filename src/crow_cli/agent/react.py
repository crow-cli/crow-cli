import asyncio
import contextlib
import json
import logging
from logging import Logger
from pathlib import Path
from typing import Any

from acp import text_block
from acp.interfaces import Client
from acp.schema import (
    ClientCapabilities,
    ToolCallProgress,
    UserMessageChunk,
    UsageUpdate,
)
from fastmcp import Client as MCPClient
from openai import APIConnectionError, APIError, AsyncOpenAI, RateLimitError
from openai._exceptions import APITimeoutError

from crow_cli.agent.compact import compact
from crow_cli.config import (
    Config,
    build_sampling_params,
    max_compact_tokens_for,
    sampling_params_for,
)
from crow_cli.agent.context import maximal_deserialize
from crow_cli.agent.hooks import CommandHook, FileSnapshotHook
from crow_cli.agent.model_routing import (
    modalities_in_messages,
    route_model,
    strip_unsupported_blocks,
)
from crow_cli.agent.prompt import normalize_blocks
from crow_cli.agent.session import AgentSession
from crow_cli.memory import get_engine, parse_agent_id, running_tasks, wire_session_id
from crow_cli.memory.writes import claim_deliveries
from crow_cli.agent.tools import (
    execute_acp_edit,
    execute_acp_read,
    execute_acp_task,
    execute_acp_terminal,
    execute_acp_tool,
    execute_acp_write,
)

logger = logging.getLogger(__name__)

# Content used for the synthetic tool response that keeps history valid when
# the user cancels a turn after the LLM emitted tool calls. The API requires
# every tool_call_id in an assistant message to have a matching tool response.
TOOL_CALL_CANCELLED_MESSAGE = "Tool call cancelled by user"


def session_from_agent_id(agent_id):
    return wire_session_id(agent_id)


def cancelled_tool_results(tool_call_inputs: list[dict]) -> list[dict]:
    """Build a 'cancelled by user' tool response for every tool call."""
    return [
        {
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": TOOL_CALL_CANCELLED_MESSAGE,
        }
        for tc in tool_call_inputs
    ]


# ---------------------------------------------------------------------------
# Delivery consultation: completions register in STATE (the task tool's
# finish_task lands them in task_deliveries the moment they arrive); the
# loop CONSULTS state at natural breakpoints — prompt start, top of each
# iteration (highs), after each tool batch (highs), end of turn (all).
# No parking, no hostage, no in-process queues: nothing waits on
# unregistered work, so the old hang is structurally impossible.
# ---------------------------------------------------------------------------

# Delegation hold: while a subagent is running, the turn does NOT end —
# the loop stays alive (and cancellable) and re-consults the mailbox on
# this cadence until the reply lands. This is the only "wait" in the
# system; there is no out-of-loop watcher, so nothing can self-wake a
# session. After a cancel the reply simply stays queued until the user's
# next prompt (the prompt-start drain injects it).
DELIVERY_POLL_S = 2.0


async def consult_deliveries(
    engine,
    session,
    conn: Client,
    session_id: str,
    logger: Logger,
    high_only: bool = False,
) -> bool:
    """Land pending deliveries as synthetic user messages.

    Returns True when anything was injected (the loop must react). The
    claim is ATOMIC (one UPDATE...RETURNING): the loop's own consult
    points (prompt start, top-of-loop, between-batch, end-of-turn, hold)
    race for the same rows and each delivery is still injected exactly
    once. With high_only=True only highs are claimed — the mid-turn
    breakpoint; lows stay pending for end of turn.
    """
    deliveries = claim_deliveries(
        engine, session_id, "high" if high_only else None
    )
    if not deliveries:
        return False
    for d in deliveries:
        await session.add_message({"role": "user", "content": d["content"]})
        with contextlib.suppress(Exception):
            await conn.session_update(
                session_id=session_id,
                update=UserMessageChunk(
                    session_update="user_message_chunk",
                    content=text_block(d["content"]),
                ),
            )
        logger.info(
            "DELIVERY: injected %s (%s) into %s",
            d["task_id"],
            d["priority"],
            session_id,
        )
    return True


# Provider-side transient faults that surface as HTTP 400 and so are never
# retried by the openai SDK (it only retries 429/5xx/connection). Observed
# in the wild: DashScope's server-side multimodal ingest timing out while
# processing a large image payload ("invalid_parameter_error" /
# "Download multimodal file timed out"). Sporadic => retryable.
_TRANSIENT_400_MARKERS = (
    "download multimodal file timed out",
    "multimodal file timed out",
    "ingest timeout",
    "ingest timed out",
)


def _is_transient_provider_400(e: APIError) -> bool:
    if getattr(e, "status_code", None) != 400:
        return False
    try:
        body = json.dumps(getattr(e, "body", None), ensure_ascii=False)
    except (TypeError, ValueError):
        body = ""
    haystack = f"{e} {body}".lower()
    return any(marker in haystack for marker in _TRANSIENT_400_MARKERS)


async def send_request(
    llm: AsyncOpenAI,
    session: AgentSession,
    tools: list[dict],
    max_tokens: int,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    temperature: float = 0.6,
    reasoning_effort: str | None = None,
    request_log_path: str | None = None,
    config: Config | None = None,
):
    """
    Send request to LLM with error handling and retry logic.

    Args:
        llm: The async OpenAI client.
        session: The current session containing messages and model identifier.
        tools: List of tool definitions.
        max_retries: Maximum number of retry attempts (default: 3).
        retry_delay: Base delay between retries in seconds (default: 1.0).
        temperature: Fallback sampling temperature, used only when config is
            None. With a config, the routed model's per-model values apply.
        reasoning_effort: Fallback effort (config is None); when set, sent
            INSTEAD of temperature — reasoning models reject temperature.

    Returns:
        Streaming response from LLM

    Raises:
        APIError: If the API request fails after all retries.
        RateLimitError: If rate limit is exceeded.
        APIConnectionError: If connection to API fails.
    """
    # Normalize messages once — deterministic, no need to redo per retry.
    # Handles both list format (multimodal) and string format.
    normalized_messages = []
    for msg in session.messages:
        normalized_msg = dict(msg)
        content = msg.get("content")
        # If content is a list of content blocks, keep it as-is (for multimodal)
        # but if it's a list with only text blocks in the wrong format, fix it.
        if isinstance(content, list):
            normalized_msg["content"] = normalize_blocks(content)
        normalized_messages.append(normalized_msg)

    # Capability-aware routing: if the selected model cannot handle the
    # modalities present, fall back to a capable same-provider model, or
    # strip the unsupported blocks (auto-strip on downgrade). Session
    # history is never mutated — routing applies to this request only.
    routed_model = session.model_identifier
    if config is not None:
        modalities = modalities_in_messages(normalized_messages)
        if modalities:
            routed_model, to_strip = route_model(
                config, session.model_identifier, modalities
            )
            if to_strip:
                normalized_messages = strip_unsupported_blocks(
                    normalized_messages, to_strip
                )

    # Per-model sampling: the ROUTED model's reasoning_effort XOR temperature
    # (reasoning models reject temperature). Without a config the explicit
    # args apply.
    if config is not None:
        sampling_params = sampling_params_for(config, routed_model)
    else:
        sampling_params = build_sampling_params(reasoning_effort, temperature)

    # Under --debug, dump the exact request payload (the append-only chat
    # history + params) so immutable-history analysis can diff consecutive
    # turns. Sits beside the response chunk log in the same chunk_log_dir.
    if request_log_path:
        request_payload = {
            "model": routed_model,
            "messages": normalized_messages,
            "tools": tools,
            **sampling_params,
            "max_tokens": max_tokens,
            "parallel_tool_calls": True,
            "stream_options": {"include_usage": True},
        }
        Path(request_log_path).write_text(
            json.dumps(request_payload, ensure_ascii=False, indent=2)
        )

    last_exception = None

    for attempt in range(max_retries):
        try:
            return await llm.chat.completions.create(
                model=routed_model,
                messages=normalized_messages,
                tools=tools,
                stream=True,
                **sampling_params,
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
            # Retryable: rate limit / server errors, plus the transient
            # provider-side multimodal ingest faults that arrive as a 400
            # (openai SDK never retries 4xx, but these are sporadic).
            retryable = hasattr(e, "status_code") and e.status_code in [
                429,
                500,
                502,
                503,
                504,
            ]
            if not retryable:
                retryable = _is_transient_provider_400(e)
            if retryable:
                last_exception = e
                if attempt < max_retries - 1:
                    delay = retry_delay * (2**attempt)  # Exponential backoff
                    logger.warning(
                        "Retryable provider error (attempt %d/%d): %s",
                        attempt + 1,
                        max_retries,
                        e,
                    )
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
        # record types (to_dict) or Pydantic model - serialize to dict
        if hasattr(value, "to_dict"):
            return _serialize_value(value.to_dict())
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
    tool_results: list[dict] | None = None,
) -> list[dict]:
    """
    Execute tool calls via MCP or ACP client terminal.

    Args:
        turn_id: Turn ID for ACP tool call IDs
        agent_id: Agent ID (internal key)
        tool_call_id: LLM tool call ID
        tool_results: Optional accumulator filled in-place, so callers can
            still see completed results when the call is cancelled mid-flight.

    Returns:
        List of tool results
    """
    session_id = session_from_agent_id(agent_id)
    if tool_results is None:
        tool_results = []
    use_acp_terminal = client_capabilities and getattr(
        client_capabilities, "terminal", False
    )
    fs_caps = getattr(client_capabilities, "fs", None) if client_capabilities else None
    use_acp_write = fs_caps and getattr(fs_caps, "write_text_file", False)
    use_acp_read = fs_caps and getattr(fs_caps, "read_text_file", False)
    try:
        return await _execute_tool_calls_inner(
            conn=conn,
            session_id=session_id,
            client_capabilities=client_capabilities,
            turn_id=turn_id,
            config=config,
            mcp_clients=mcp_clients,
            sessions=sessions,
            agent_id=agent_id,
            tool_call_inputs=tool_call_inputs,
            tool_results=tool_results,
            logger=logger,
            hooks=hooks,
            snapshot_hooks=snapshot_hooks,
            use_acp_terminal=use_acp_terminal,
            use_acp_write=use_acp_write,
            use_acp_read=use_acp_read,
        )
    except asyncio.CancelledError:
        # Cancelled mid-execution: every tool call still needs a response so
        # the persisted assistant message (with tool_calls) stays valid. Keep
        # real results for tools that finished; placeholder for the rest.
        responded = {r["tool_call_id"] for r in tool_results}
        for tool_call in tool_call_inputs:
            if tool_call["id"] not in responded:
                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": TOOL_CALL_CANCELLED_MESSAGE,
                    }
                )
        raise


async def _execute_tool_calls_inner(
    conn: Client,
    session_id: str,
    client_capabilities: ClientCapabilities,
    turn_id: str,
    config: Config,
    mcp_clients: dict[str, MCPClient],
    sessions: dict[str, AgentSession],
    agent_id: str,
    tool_call_inputs: list[dict],
    tool_results: list[dict],
    logger: Logger,
    hooks: list[CommandHook],
    snapshot_hooks: list[FileSnapshotHook] | None,
    use_acp_terminal: bool,
    use_acp_write: bool,
    use_acp_read: bool,
) -> list[dict]:
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
            elif tool_name == "task":
                result_content = await execute_acp_task(
                    conn=conn,
                    turn_id=turn_id,
                    mcp_clients=mcp_clients,
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
    engine = get_engine(config.db_uri)

    # Prompt-start drain: completions that landed while this session was
    # idle — including everything queued while a cancelled turn was dead —
    # are waiting in the mailbox. Inject them ALL (priority order) before
    # the first model call so this prompt starts knowing its tasks
    # finished. This is the only path by which a queued reply resumes a
    # session: a user prompt. Nothing self-wakes.
    await consult_deliveries(engine, session, conn, session_id, logger)

    for turn in range(max_turns):
        # Top-of-loop checkpoint: highs that landed since the last
        # breakpoint surface immediately; lows keep holding to end of
        # turn by design.
        await consult_deliveries(
            engine, session, conn, session_id, logger, high_only=True
        )
        # Under --debug, log both the request payload and the response chunks
        # for this turn into the same chunk_log_dir (sibling filenames).
        chunk_log_path = None
        request_log_path = None
        if chunk_log_dir:
            # Include the loop index: turn_id is constant for the whole
            # prompt, so without it every turn overwrites the same request
            # file and only the LAST payload survives — exactly the turns
            # where a delivery was injected would be lost.
            chunk_log_path = str(
                Path(chunk_log_dir) / f"turn-{turn:03d}-{turn_id}.jsonl"
            )
            request_log_path = str(
                Path(chunk_log_dir) / f"turn-{turn:03d}-{turn_id}-request.json"
            )

        response = await send_request(
            llm,
            session,
            tools,
            config.MAX_TOKENS,
            max_retries=config.max_retries_per_step,
            request_log_path=request_log_path,
            config=config,
        )
        state_accumulator = state_accumulators.get(
            session_id, {"thinking": [], "content": [], "tool_calls": {}}
        )
        thinking, content, tool_call_inputs, usage = [], [], [], None

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

            # Persist whatever tool calls the stream already produced, EACH
            # with a synthetic "cancelled" tool response. The API requires
            # every tool_call_id in an assistant message to be followed by a
            # tool message responding to it — so we never persist a tool call
            # without its response, and we never silently drop one either.
            # Incomplete calls (no id or no name yet — cancelled very early)
            # are filtered out since they can't be addressed in history.
            tool_call_inputs, _ = process_tool_call_inputs(
                state_accumulator["tool_calls"]
            )
            tool_call_inputs = [
                tc
                for tc in tool_call_inputs
                if tc["id"] and tc["function"]["name"]
            ]
            await session.add_assistant_response(
                state_accumulator["thinking"],
                state_accumulator["content"],
                tool_call_inputs,
                logger,
                usage,
            )
            if tool_call_inputs:
                await session.add_tool_response(
                    cancelled_tool_results(tool_call_inputs), logger
                )
            # bg semantics: cancelling the parent does NOT touch its
            # subagents — they keep running, their completions still land
            # in the mailbox, and the model cancels them itself via
            # task(CancelTurn) if it wants to.
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

        # Per-model compaction threshold, resolved LIVE from the session's
        # CURRENT model — the user can switch models mid-session
        # (set_config_option), so this is never cached at session init.
        # Models without their own max_compact_tokens keep the global rate.
        compact_threshold = max_compact_tokens_for(config, session.model_identifier)

        # Expose token usage to the ACP client (context % against the compaction
        # threshold). usage_update is stabilized in v1; Zed renders it as a
        # context-meter. Best-effort: a dead client must not kill the react loop.
        if usage and usage.get("total_tokens"):
            try:
                await conn.session_update(
                    session_id=session_id,
                    update=UsageUpdate(
                        session_update="usage_update",
                        used=int(usage["total_tokens"]),
                        size=compact_threshold,
                    ),
                )
            except Exception:
                logger.warning("Failed to send usage_update to ACP client", exc_info=True)

        # 1. Check your token threshold
        if usage and usage["total_tokens"] > compact_threshold:
            logger.info("Token threshold crossed. Initiating compaction...")

            yield {
                "type": "compaction",
                "token": f"\n\nCompaction threshold of {compact_threshold} reached — compacting conversation history...\n\n",
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

        # This ends the react loop — NO TOOLS!! But with bg-task semantics,
        # "model done" ends the turn ONLY when the mailbox is empty AND no
        # delegation is in flight. Consult STATE (no polling): if
        # deliveries landed while we were working, inject them all and
        # keep the turn going. If a subagent is still RUNNING, withhold
        # end_turn and hold the loop open — alive and cancellable — until
        # its reply lands. Cancel during the hold kills THIS TURN ONLY:
        # subagents keep running, their replies stay queued in the mailbox
        # until the user's next prompt (prompt-start drain). Nothing
        # self-wakes.
        if not tool_call_inputs and len(content) > 0:
            await session.add_assistant_response(
                thinking,
                content,
                [],
                logger,
                usage,
            )
            if await consult_deliveries(
                engine, session, conn, session_id, logger
            ):
                continue
            injected = False
            try:
                while running_tasks(engine, session_id):
                    await asyncio.sleep(DELIVERY_POLL_S)
                    if await consult_deliveries(
                        engine, session, conn, session_id, logger
                    ):
                        injected = True
                        break
            except asyncio.CancelledError:
                logger.info(
                    "Cancelled while holding for a delegated task — "
                    "subagents keep running, replies stay queued"
                )
                raise
            if injected:
                continue
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
            tool_results: list[dict] = []
            try:
                await execute_tool_calls(
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
                    tool_results=tool_results,
                )
            except asyncio.CancelledError:
                # Cancelled mid-tool-execution. execute_tool_calls already
                # filled "cancelled" placeholders for every call that has no
                # result, so persist the assistant message WITH its tool calls
                # and the full response set — history stays valid.
                logger.info(
                    "Cancelled during tool execution - persisting assistant "
                    "message and tool responses before re-raising"
                )
                await session.add_assistant_response(
                    thinking,
                    content,
                    tool_call_inputs,
                    logger,
                    usage,
                )
                await session.add_tool_response(tool_results, logger)
                # bg semantics: cancelling the parent does NOT touch its
                # subagents — they keep running and their completions still
                # land in the mailbox; the model cancels them itself via
                # task(CancelTurn) if it wants to.
                raise

            await session.add_assistant_response(
                thinking,
                content,
                tool_call_inputs,
                logger,
                usage,
            )
            await session.add_tool_response(tool_results, logger)
            # Between-batch: inject HIGH-priority deliveries immediately so
            # the model sees cancels/urgencies on the next turn; low
            # priority holds until end of prompt (consulted at end-turn).
            await consult_deliveries(
                engine, session, conn, session_id, logger, high_only=True
            )
