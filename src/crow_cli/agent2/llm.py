"""Talking to the model. Protocol-free, session-free, emitter-free.

Ported from ``agent/react.py:135-680`` — the half of v1's react module that
has nothing to do with ACP. Two changes of substance:

* :func:`send_request` takes ``messages`` and ``model`` instead of an
  ``AgentSession``, so it can be tested without a database and reused by
  compaction and subagents alike.
* :func:`stream` takes callbacks instead of yielding ``("content", token)``
  tuples. v1 yielded, react_loop re-wrapped each into ``{"type": ...}``, and
  ``AcpAgent.prompt`` interleaved 230 lines of that against its own direct
  ``conn.session_update`` calls. Here the caller passes emitter-bound
  callbacks and the stream never becomes a second output channel.

Everything hard-won is preserved verbatim: exponential backoff, the
transient-provider-400 classification (DashScope's multimodal ingest timeout
arrives as a 400, which the openai SDK never retries), capability-aware model
routing with auto-strip on downgrade, and the JSON repair for models that
emit malformed tool arguments.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx
from openai import APIConnectionError, APIError, AsyncOpenAI, RateLimitError
from openai._exceptions import APITimeoutError

from crow_cli.agent.model_routing import (
    modalities_in_messages,
    route_model,
    strip_unsupported_blocks,
)
# Pure file-URI helpers — #L12:20 range parsing and url2pathname. They live in
# a v1 module that also holds v1's protocol-shaped prompt code, but these two
# have no protocol in them, and a second copy of the range grammar is a second
# thing to keep in step.
from crow_cli.agent.prompt import context_fetcher, uri_to_path
from crow_cli.config import Config, build_sampling_params, sampling_params_for

logger = logging.getLogger(__name__)

#: Provider-side transient faults that surface as HTTP 400 and so are never
#: retried by the openai SDK (it only retries 429/5xx/connection). Observed in
#: the wild: DashScope's server-side multimodal ingest timing out while
#: processing a large image payload. Sporadic => retryable.
TRANSIENT_400_MARKERS = (
    "download multimodal file timed out",
    "multimodal file timed out",
    "ingest timeout",
    "ingest timed out",
)

RETRYABLE_STATUS = (429, 500, 502, 503, 504)

#: Callbacks are awaited, so the react loop can hand the emitter straight in.
TokenSink = Callable[[str], Awaitable[None]]


def normalize_blocks(content: Any) -> list[dict]:
    """Coerce stored message content to OpenAI block form.

    History holds both bare strings (old rows) and block lists (multimodal);
    blank text blocks are dropped because some providers reject them.
    """
    normalized: list[dict] = []
    for block in content:
        if isinstance(block, str):
            normalized.append({"type": "text", "text": block})
        elif isinstance(block, dict):
            if block.get("type") == "text" and not block.get("text", "").strip():
                continue
            normalized.append(block)
    return normalized


def normalize_messages(messages: list[dict]) -> list[dict]:
    out = []
    for msg in messages:
        copy = dict(msg)
        if isinstance(copy.get("content"), list):
            copy["content"] = normalize_blocks(copy["content"])
        out.append(copy)
    return out


def _uri(value: Any) -> Optional[str]:
    """A wire ``uri`` as a plain string, or None.

    v2 types every ``uri`` as ``AnyUrl``, which is not a ``str`` — it has no
    ``.startswith``, and ``re.search`` refuses it. Both ways of failing land in
    the ``except`` blocks below, which log and drop the block, so what the
    client attached reaches the model as nothing at all. And a client is
    entitled to attach: a ``ResourceLink`` is BASELINE — the spec requires
    every agent to accept text and resource links in a prompt, capability or
    no — and an image is what advertising ``prompt.image`` invites. v1 typed
    these ``str``, which is why the port did not notice. ``str()`` is faithful apart from percent-encoding, and
    ``uri_to_path`` unquotes on the way back to a path.
    """
    return None if value is None else str(value)


async def normalize_prompt(blocks: Any, log: Any = None) -> list[dict]:
    """Wire content blocks -> OpenAI user-message content.

    Duck-typed on ``.type`` so this module still imports no protocol package:
    the driver hands it whatever the wire produced.

    v2 renamed two of v1's blocks, and getting them backwards silently loses
    the user's attachment:

    ==========================  =========================================
    v1                          v2
    ==========================  =========================================
    ``resource`` (had ``.resource.text``)   ``resource`` — an EMBEDDED payload,
                                  ``.resource`` is Text- or BlobResourceContents
    ``resource_link``            ``resource_link`` — but the model is now
                                  ``ResourceContentBlock`` (a bare uri/name)
    ==========================  =========================================

    An embedded blob whose mime type is an image becomes an ``image_url``
    rather than text: v1 could not receive one, v2 can, and base64 in a text
    block is a way of spending context to say nothing.
    """
    log = log or logger
    out: list[dict] = []
    for block in blocks or ():
        kind = getattr(block, "type", None) or (
            block.get("type") if isinstance(block, dict) else None
        )
        get = (
            (lambda name, default=None: block.get(name, default))
            if isinstance(block, dict)
            else (lambda name, default=None: getattr(block, name, default))
        )

        if kind == "text":
            text = get("text")
            if text:  # the API rejects empty text blocks
                out.append({"type": "text", "text": text})

        elif kind == "image":
            url = await _image_url(
                get("data"), _uri(get("uri")), get("mime_type"), log
            )
            if url:
                out.append({"type": "image_url", "image_url": {"url": url}})

        elif kind == "resource_link":
            uri = _uri(get("uri"))
            log.info("resource uri: %s", uri)
            try:
                fetched = context_fetcher(uri, log)
            except Exception as exc:
                log.error("could not fetch resource %s: %s", uri, exc)
                continue
            if fetched:
                out.append({"type": "text", "text": fetched})

        elif kind == "resource":
            resource = get("resource")
            rget = (
                (lambda name, default=None: resource.get(name, default))
                if isinstance(resource, dict)
                else (lambda name, default=None: getattr(resource, name, default))
            )
            uri = rget("uri") or ""
            text = rget("text")
            if text is not None:
                # v1's shape, kept: the location travels with the content so
                # the model can cite the file it came from.
                out.append({"type": "text", "text": f"file_location:{uri}\n{text}"})
                continue
            blob = rget("blob")
            if blob:
                mime = rget("mime_type") or "image/png"
                if mime.startswith("image/"):
                    out.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{blob}"},
                        }
                    )
                else:
                    log.warning("dropping non-image embedded blob (%s) from %s", mime, uri)
            else:
                log.warning("embedded resource with neither text nor blob: %s", uri)

        elif kind == "audio":
            log.warning("audio content blocks are not supported — dropped")

        else:
            log.warning("unhandled prompt block type %r — dropped", kind)
    return out


async def _image_url(
    data: Optional[str], uri: Optional[str], mime_type: Optional[str], log: Any
) -> Optional[str]:
    """A base64 data URL for an image block, fetching ``uri`` when needed.

    A data URL rather than a remote one because that is what llama.cpp
    accepts; a provider that could take the URL directly still takes this.
    """
    if data:
        return f"data:{mime_type or 'image/png'};base64,{data}"
    if not uri:
        log.warning("image block with neither data nor uri — dropped")
        return None
    try:
        if uri.startswith("file://"):
            with open(uri_to_path(uri), "rb") as fh:
                raw = fh.read()
        elif uri.startswith(("http://", "https://")):
            async with httpx.AsyncClient() as client:
                raw = (await client.get(uri)).content
        else:
            log.warning("unsupported image URI scheme: %s", uri)
            return None
    except Exception as exc:
        log.error("failed to fetch image from %s: %s", uri, exc)
        return None
    mime = mime_type or mimetypes.guess_type(uri)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def is_transient_provider_400(exc: APIError) -> bool:
    if getattr(exc, "status_code", None) != 400:
        return False
    try:
        body = json.dumps(getattr(exc, "body", None), ensure_ascii=False)
    except (TypeError, ValueError):
        body = ""
    haystack = f"{exc} {body}".lower()
    return any(marker in haystack for marker in TRANSIENT_400_MARKERS)


async def send_request(
    llm: AsyncOpenAI,
    messages: list[dict],
    model: str,
    tools: list[dict],
    max_tokens: int,
    *,
    config: Optional[Config] = None,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    temperature: float = 0.6,
    reasoning_effort: Optional[str] = None,
    request_log_path: Optional[str] = None,
) -> Any:
    """Open a streaming chat completion, retrying transient provider faults.

    With a ``config`` the routed model's own sampling params apply
    (``reasoning_effort`` XOR ``temperature`` — reasoning models reject
    temperature) and capability routing may swap the model or strip
    unsupported blocks. Without one the explicit args are used. History is
    never mutated: routing applies to this request only.
    """
    normalized = normalize_messages(messages)

    routed_model = model
    if config is not None:
        modalities = modalities_in_messages(normalized)
        if modalities:
            routed_model, to_strip = route_model(config, model, modalities)
            if to_strip:
                normalized = strip_unsupported_blocks(normalized, to_strip)
        sampling = sampling_params_for(config, routed_model)
    else:
        sampling = build_sampling_params(reasoning_effort, temperature)

    if request_log_path:
        payload = {
            "model": routed_model,
            "messages": normalized,
            "tools": tools,
            **sampling,
            "max_tokens": max_tokens,
            "parallel_tool_calls": True,
            "stream_options": {"include_usage": True},
        }
        Path(request_log_path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2)
        )

    for attempt in range(max_retries):
        try:
            return await llm.chat.completions.create(
                model=routed_model,
                messages=normalized,
                tools=tools,
                stream=True,
                **sampling,
                max_tokens=max_tokens,
                parallel_tool_calls=True,
                stream_options={"include_usage": True},
            )
        except (APITimeoutError, RateLimitError, APIConnectionError):
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(retry_delay * (2**attempt))
        except APIError as exc:
            retryable = getattr(exc, "status_code", None) in RETRYABLE_STATUS
            if not retryable:
                retryable = is_transient_provider_400(exc)
            if not retryable:
                raise
            logger.warning(
                "Retryable provider error (attempt %d/%d): %s",
                attempt + 1,
                max_retries,
                exc,
            )
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(retry_delay * (2**attempt))

    raise RuntimeError("send_request exhausted retries")  # pragma: no cover


@dataclass
class StreamState:
    """What the stream has produced so far, readable from outside.

    A cancel mid-stream still has to persist a valid assistant message — the
    API requires every ``tool_call_id`` in one to have a matching tool
    response — so partial accumulation is not scratch state, it is the record.
    Owned by the driver, passed in, mutated in place.
    """

    thinking: list[str] = field(default_factory=list)
    content: list[str] = field(default_factory=list)
    tool_calls: dict[int, dict] = field(default_factory=dict)

    def reset(self) -> None:
        self.thinking.clear()
        self.content.clear()
        self.tool_calls.clear()


@dataclass
class Completion:
    """One finished LLM call."""

    thinking: str
    content: str
    tool_calls: list[dict]
    repaired: list[bool]
    usage: Optional[dict]

    @property
    def has_tools(self) -> bool:
        return bool(self.tool_calls)


def _accumulate_chunk(chunk: Any, state: StreamState) -> list[tuple[str, Any]]:
    """Fold one stream chunk into ``state``; return the new tokens by kind.

    A single chunk can carry reasoning_content AND content (the transition
    boundary), so the return is a list, not a single token. Tool-call deltas
    are index-keyed: providers split one call's arguments across many chunks
    and the index is the only thing tying them together.
    """
    if not chunk.choices:
        return []
    delta = chunk.choices[0].delta
    tokens: list[tuple[str, Any]] = []

    reasoning = getattr(delta, "reasoning_content", None)
    if reasoning:
        state.thinking.append(reasoning)
        tokens.append(("thinking", reasoning))

    if delta.content:
        state.content.append(delta.content)
        tokens.append(("content", delta.content))

    for call in delta.tool_calls or ():
        slot = state.tool_calls.setdefault(
            call.index, {"id": "", "function_name": "", "arguments": []}
        )
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


def build_tool_calls(state: StreamState) -> tuple[list[dict], list[bool]]:
    """Assemble accumulated deltas into OpenAI tool_calls, repairing bad JSON.

    Some models emit malformed arguments; sending those back in history is an
    API error, so unbalanced braces/brackets are closed and, failing that, the
    arguments fall back to ``{}``. The parallel ``repaired`` flags let the
    caller log which calls were touched.
    """
    calls: list[dict] = []
    repaired: list[bool] = []
    for _, slot in sorted(state.tool_calls.items()):
        arguments = "".join(slot["arguments"])
        was_repaired = False
        try:
            json.loads(arguments)
        except (json.JSONDecodeError, TypeError, ValueError):
            was_repaired = True
            arguments += "}" * (arguments.count("{") - arguments.count("}"))
            arguments += "]" * (arguments.count("[") - arguments.count("]"))
            try:
                json.loads(arguments)
            except (json.JSONDecodeError, TypeError, ValueError):
                arguments = "{}"
        calls.append(
            dict(
                id=slot["id"],
                type="function",
                function=dict(name=slot["function_name"], arguments=arguments),
            )
        )
        repaired.append(was_repaired)
    return calls, repaired


def serialize_chunk(chunk: Any) -> Any:
    """Dump a raw stream chunk for --debug logging, assuming nothing."""

    def value(v: Any) -> Any:
        if isinstance(v, (str, int, float, bool, type(None))):
            return v
        if isinstance(v, list):
            return [value(x) for x in v]
        if isinstance(v, dict):
            return {k: value(x) for k, x in v.items()}
        if hasattr(v, "to_dict"):
            return value(v.to_dict())
        if hasattr(v, "model_dump"):
            return value(v.model_dump())
        return {
            a: value(getattr(v, a))
            for a in dir(v)
            if not a.startswith("_") and not callable(getattr(v, a))
        }

    return value(chunk)


async def stream(
    response: Any,
    state: StreamState,
    *,
    on_thought: Optional[TokenSink] = None,
    on_content: Optional[TokenSink] = None,
    chunk_log_path: Optional[str] = None,
) -> Completion:
    """Consume a streaming completion into ``state``, fanning tokens out.

    Cancellation propagates: the caller persists ``state`` on the way out,
    which is why accumulation lives in a passed-in object rather than locals.
    """
    usage: Optional[dict] = None
    log_file = open(chunk_log_path, "a") if chunk_log_path else None
    try:
        async for chunk in response:
            if getattr(chunk, "usage", None) is not None:
                usage = {
                    "prompt_tokens": getattr(chunk.usage, "prompt_tokens", None),
                    "completion_tokens": getattr(chunk.usage, "completion_tokens", None),
                    "total_tokens": getattr(chunk.usage, "total_tokens", None),
                }
            if log_file is not None:
                log_file.write(json.dumps(serialize_chunk(chunk), ensure_ascii=False) + "\n")
                log_file.flush()
            for kind, token in _accumulate_chunk(chunk, state):
                if kind == "thinking" and on_thought is not None:
                    await on_thought(token)
                elif kind == "content" and on_content is not None:
                    await on_content(token)
    finally:
        if log_file is not None:
            log_file.close()

    calls, repaired = build_tool_calls(state)
    return Completion(
        thinking="".join(state.thinking),
        content="".join(state.content),
        tool_calls=calls,
        repaired=repaired,
        usage=usage,
    )
