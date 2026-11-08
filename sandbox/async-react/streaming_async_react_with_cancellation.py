#!/usr/bin/env python3
"""Minimal streaming react loop: MCP tools, OpenAI chat completions, cancellation.

The whole agent in one file — no ACP, no database, no compaction. Stream,
accumulate, call the tool, append, loop. Same general idea as the original
sandbox script; the wire details are what crow-cli does today
(``crow_cli/agent2/llm.py``, ``agent2/tools.py``, ``agent/session.py``).

    uv run python sandbox/async-react/streaming_async_react_with_cancellation.py
    ... --cancel-after 10    cancel mid-turn, inspect the history left behind
    ... --raw                dump every request body
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from fastmcp import Client
from mcp.types import ImageContent
from openai import APIConnectionError, AsyncOpenAI, RateLimitError
from openai._exceptions import APITimeoutError

API_KEY = os.getenv("ALIBABA_API_KEY")
BASE_URL = os.getenv("ALIBABA_BASE_URL", "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1")
MODEL = os.getenv("REACT_MODEL", "glm-5.2")
MAX_TOKENS = 8192
CANCELLED_MESSAGE = "Tool call cancelled by user"
MCP_CONFIG = {
    "mcpServers": {
        "crow-mcp": {
            "transport": "stdio",
            "command": str(Path.home() / ".agents/crow/src/crow-cli/.venv/bin/crow-cli"),
            "args": ["mcp2"],
        }
    }
}


def configure_provider(raw: bool = False) -> AsyncOpenAI:
    async def log_request(request):
        print(f"\n{'=' * 20} RAW REQUEST {'=' * 20}\n{request.read().decode()}\n")

    hooks = {"request": [log_request]} if raw else None
    return AsyncOpenAI(
        api_key=API_KEY,
        base_url=BASE_URL,
        http_client=httpx.AsyncClient(event_hooks=hooks) if hooks else None,
    )


async def get_tools(mcp_client: Client) -> list[dict]:
    """MCP schemas -> OpenAI tool definitions. ``or ""`` because a null
    description is rejected by some providers and many MCP tools omit it."""
    return [
        {
            "type": "function",
            "function": {"name": t.name, "description": t.description or "", "parameters": t.inputSchema},
        }
        for t in await mcp_client.list_tools()
    ]


async def send_request(lm, messages, model, tools, max_retries=3):
    """Open a streaming completion, retrying what the SDK will not.

    ``include_usage`` is what makes the last chunk carry token counts — and that
    chunk has ``choices: []``, which is why the accumulator guards the index.
    ``parallel_tool_calls`` is not a sampling param and omitting it is NOT false,
    so it is always sent. ``reasoning_effort`` XOR ``temperature``: reasoning
    models reject temperature.
    """
    for attempt in range(max_retries):
        try:
            return await lm.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                stream=True,
                max_tokens=MAX_TOKENS,
                stream_options={"include_usage": True},
                temperature=0.6,
                parallel_tool_calls=False,
            )
        except (APITimeoutError, RateLimitError, APIConnectionError):
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2**attempt)


@dataclass
class StreamState:
    """What the stream has produced so far, owned OUTSIDE the stream: a cancel
    mid-stream still has to persist a valid assistant message, so partial
    accumulation is not scratch state, it is the record."""

    thinking: list[str] = field(default_factory=list)
    content: list[str] = field(default_factory=list)
    tool_calls: dict[int, dict] = field(default_factory=dict)  # by delta index
    usage: dict | None = None

    def reset(self) -> None:
        self.thinking.clear()
        self.content.clear()
        self.tool_calls.clear()
        self.usage = None


def accumulate_chunk(chunk, state: StreamState) -> list[tuple[str, object]]:
    """Fold one chunk into ``state``; return the new tokens by kind.

    Reasoning, content and tool calls are three INDEPENDENT checks — one chunk
    can carry reasoning AND content (the transition boundary), and an if/else
    between them silently drops one.
    """
    if getattr(chunk, "usage", None) is not None:
        state.usage = {
            "prompt_tokens": chunk.usage.prompt_tokens,
            "completion_tokens": chunk.usage.completion_tokens,
            "total_tokens": chunk.usage.total_tokens,
        }
    if not chunk.choices:
        return []
    delta = chunk.choices[0].delta
    tokens: list[tuple[str, object]] = []

    reasoning = getattr(delta, "reasoning_content", None)
    if reasoning:
        state.thinking.append(reasoning)
        tokens.append(("thinking", reasoning))
    if delta.content:
        state.content.append(delta.content)
        tokens.append(("content", delta.content))

    for call in delta.tool_calls or ():
        # ``index`` is the only reliable accumulation key: it is on every delta,
        # while id/type/name arrive exactly once, in the first one. Keying by id
        # breaks parallel calls, and breaks on alibaba compatible-mode, which
        # sends id:"" and name:"" on every continuation delta — `is not None`
        # passes, the real values are overwritten, the tool name is gone. Hence
        # truthiness below, not identity.
        slot = state.tool_calls.setdefault(call.index, {"id": "", "function_name": "", "arguments": []})
        if call.id:
            slot["id"] = call.id
        if call.function and call.function.name:
            slot["function_name"] = call.function.name
            tokens.append(("tool_call", (call.function.name, call.function.arguments or "")))
        if call.function and call.function.arguments:
            slot["arguments"].append(call.function.arguments)
            if not any(kind == "tool_call" for kind, _ in tokens):
                tokens.append(("tool_args", call.function.arguments))
    return tokens


def build_tool_calls(state: StreamState) -> list[dict]:
    """Deltas -> OpenAI ``tool_calls``, by index, argument JSON repaired.

    The id is the LLM's and stays the LLM's — the only link between the assistant
    message and its tool results. A provider that never sent one gets "" on both
    sides, never a generated UUID. Repair happens here, before the string enters
    history: a model that truncates its arguments would otherwise poison every
    later request, since the assistant message is re-sent each turn.
    """
    calls = []
    for _, slot in sorted(state.tool_calls.items()):
        arguments = "".join(slot["arguments"])
        try:
            json.loads(arguments)
        except (json.JSONDecodeError, TypeError, ValueError):
            arguments += "}" * (arguments.count("{") - arguments.count("}"))
            arguments += "]" * (arguments.count("[") - arguments.count("]"))
            try:
                json.loads(arguments)
            except (json.JSONDecodeError, TypeError, ValueError):
                arguments = "{}"
        calls.append(
            dict(id=slot["id"], type="function",
                 function=dict(name=slot["function_name"], arguments=arguments))
        )
    return calls


def deserialize_args(data):
    """Recursively decode JSON strings nested inside arguments — models
    double-encode constantly, and handing a tool the string '{"a": 1}' where it
    wanted an object is a spurious failure. Only strings starting { or [ are
    attempted, so a bare "1" stays a string. This is the top-level parse too: a
    well-formed call comes back a dict, anything else is malformed."""
    if isinstance(data, str):
        if data.startswith(("{", "[")):
            try:
                return deserialize_args(json.loads(data))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        return data
    if isinstance(data, dict):
        return {k: deserialize_args(v) for k, v in data.items()}
    if isinstance(data, list):
        return [deserialize_args(item) for item in data]
    return data


def mcp_to_llm(mcp_content) -> object:
    """MCP content blocks -> OpenAI tool-message content: a list only when there
    is something a string cannot carry (an image), otherwise the plain text. The
    obvious ``result.content[0].text`` dies on an empty result and on any
    non-text block."""
    if not mcp_content:
        return ""
    blocks = []
    for item in mcp_content:
        if isinstance(item, ImageContent):
            blocks.append({"type": "image_url", "image_url": {"url": f"data:{item.mimeType};base64,{item.data}"}})
        else:
            blocks.append({"type": "text", "text": str(getattr(item, "text", item))})
    if len(blocks) == 1 and blocks[0]["type"] == "text":
        return blocks[0]["text"]
    return blocks


async def execute_tool_calls(mcp_client, tool_call_inputs, tool_results: list[dict]):
    """Run a batch, filling ``tool_results`` IN PLACE — so a cancel mid-batch
    still shows the calls that finished, and every call with no result can get a
    placeholder, because the assistant message about to be persisted carries the
    tool_calls and the API requires a response for each one.

    A tool that raises is a tool result, not an exception: the model gets to see
    the error and recover, which it cannot do if the turn dies.
    """
    try:
        for tool_call in tool_call_inputs:
            name = tool_call["function"]["name"]
            raw_args = tool_call["function"]["arguments"]
            args = deserialize_args(raw_args)
            if not isinstance(args, dict):
                tool_call["function"]["arguments"] = "{}"  # in place: history is re-sent
                content = (f"Error: malformed arguments for '{name}': {raw_args!r}. "
                           "Retry with valid JSON matching the tool schema.")
            else:
                try:
                    # call_tool_mcp, not call_tool: the raw protocol result, with
                    # isError and every content block, and no raise on tool error.
                    result = await mcp_client.call_tool_mcp(name, args)
                    content = mcp_to_llm(result.content)
                    if result.isError:
                        content = f"Error: {content}"
                except Exception as exc:
                    content = f"Error: {exc}"
            tool_results.append(dict(role="tool", tool_call_id=tool_call["id"], content=content))
        return tool_results
    except asyncio.CancelledError:
        responded = {r["tool_call_id"] for r in tool_results}
        for tool_call in tool_call_inputs:
            if tool_call["id"] not in responded:
                tool_results.append(
                    dict(role="tool", tool_call_id=tool_call["id"], content=CANCELLED_MESSAGE)
                )
        raise


def add_response_to_messages(messages, state, tool_call_inputs, tool_results):
    """ONE assistant message, then one tool message per call, in that order.

    Not a content message plus a separate tool_calls message: the tool_calls ride
    on the assistant turn and the results must follow it immediately, each keyed
    by an id from it. ``content`` is always present, possibly "" — an assistant
    message with no content key is another thing providers reject.
    """
    if not (state.content or state.thinking or tool_call_inputs):
        return messages  # an empty completion persists nothing
    thinking = "".join(state.thinking)
    msg = {"role": "assistant", "content": "".join(state.content)}
    if thinking:
        msg["reasoning_content"] = thinking
    if tool_call_inputs:
        msg["tool_calls"] = tool_call_inputs
    messages.append(msg)
    messages.extend(tool_results)
    return messages


async def react_loop(messages, mcp_client, lm, model, tools, max_turns=50000):
    """Stream -> accumulate -> run tools -> append -> loop.

    Yields ``{"type", "token"}`` for whoever is rendering and mutates ``messages``
    in place, so a cancel leaves resumable history behind without a callback —
    the caller already owns the list. Cancellation is a real CancelledError, not
    a polled flag: it lands wherever the loop is actually waiting, which is the
    only place a partial stream exists.
    """
    state = StreamState()
    for _ in range(max_turns):
        response = await send_request(lm, messages, model, tools)
        state.reset()
        try:
            async for chunk in response:
                for kind, token in accumulate_chunk(chunk, state):
                    yield {"type": kind, "token": token}
        except asyncio.CancelledError:
            # Persist what arrived. Incomplete calls — no id or no name yet — are
            # dropped: they cannot be addressed in history, and an unaddressable
            # tool_call is a rejected request.
            calls = [c for c in build_tool_calls(state) if c["id"] and c["function"]["name"]]
            add_response_to_messages(
                messages, state, calls,
                [dict(role="tool", tool_call_id=c["id"], content=CANCELLED_MESSAGE) for c in calls],
            )
            raise

        tool_call_inputs = build_tool_calls(state)
        if not tool_call_inputs:
            add_response_to_messages(messages, state, [], [])
            yield {"type": "usage", "token": state.usage}
            return

        tool_results: list[dict] = []
        try:
            await execute_tool_calls(mcp_client, tool_call_inputs, tool_results)
        except asyncio.CancelledError:
            add_response_to_messages(messages, state, tool_call_inputs, tool_results)
            raise  # placeholders already filled for every unanswered call
        add_response_to_messages(messages, state, tool_call_inputs, tool_results)


def make_renderer():
    last = None

    def render(chunk):
        nonlocal last
        kind, token = chunk["type"], chunk["token"]
        if last == "tool_args" and kind != "tool_args":
            print(")")
        if kind in ("thinking", "content"):
            if last != kind:
                print(("\n" if last else "") + f"[{kind}] ", end="")
            print(token, end="", flush=True)
        elif kind == "tool_call":
            print(f"\n[tool] {token[0]}({token[1]}", end="", flush=True)
        elif kind == "tool_args":
            print(token, end="", flush=True)
        elif kind == "usage":
            print(f"\n[usage] {token}")
        last = kind

    return render


async def run(cancel_after: float | None, raw: bool) -> list[dict]:
    mcp_client = Client(MCP_CONFIG)
    lm = configure_provider(raw)
    render = make_renderer()
    messages = [
        dict(role="system", content="You are a helpful assistant named Crow."),
        dict(role="user", content="search for machine learning papers with your search tool"),
    ]
    async with mcp_client:
        tools = await get_tools(mcp_client)
        if cancel_after:
            task = asyncio.current_task()
            asyncio.get_running_loop().call_later(cancel_after, task.cancel)
            print(f"[cancelling in {cancel_after}s]")
        try:
            async for chunk in react_loop(messages, mcp_client, lm, MODEL, tools):
                render(chunk)
        except asyncio.CancelledError:
            # The point of the exercise: history is still valid to resume from.
            # Every assistant tool_calls entry has a matching tool response.
            print(f"\n[cancelled — {len(messages)} messages in history]")
            for msg in messages[2:]:
                print(" ", json.dumps(msg, ensure_ascii=False)[:220])
    return messages


if __name__ == "__main__":
    argv = sys.argv[1:]
    cancel = float(argv[argv.index("--cancel-after") + 1]) if "--cancel-after" in argv else None
    asyncio.run(run(cancel, "--raw" in argv))
