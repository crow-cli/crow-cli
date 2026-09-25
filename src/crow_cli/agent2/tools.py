"""Tool execution, on the emitter.

One dispatch decision matters here, and it is the only one v2 forces:

    if tool_name == "execute":  a terminal
    else:                       a tool call

Everything else is the shape it always was — call MCP, put the result on the
wire, hand the model its text. But ``execute`` is where the agent lives (a
spawned crow agent is handed ``execute`` and nothing else; its file, web,
memory, vision and delegation work happens through subtools ambient in the
kernel), and ACP v2 gave terminals to the agent, so that one call gets the
full terminal treatment: a ``terminal_id``, live ``terminal_output_chunk``
bytes relayed from MCP progress notifications, a ``terminal_update`` snapshot
and exit status, and a ``terminal`` content reference tying the call to the
terminal. Two audiences, one execution — raw ANSI for the human watching,
stripped text for the model reading.

v1 could not do this. It had a ``terminal`` tool that drove a PTY *in the
client* behind ``ctx.terminal_via_client``, and ``execute`` was just another
MCP call whose output the client rendered as the same text the model read. v2
deleted ``clientCapabilities.terminal`` along with ``terminal/create|output|
release|wait_for_exit|kill``, so the client-driven path is not ported — it is
gone, and the capability gate that guarded it with it.

Also collapsed here: v1 built every tool call in three beats — a ``tool_call``
create, then ``tool_call_update`` patches. v2 has no ``tool_call``;
``tool_call_update`` is an upsert keyed on ``toolCallId`` where first sight
creates. So one call per beat, and for the subtool drain — which emits rows
whose work is already finished — one call total.
"""

from __future__ import annotations

import asyncio
import base64
import difflib
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from acp.experimental.v2 import schema as v2
from mcp.types import ImageContent, TextContent
from sqlalchemy import select
from sqlalchemy import update as sa_update

from crow_cli.memory.db import get_engine
from crow_cli.memory.image_store import resolve_image_store
from crow_cli.memory.models import SubtoolCall

from .ctx import TurnCtx

logger = logging.getLogger(__name__)

#: Content for the synthetic tool response that keeps history valid when a
#: turn is cancelled after the model emitted tool calls. The API requires
#: every tool_call_id in an assistant message to have a matching tool response.
TOOL_CALL_CANCELLED_MESSAGE = "Tool call cancelled by user"


def cancelled_tool_results(tool_calls: list[dict]) -> list[dict]:
    """A "cancelled by user" tool response for every tool call."""
    return [
        {"role": "tool", "tool_call_id": tc["id"], "content": TOOL_CALL_CANCELLED_MESSAGE}
        for tc in tool_calls
    ]


# ---------------------------------------------------------------------------
# Pure helpers: kinds, arguments, content conversion
# ---------------------------------------------------------------------------


def tool_kind(tool_name: str) -> str:
    """Map a tool name to an ACP ToolKind.

    Substring rules, so an MCP server can name its tools anything sensible and
    still get the right icon. Orchestration names are exact-matched FIRST so
    the rules below do not misclassify them (``task_read`` would otherwise be
    "read", ``task_write`` "edit", ``send_prompt`` "execute").
    """
    if tool_name in (
        "send_prompt",
        "task",
        "task_read",
        "task_write",
        "task_send",
        "task_cancel",
    ):
        return "other"
    name = tool_name.lower()

    def match(*terms: str) -> bool:
        return any(term in name for term in terms)

    if match("read_file", "read", "view", "list_directory", "list"):
        return "read"
    if match("write_file", "write", "edit", "create", "str_replace"):
        return "edit"
    if match("delete", "remove"):
        return "delete"
    if match("move", "rename"):
        return "move"
    if match("search", "grep", "find"):
        return "search"
    if match("fetch", "download"):
        return "fetch"
    if match("terminal", "bash", "shell", "execute", "prompt"):
        return "execute"
    return "other"


def deserialize_args(data: Any) -> Any:
    """Recursively decode JSON strings nested inside arguments.

    Models double-encode constantly, and handing a tool the string
    ``'{"a": 1}'`` where it wanted an object is a spurious failure. Drills
    until nothing left decodes. Only strings starting ``{`` or ``[`` are
    attempted, so a bare ``"1"`` or ``"true"`` stays a string.
    """
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


def text_content(text: str) -> Any:
    return v2.ContentToolCallContent(content=v2.TextContentBlock(text=text))


def image_content(data_b64: str, mime_type: str) -> Any:
    # MCP uses mimeType (camelCase), ACP uses mime_type (snake_case).
    return v2.ContentToolCallContent(
        content=v2.ImageContentBlock(data=data_b64, mime_type=mime_type)
    )


def mcp_to_content(mcp_content: Any) -> list[Any]:
    """MCP content blocks -> v2 tool-call content for the client."""
    blocks = []
    for item in mcp_content or ():
        if isinstance(item, TextContent):
            blocks.append(text_content(item.text))
        elif isinstance(item, ImageContent):
            blocks.append(image_content(item.data, item.mimeType))
        else:
            text = getattr(item, "text", None)
            blocks.append(text_content(str(text if text is not None else item)))
    return blocks


def mcp_to_llm(mcp_content: Any) -> Any:
    """MCP content blocks -> OpenAI tool-message content.

    A list only when there is something a string cannot carry (an image);
    otherwise the plain text, because that is what every provider handles best
    and what history stays readable in.
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
            blocks.append({"type": "text", "text": str(getattr(item, "text", item))})
    if len(blocks) == 1 and blocks[0]["type"] == "text":
        return blocks[0]["text"]
    return blocks


def absolute(path: str, cwd: str) -> str:
    """``DiffChange.path`` and ``ToolCallLocation.path`` must be absolute.

    A client resolves them against its own process, not ours, so a relative
    path is not a smaller path — it is a wrong one.
    """
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(cwd, path))


def diff_content(path: str, cwd: str, new_text: str, old_text: Optional[str]) -> Any:
    """A v2 diff: structured ``changes`` plus the unified ``patch`` text.

    v1 sent ``FileEditToolCallContent{path, oldText, newText}`` and left the
    client to diff them. v2 wants the patch, and our edit/write results
    already carry real text on both sides, so it is generated here.
    ``old_text is None`` means the file did not exist: an add, not a modify.
    """
    abs_path = absolute(path, cwd)
    added = old_text is None
    before = [] if added else (old_text or "").splitlines(keepends=True)
    after = (new_text or "").splitlines(keepends=True)
    # git convention for the a/ b/ header: the absolute path minus its leading
    # slash. `changes[].path` keeps the real absolute path — a client resolves
    # that against its own process — but a patch header that read `a//tmp/x`
    # is not a path anything can open.
    header = abs_path.lstrip("/")
    patch = "".join(
        difflib.unified_diff(
            before,
            after,
            fromfile="/dev/null" if added else f"a/{header}",
            tofile=f"b/{header}",
        )
    )
    change = (
        v2.AddDiffChange(path=abs_path, file_type="text")
        if added
        else v2.ModifyDiffChange(path=abs_path, file_type="text")
    )
    return v2.DiffToolCallContent(
        changes=[change],
        patch=v2.DiffPatch(format="git_patch", text=patch) if patch else None,
    )


def terminal_id_for(acp_tool_call_id: str) -> str:
    """The terminal an execute call owns.

    Deterministic from the call id, so chunks relayed from a progress
    notification and the snapshot that follows land on the same terminal
    without anyone having to thread the id through the MCP call.
    """
    return f"term_{acp_tool_call_id}"


def images_dir(config: Any) -> str:
    """Session ImageStore directory — same derivation as agent/memory.py:
    sqlite -> beside the db file; other backends -> beside the config."""
    db_uri = config.db_uri or ""
    if db_uri.startswith("sqlite:///"):
        return str(Path(db_uri.removeprefix("sqlite:///")).parent / "images")
    return str(Path(config.config_dir) / "images")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


async def execute_tool_calls(
    ctx: TurnCtx,
    mcp_clients: dict[str, Any],
    tool_call_inputs: list[dict],
    tool_results: Optional[list[dict]] = None,
) -> list[dict]:
    """Run a batch of tool calls, filling ``tool_results`` in place.

    In place so a caller can still see completed results when the batch is
    cancelled mid-flight — and on cancel every call with no result gets a
    placeholder, because the persisted assistant message carries the
    tool_calls and the API requires a response for each one.
    """
    if tool_results is None:
        tool_results = []
    try:
        return await _execute_inner(ctx, mcp_clients, tool_call_inputs, tool_results)
    except asyncio.CancelledError:
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


async def _execute_inner(
    ctx: TurnCtx,
    mcp_clients: dict[str, Any],
    tool_call_inputs: list[dict],
    tool_results: list[dict],
) -> list[dict]:
    log = ctx.logger or logger
    for tool_call in tool_call_inputs:
        name = tool_call["function"]["name"]
        raw_args = tool_call["function"]["arguments"]
        llm_id = tool_call["id"]
        acp_id = ctx.tcid(llm_id)
        try:
            args = deserialize_args(raw_args)
            if not isinstance(args, dict):
                # Malformed arguments. Fix them IN PLACE so the persisted
                # history does not poison every later API call with invalid
                # JSON, and tell the model what it did wrong.
                tool_call["function"]["arguments"] = "{}"
                log.error("Malformed tool arguments for %s: %s", name, raw_args)
                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": llm_id,
                        "content": (
                            f"Error: Your tool call for '{name}' had malformed arguments "
                            f"that could not be parsed as JSON. Raw arguments: {raw_args!r}\n"
                            f"Please retry with valid JSON arguments matching the tool schema."
                        ),
                    }
                )
                continue

            # THE dispatch. execute is a terminal; everything else is a call.
            if name == "execute":
                content = await _run_execute(ctx, mcp_clients, acp_id, args)
            else:
                content = await _run_mcp_tool(ctx, mcp_clients, acp_id, name, args)
            tool_results.append({"role": "tool", "tool_call_id": llm_id, "content": content})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("Error executing tool %s: %s", name, exc, exc_info=True)
            await ctx.emitter.tool_call(acp_id, status="failed")
            tool_results.append(
                {"role": "tool", "tool_call_id": llm_id, "content": f"Error: {exc}"}
            )
    return tool_results


def _client_for(ctx: TurnCtx, mcp_clients: dict[str, Any]) -> Any:
    client = mcp_clients.get(ctx.session_id)
    if not client:
        raise RuntimeError(f"No MCP client for session {ctx.session_id}")
    return client


async def _run_mcp_tool(
    ctx: TurnCtx, mcp_clients: dict[str, Any], acp_id: str, name: str, args: dict
) -> Any:
    """The generic path: upsert pending -> in_progress -> call -> completed.

    Content goes to the client; the return value is what the model reads.
    """
    emitter = ctx.emitter
    await emitter.tool_call(
        acp_id, title=name, kind=tool_kind(name), status="pending", raw_input=args
    )
    await emitter.tool_call(acp_id, status="in_progress")

    client = _client_for(ctx, mcp_clients)
    (ctx.logger or logger).info("Executing tool via MCP: %s", name)
    result = await client.call_tool_mcp(name, args)

    await emitter.tool_call(
        acp_id,
        status="failed" if result.isError else "completed",
        content=mcp_to_content(result.content),
    )
    return mcp_to_llm(result.content)


async def _run_execute(
    ctx: TurnCtx, mcp_clients: dict[str, Any], acp_id: str, args: dict
) -> Any:
    """``execute`` as an ACP v2 terminal.

    The sequence is the one the Rust reference established and its renderer is
    written against:

    1. ``tool_call_update`` — create, kind ``execute``, ``raw_input`` carrying
       the cell so the client can show what is about to run.
    2. ``terminal_update`` — the terminal's command and cwd.
    3. ``terminal_output_chunk`` — raw bytes, ANSI intact, base64, relayed
       from MCP progress notifications as the cell produces them.
    4. ``tool_call_update`` — completed, content a ``terminal`` reference,
       ``raw_output`` the stripped text and exit code.
    5. ``terminal_update`` — exit status, independent of the call's status.

    The model gets ``output`` and nothing else: the same ANSI-stripped text v1
    returned, so a cell's result reads the way it always has. The raw bytes
    never enter the context window — that is the point of the split, since
    color and cursor movement are signal for a human and noise for a model.
    """
    emitter = ctx.emitter
    log = ctx.logger or logger
    terminal_id = terminal_id_for(acp_id)
    code = str(args.get("code", ""))

    await emitter.tool_call(
        acp_id, title="execute", kind="execute", status="in_progress", raw_input=args
    )
    await emitter.terminal(terminal_id, command=code, cwd=ctx.cwd)

    async def on_progress(progress: float, total: Optional[float], message: Optional[str]) -> None:
        # crow-mcp2 puts the base64 chunk in the notification's `message`
        # field — the same channel the Rust crow-mcp terminal tool used.
        if message:
            await emitter.terminal_chunk(terminal_id, base64.b64decode(message))

    client = _client_for(ctx, mcp_clients)
    log.info("Executing execute tool via MCP for session %s", ctx.session_id)
    result = await client.call_tool_mcp(
        "execute",
        args,
        progress_handler=on_progress,
        meta={
            "cwd": ctx.cwd,
            "session_id": ctx.session_id,
            "tool_call_id": acp_id,
            "db_uri": ctx.config.db_uri,
            "images_dir": images_dir(ctx.config),
            # The wake bus, so an in-cell task can poke this session the moment
            # it commits a delivery instead of leaving it to the backstop poll.
            # Resolved here rather than read in the kernel: the kernel reads no
            # config, and the model cannot point the bus somewhere else.
            "redis_url": ctx.config.redis_url,
            # Delegation depth, so an in-cell rlm knows whether it is allowed
            # to delegate at all. Derived from the session's own persisted
            # prompt_args, never from the model's arguments.
            "rlm_depth": ctx.session.rlm_depth,
        },
    )

    payload = _execute_payload(result)
    exit_code = payload.get("exit_code")
    text = payload.get("output") or ""

    # The snapshot, for a client that was not watching live. Always sent when
    # there are bytes: the server does not know who is listening (a second
    # client may attach mid-cell, a resume replays from the snapshot), and the
    # client — which does know whether it saw the chunks — is the one that
    # skips re-rendering them.
    raw_b64 = payload.get("raw_bytes_b64") or ""
    if raw_b64:
        await emitter.terminal(terminal_id, output_b64=raw_b64)

    # Tools called INSIDE the cell wrote themselves through to subtool_calls;
    # the drain emits each as its OWN tool call so the client sees every file
    # the code touched. It returns the LLM channel: hydrated image blocks to
    # PREPEND, the one addition to what the cell printed.
    image_blocks = await drain_subtool_calls(ctx, acp_id)

    await emitter.tool_call(
        acp_id,
        status="failed" if result.isError else "completed",
        content=[v2.TerminalToolCallContent(terminal_id=terminal_id)],
        raw_output={"output": text, "exit_code": exit_code},
    )
    if exit_code is not None:
        await emitter.terminal(terminal_id, exit_code=exit_code)

    if image_blocks:
        return [*image_blocks, {"type": "text", "text": text}]
    return text


def _execute_payload(result: Any) -> dict:
    """The execute tool's JSON result, or a text-only fallback.

    crow-mcp2 always returns ``{exit_code, output, timed_out, raw_bytes_b64}``.
    A v1 server returns plain text, which still works — there is just no raw
    copy to snapshot, so the client renders the text like it always did.
    """
    text = "".join(item.text for item in result.content or () if isinstance(item, TextContent))
    empty = {"exit_code": None, "output": text, "timed_out": False, "raw_bytes_b64": ""}
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return empty
    if not isinstance(payload, dict) or "output" not in payload:
        return empty
    return payload

# ---------------------------------------------------------------------------
# The subtool drain
# ---------------------------------------------------------------------------

KIND_BY_RESULT: dict[str, str] = {
    "diff": "edit",
    "read": "read",
    "search": "search",
    # Rows read out of the agent's own memory. The mode cannot decide this
    # one: tool_kind("list") is "read" and tool_kind("search") is "search",
    # but all three modes are the same artifact — rows out of a connection
    # that is read-only at the OS level.
    "memory": "read",
    # A multi-file replace modifies files, so it is an edit-kind call even
    # though its own payload is the summary text (the per-file diffs ride
    # their own rows). tool_kind's substring rules would call "rewrite" an
    # edit only because it happens to contain "write", and "sub" not at all.
    "rewrite": "edit",
    # A page read, whether httpx fetched it or a browser rendered it.
    # tool_kind("fetch") is "fetch" but tool_kind("run") is "other", and a
    # browser loading a URL is the same artifact either way.
    "web": "fetch",
    # A delegation — a fork of the calling session, asked one question.
    # tool_kind("rlm") matches no rule and falls to "other", but the artifact
    # is reasoning paid for out of a fork instead of out of context: "think".
    "rlm": "think",
    # Orchestration: a subagent launched, steered, stopped or read. Stated
    # here rather than left to the tool_kind fallback, which reaches the same
    # "other" only by way of a name list in a different function — and ACP has
    # no kind for "something else is working on your behalf" to reach for.
    "task": "other",
    # The model ending its own continuation loop. Same artifact as task —
    # orchestration, with no ACP kind to reach for — but reached differently:
    # tool_kind("goal_done") falls all the way through the substring rules, so
    # without this entry the kind would be "other" by accident of nothing in
    # the name matching, and the next rule added to that function could
    # quietly reclassify it.
    "goal": "other",
}
"""ACP kind follows the ARTIFACT, not the tool name: a multi-mode tool
(``fs``) is one name doing read/glob/search, and ``tool_kind("fs")`` is
"other". Rows whose result_kind is not an artifact shape (image, text, error)
fall back to the mode, then the tool."""


def subtool_id(ctx: TurnCtx, row_id: int) -> str:
    """Synthetic ACP toolCallId for a call made inside an execute cell.

    Shaped like every other id on the wire (``<turn>/call_...``) so the client
    renders it as the tool call it stands for; the row id keeps it
    deterministic and collision-free.

    One row is one call. A tool that touches N files records N rows — that is
    what fs rewrite does, by calling write() per changed file — so the
    artifacts land where the diffs already live instead of megabytes of whole
    files going into a single row.
    """
    return ctx.tcid(f"call_sub{row_id}")


async def _emit_subtool_call(
    ctx: TurnCtx,
    sub_id: str,
    row: Any,
    title: str,
    kind: str,
    *,
    locations: Optional[list] = None,
    content: Optional[list] = None,
) -> None:
    """Put one in-cell tool call on the wire, in ONE upsert.

    v1 sent three: a pending ``tool_call`` create carrying the args and the
    file location, an ``in_progress`` patch with the artifact, then a status
    patch. That was a create-plus-patch protocol. ``tool_call_update`` is an
    upsert keyed on ``toolCallId``, and a drained row's work is already
    finished — there is no pending phase to show and nothing left to patch.

    Exceptions are swallowed with a warning, as in v1: these are decorative
    synthetic calls, and one row whose payload the schema rejects must not
    abort the turn. If the client is genuinely gone, the next real emission —
    execute's own completion — propagates and ends it.
    """
    patch: dict[str, Any] = {
        "title": title,
        "kind": kind,
        "status": "completed" if row.status == "completed" else "failed",
        "raw_input": row.args or None,
    }
    if locations:
        patch["locations"] = locations
    if content:
        patch["content"] = content
    try:
        await ctx.emitter.tool_call(sub_id, **patch)
    except Exception:
        (ctx.logger or logger).warning(
            "subtool emission failed: %s", sub_id, exc_info=True
        )


def _hydrate_images(
    ctx: TurnCtx, row: Any, llm_blocks: list[dict], store: Any
) -> tuple[list, Any]:
    """(ACP image content, store) for one row's llm_images refs.

    Hoisted out of the image branch because images are orthogonal to the
    payload's shape: a vision call is ALL image, while a browser call is the
    rendered page PLUS a screenshot — one call, one row, two artifacts. The
    LLM's image_url blocks are appended to ``llm_blocks`` either way, since
    that prepend is the only channel a vision model can see through.
    """
    if not row.llm_images:
        return [], store
    if store is None:
        store = resolve_image_store(
            ctx.config.image_store.get("s3"), Path(images_dir(ctx.config))
        )
    blocks = []
    for ref in row.llm_images:
        data = store.get(ref.get("key", ""))
        if data is None:
            (ctx.logger or logger).warning("image blob missing: %s", ref.get("key"))
            continue
        mime = ref.get("mime", "image/png")
        b64 = base64.b64encode(data).decode()
        blocks.append(image_content(b64, mime))
        llm_blocks.append(
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
        )
    return blocks, store


async def drain_subtool_calls(ctx: TurnCtx, parent_acp_id: str) -> list[dict]:
    """Drain the subtool_calls recorded by tools inside an execute cell and
    emit each as its OWN ACP tool call — the client's view of the work the
    code did, even though the LLM only ever called execute.

    Two channels, deliberately different:

    * ACP gets the pretty face — one synthetic tool call per artifact, shaped
      exactly like a real edit/write call (kind, title, locations,
      ``rawInput`` = the args the code passed, content = the diff / image /
      error text) so the client renders a diff view per file changed.
    * The LLM gets NONE of this. It sees execute's stdout and, when a vision
      tool ran, the hydrated image_url blocks returned here for the caller to
      PREPEND. Subtools are code, not conversation.

    Lineage lives in the table (``parent_tool_call_id``); the wire has no
    parent field, so the synthetic ids carry the turn prefix like every other
    call and the row id keeps them deterministic and collision-free.

    Rows were written through from the kernel at call time — the table IS the
    queue — so this works even if the kernel wedged mid-cell. Claiming is
    ``emitted 0 -> 1`` in one transaction, so two drains of the same parent
    (a retry, a second client) cannot double-emit.
    """
    if not ctx.config.db_uri:
        return []
    try:
        engine = get_engine(ctx.config.db_uri)
        try:
            with engine.begin() as conn:
                rows = list(
                    conn.execute(
                        select(SubtoolCall)
                        .where(
                            SubtoolCall.parent_tool_call_id == parent_acp_id,
                            SubtoolCall.emitted == 0,
                        )
                        .order_by(SubtoolCall.id)
                    )
                )
                if rows:
                    conn.execute(
                        sa_update(SubtoolCall)
                        .where(SubtoolCall.id.in_([r.id for r in rows]))
                        .values(emitted=1)
                    )
        finally:
            engine.dispose()
    except Exception:
        (ctx.logger or logger).warning("subtool drain failed", exc_info=True)
        return []

    cwd = ctx.cwd
    llm_blocks: list[dict] = []
    store = None  # resolved lazily — only image rows touch the store
    for row in rows:
        payload = row.acp_payload or {}
        kind = KIND_BY_RESULT.get(row.result_kind) or tool_kind(row.mode or row.tool)
        title = f"{row.tool}/{row.mode}" if row.mode else row.tool
        blocks, store = _hydrate_images(ctx, row, llm_blocks, store)
        sub_id = subtool_id(ctx, row.id)

        if row.result_kind == "diff":
            path = payload.get("path", "")
            await _emit_subtool_call(
                ctx,
                sub_id,
                row,
                title=f"{row.tool}: {path}",
                kind=kind,
                locations=[v2.ToolCallLocation(path=absolute(path, cwd))],
                content=[
                    diff_content(
                        path, cwd, payload.get("new_text", ""), payload.get("old_text")
                    )
                ],
            )
        elif row.result_kind == "read":
            # A read-kind call located at the file, carrying the text read.
            path = payload.get("path", "")
            text = payload.get("text", "")
            await _emit_subtool_call(
                ctx,
                sub_id,
                row,
                title=f"{title}: {path}",
                kind=kind,
                locations=[v2.ToolCallLocation(path=absolute(path, cwd))],
                content=[text_content(text)] if text else None,
            )
        elif row.result_kind == "image":
            await _emit_subtool_call(
                ctx, sub_id, row, title=title, kind=kind, content=blocks or None
            )
        else:
            text = payload.get("text") or (
                f"{title} failed: {row.error}" if row.status == "failed" else ""
            )
            # A result may name its own SUBJECT — a URL, a query — and the
            # title reads better carrying it. Deliberately not a location: a
            # subject is displayed, never claimed as a path, because a page
            # is not a file.
            subject = payload.get("subject")
            content = [text_content(text)] if text else []
            await _emit_subtool_call(
                ctx,
                sub_id,
                row,
                title=f"{title}: {subject}" if subject else title,
                kind=kind,
                content=(content + blocks) or None,
            )
    return llm_blocks

