"""Replaying persisted history as v1 ``session/update`` notifications.

``session/load``'s contract is that the agent streams the conversation back and
only then answers, so a client that opens a thread sees the thread. Without
this the load succeeds, the client resets its transcript, and the user is left
staring at an empty conversation the agent is perfectly able to continue — the
worst of both worlds, because it looks like the switch silently lost the chat.

:mod:`crow_cli.agent2.replay` is the v2 half of the same idea; this is v1, and
the two differ only in wire shape (v1 splits a tool call into ``tool_call`` +
``tool_call_update``, and its chunks carry one content block each with no
``messageId``).

What replay can be faithful about, and what it cannot:

**The transcript is the LLM's, not the wire's.** crow persists ONE message
history and it is the one the next model call reads: OpenAI-shaped dicts, not
the notifications that crossed the wire. There is no second store to replay
from, so this reconstructs — and it reconstructs from the same object the model
reads, so replay and the model cannot disagree about what happened.

**Tool calls are re-presented, not re-run.** Each one is emitted with the same
start its live emitter would have sent — same title, kind, locations and
raw_input, derived from the persisted arguments — followed by ONE update
carrying the final status and content. The live ``in_progress`` step is
skipped: walking a finished call back through a state nobody watched is
theatre. Because the arguments survived, an ``edit`` or ``write`` replays with
its real diff content and renders the same viewer it rendered live.

**Calls an execute cell made replay too**, and they carry more of the story
than they look: crow does most of its file work inside cells, so a replay that
showed only the ``execute`` card would lose every diff that card produced.
Those calls are in no message history — the LLM only ever called ``execute`` —
but the subtool register wrote one row per in-cell call, keyed on the parent's
ACP id. That key is ``<turn_id>/<llm id>``; the turn id died with the process
that minted it, but the llm id is persisted in the assistant message's
``tool_calls[].id``, so the last path segment is a join that survives. Rows
arrive as ``subtools`` — that segment mapped to the calls made under it — and
each replays as its own tool call, in the position the live drain put it:
between the parent's start and the parent's ending. This module reads no
database; building the mapping is
:func:`crow_cli.memory.reads.subtool_calls_by_parent`'s job, which keeps the
wire logic here testable against plain objects.

**Two things do not survive**, and are not worth a migration:

* a tool call's ``failed`` status. ``result.isError`` decided it live and the
  tool message that survived carries only text, so every answered call replays
  as ``completed``. A call with NO answer — cancelled turn, dead process —
  replays as ``failed``, because v1's ``ToolCallStatus`` has no ``cancelled``
  (v2 added it) and the other three are worse: ``pending``/``in_progress``
  would leave a client spinning on a call that ended years ago. Note that an
  out-of-Literal status does not raise here — pydantic coerces it to ``None``,
  which a client reads as "unchanged", so the wrong word silently freezes the
  card instead of failing loudly.
* an execute cell's raw PTY bytes and exit code. The bytes went to the client
  live and nowhere else; what is durable is the ANSI-stripped text the model
  read, and that is what replays.

**Tool call ids are minted, not recovered.** The live id was
``<turn_id>/<llm id>`` and the turn id is gone. ``replay/<seq>/<llm id>`` is
unique within the replay, stable across two replays of the same history (so a
client can dedupe), and can never collide with a live id. In-cell calls mint
the same shape around the register's row id — ``replay/<seq>/call_sub<row>`` —
which is what the live emitter would have called them had the turn survived.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    ToolCallLocation,
    ToolCallStart,
    UserMessageChunk,
)

from crow_cli.acp_helpers import (
    image_block,
    start_edit_tool_call,
    start_read_tool_call,
    start_tool_call,
    text_block,
    tool_content,
    tool_diff_content,
    update_tool_call,
)

# _KIND_BY_RESULT is private to the live emitter and imported anyway: it is a
# mapping of artifact shape to ACP kind that took its comments seriously, and
# a second copy of it here would be a second thing to keep in step with the
# first. Replay's whole claim is that a replayed card is indistinguishable
# from a live one, which is only true if both ask the same table.
from crow_cli.agent.tools import _KIND_BY_RESULT, get_tool_kind

logger = logging.getLogger(__name__)

ContentBlock = Any


@dataclass(frozen=True)
class ReplayCtx:
    """What stays fixed for one replay, bundled so the helpers below take one
    argument instead of five.

    The same idea as :class:`crow_cli.agent.context.TurnCtx` on the live side,
    and for the same reason: every emitter needs the connection and the wire
    session id, and the in-cell ones additionally need the register rows and
    somewhere to fetch image blobs from. Frozen because a replay is a single
    pass over a history that is not changing underneath it.
    """

    conn: Any
    session_id: str
    subtools: dict[str, list]
    store: Any = None
    log: Any = logger


def _data_url(url: Any) -> Optional[tuple[str, str]]:
    """``data:<mime>;base64,<data>`` -> ``(mime, data)``, or None."""
    if not isinstance(url, str) or not url.startswith("data:"):
        return None
    head, sep, data = url.partition(";base64,")
    if not sep or not data:
        return None
    return head[len("data:") :], data


def content_blocks(content: Any) -> list[ContentBlock]:
    """Persisted message content -> v1 content blocks.

    Both shapes history carries: a plain string (an assistant completion, a
    mailbox delivery) and the block list ``normalize_prompt`` wrote for a
    prompt that carried an attachment. Images arrive hydrated — ``load`` swaps
    the store's refs back into data URLs — so the decode is the same one the
    model's own view went through.
    """
    if content is None:
        return []
    if isinstance(content, str):
        return [text_block(content)] if content else []
    blocks: list[ContentBlock] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "text" and item.get("text"):
            blocks.append(text_block(item["text"]))
        elif kind == "image_url":
            decoded = _data_url((item.get("image_url") or {}).get("url"))
            if decoded is not None:
                mime, data = decoded
                blocks.append(image_block(data=data, mime_type=mime))
    return blocks


def _args_of(call: dict) -> dict:
    """The call's arguments, decoded. A malformed payload replays as no args
    rather than taking the whole transcript down with it."""
    raw = (call.get("function") or {}).get("arguments")
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


async def replay(
    conn: Any,
    session_id: str,
    messages: list[dict],
    log: Any = None,
    subtools: Optional[dict[str, list]] = None,
    resolve_store: Optional[Callable[[], Any]] = None,
) -> int:
    """Emit ``messages`` as session updates. Returns how many were sent.

    ``messages`` is the session's own list — the same object the next model
    call reads. ``subtools`` maps an execute call's llm id to the register
    rows for the calls that cell made; a missing key replays the cell on its
    own, which is also what an empty mapping does.

    ``resolve_store`` returns the session's ImageStore, and is called at most
    once and only if some row actually carries image refs — probing an S3
    endpoint for a transcript with no images in it is a round trip bought for
    nothing, which is why :attr:`MemoryClient.image_store` is lazy too.
    """
    log = log or logger
    subtools = subtools or {}
    store = None
    if resolve_store is not None and any(
        row.llm_images for rows in subtools.values() for row in rows
    ):
        store = resolve_store()
    ctx = ReplayCtx(
        conn=conn, session_id=session_id, subtools=subtools, store=store, log=log
    )
    sent = 0
    index = 0
    total = len(messages)
    while index < total:
        message = messages[index]
        index += 1
        role = message.get("role")

        if role == "system":
            continue

        if role == "user":
            for block in content_blocks(message.get("content")):
                await conn.session_update(
                    session_id=session_id,
                    update=UserMessageChunk(
                        session_update="user_message_chunk", content=block
                    ),
                )
                sent += 1
            continue

        if role == "assistant":
            thought = (message.get("reasoning_content") or "").strip()
            if thought:
                await conn.session_update(
                    session_id=session_id,
                    update=AgentThoughtChunk(
                        session_update="agent_thought_chunk",
                        content=text_block(thought),
                    ),
                )
                sent += 1
            for block in content_blocks(message.get("content")):
                await conn.session_update(
                    session_id=session_id,
                    update=AgentMessageChunk(
                        session_update="agent_message_chunk", content=block
                    ),
                )
                sent += 1
            calls = message.get("tool_calls") or ()
            if calls:
                # The answers follow, in order, exactly as react persisted
                # them. Taken as a run and matched by id INSIDE it rather than
                # by position alone: an llm tool-call id repeats across turns
                # but never within one batch, so the run is the only scope in
                # which the id means anything.
                run: list[dict] = []
                while index < total and messages[index].get("role") == "tool":
                    run.append(messages[index])
                    index += 1
                by_id = {r.get("tool_call_id"): r for r in run}
                for position, call in enumerate(calls):
                    answer = by_id.get(call.get("id"))
                    if answer is None and position < len(run):
                        answer = run[position]
                    sent += await _call(ctx, call, answer, sent)
            continue

        if role == "tool":
            # An answer nobody claimed: the assistant message carrying its call
            # was never written (a crash between the two). It is still history,
            # and it still has the id it was called under, so it replays as a
            # call of its own rather than leaving a hole in the transcript.
            log.warning(
                "replay: tool result with no assistant call at index %d", index - 1
            )
            sent += await _call(ctx, None, message, sent)

    log.info("replayed %d session update(s) into %s", sent, session_id)
    return sent


def _as_text(value: Any) -> str:
    """A persisted argument that reached the wire as a string. ``write``'s
    ``content`` can arrive already decoded into a dict, which the live emitter
    re-serialises before it diffs it — replay does the same."""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, indent=2)


async def _call(
    ctx: ReplayCtx,
    call: Optional[dict],
    answer: Optional[dict],
    seq: int,
) -> int:
    """One finished tool call: the start it would have sent, then its ending.

    Returns the notification count so the caller's tally matches what actually
    crossed the wire — two for the call itself (v1 splits create from patch),
    plus two for every call the cell made.

    ``call`` is the assistant's ``tool_calls`` entry and may be None for an
    orphaned answer; ``answer`` is the tool message and may be None for a call
    the turn never finished.
    """
    call = call or {}
    function = call.get("function") or {}
    name = function.get("name") or "tool"
    llm_id = call.get("id") or (answer or {}).get("tool_call_id") or str(seq)
    acp_id = f"replay/{seq}/{llm_id}"
    args = _args_of(call)
    answer_blocks = [
        tool_content(block) for block in content_blocks((answer or {}).get("content"))
    ]
    # v1 spells an interrupted call "failed" — see the module docstring.
    status = "completed" if answer is not None else "failed"

    start, content = _presentation(name, args, acp_id, answer_blocks)
    await ctx.conn.session_update(session_id=ctx.session_id, update=start)
    sent = 1
    # In-cell calls land HERE — after the parent's start, before its ending —
    # because that is where the live drain puts them: agent/tools.py sends
    # execute's start and its in_progress, runs the cell, drains the register,
    # and only then sends execute's final update. Same order in, same picture
    # out, for a client that orders by arrival.
    cursor = seq + 1
    for row in ctx.subtools.get(llm_id) or ():
        await _subtool_call(ctx, row, cursor)
        cursor += 2
        sent += 2
    await ctx.conn.session_update(
        session_id=ctx.session_id,
        update=update_tool_call(acp_id, status=status, content=content),
    )
    return sent + 1


def _presentation(
    name: str, args: dict, acp_id: str, answer_blocks: list
) -> tuple[ToolCallStart, Optional[list]]:
    """The start notification and final content for one replayed call.

    Every branch mirrors the live emitter for that tool in
    :mod:`crow_cli.agent.tools`, so a replayed card is indistinguishable from
    a live one: same title, same kind, same locations, same raw_input, and —
    for the file tools — the same diff content, because the arguments that
    produced it are exactly what survived.
    """
    if name == "edit":
        path = _as_text(args.get("file_path"))
        return (
            start_edit_tool_call(
                tool_call_id=acp_id,
                title=f"edit: {path}",
                path=path,
                content=_as_text(args.get("new_string")),
                name="edit",
            ),
            [
                tool_diff_content(
                    path=path,
                    new_text=_as_text(args.get("new_string")),
                    old_text=_as_text(args.get("old_string")),
                )
            ],
        )

    if name == "write":
        path = _as_text(args.get("file_path"))
        content = _as_text(args.get("content"))
        return (
            start_edit_tool_call(
                tool_call_id=acp_id,
                title=f"write: {path}",
                path=path,
                content=content,
                name="write",
            ),
            [tool_diff_content(path=path, new_text=content)],
        )

    if name == "read":
        path = _as_text(args.get("file_path"))
        return (
            start_read_tool_call(
                tool_call_id=acp_id, title=f"read: {path}", path=path, name="read"
            ),
            answer_blocks or None,
        )

    if name == "execute":
        # The fenced cell first, exactly as the live emitter attaches it, so
        # the client shows what ran above what it printed.
        code_block = tool_content(text_block(f"```python\n{_as_text(args.get('code'))}\n```"))
        return (
            ToolCallStart(
                session_update="tool_call",
                tool_call_id=acp_id,
                title="execute",
                name="execute",
                kind="execute",
                status="pending",
                content=[code_block],
            ),
            [code_block, *answer_blocks],
        )

    if name == "terminal":
        command = _as_text(args.get("command"))
        return (
            ToolCallStart(
                session_update="tool_call",
                tool_call_id=acp_id,
                title=command or "terminal",
                name="terminal",
                kind="execute",
                status="pending",
            ),
            answer_blocks or None,
        )

    path = args.get("path") or args.get("file_path")
    locations = (
        [ToolCallLocation(path=_as_text(path))]
        if isinstance(path, str) and path
        else None
    )
    return (
        ToolCallStart(
            session_update="tool_call",
            tool_call_id=acp_id,
            title=name,
            name=name,
            kind=get_tool_kind(name),
            status="pending",
            locations=locations,
        ),
        answer_blocks or None,
    )


async def _subtool_call(ctx: ReplayCtx, row: Any, seq: int) -> None:
    """One call an execute cell made, as the tool call it was.

    Two beats, not the live emitter's three: the ``in_progress`` step is
    skipped for the same reason it is skipped for the parent, and everything a
    client renders is on one of the two that remain — the start carries title,
    kind, location and the args the code passed, the ending carries the status
    and the artifact.

    ``row`` is a ``subtool_calls`` row. The id keeps the live shape
    (``call_sub<row id>``) under a replay prefix, so a client that groups by
    the suffix still sees one call per row.
    """
    sub_id = f"replay/{seq}/call_sub{row.id}"
    status = "completed" if row.status == "completed" else "failed"
    start, content = _subtool_presentation(ctx, row, sub_id)
    await ctx.conn.session_update(session_id=ctx.session_id, update=start)
    await ctx.conn.session_update(
        session_id=ctx.session_id,
        update=update_tool_call(sub_id, status=status, content=content),
    )


def _subtool_presentation(
    ctx: ReplayCtx, row: Any, sub_id: str
) -> tuple[ToolCallStart, Optional[list]]:
    """The start and final content for one register row.

    Branch for branch the live drain (``agent/tools.py _emit_subtool_calls``):
    kind from the ARTIFACT shape, title from the tool and its mode, and one of
    four payloads — a diff, a read, images, or text with an optional subject.
    The two are kept in step by hand rather than shared because they disagree
    on purpose about beats and ids; the branches are the contract, and each has
    a test asserting the fields the live emitter sends.
    """
    payload = row.acp_payload or {}
    kind = _KIND_BY_RESULT.get(row.result_kind) or get_tool_kind(row.mode or row.tool)
    title = f"{row.tool}/{row.mode}" if row.mode else row.tool

    def begin(title: str, path: Optional[str] = None) -> ToolCallStart:
        return start_tool_call(
            sub_id,
            title,
            name=row.tool,
            kind=kind,
            status="pending",
            locations=[ToolCallLocation(path=path)] if path else None,
            raw_input=row.args or None,
        )

    if row.result_kind == "diff":
        path = payload.get("path", "")
        return begin(f"{row.tool}: {path}", path), [
            tool_diff_content(
                path=path,
                new_text=payload.get("new_text", ""),
                old_text=payload.get("old_text"),
            )
        ]

    if row.result_kind == "read":
        path = payload.get("path", "")
        text = payload.get("text", "")
        return begin(f"{title}: {path}", path), (
            [tool_content(text_block(text))] if text else None
        )

    if row.result_kind == "image":
        return begin(title), _image_blocks(ctx, row) or None

    text = payload.get("text") or (
        f"{title} failed: {row.error}" if row.status == "failed" else ""
    )
    # A result may name its own SUBJECT — a URL, a query — and the title reads
    # better carrying it. Deliberately not a location: a subject is displayed,
    # never claimed as a path, because a page is not a file.
    subject = payload.get("subject")
    content = [tool_content(text_block(text))] if text else []
    return begin(f"{title}: {subject}" if subject else title), (
        content + _image_blocks(ctx, row)
    ) or None


def _image_blocks(ctx: ReplayCtx, row: Any) -> list:
    """ACP image content for one row's store refs.

    The live hydrator writes TWO channels — the wire, and the model's next
    request, since an ``image_url`` block prepended to execute's result is the
    only channel a vision model can see through. Replay owes the wire alone:
    the model's copy was persisted with the message, and ``load`` hydrated it
    back into a data URL that :func:`content_blocks` already decodes.
    """
    if not row.llm_images:
        return []
    if ctx.store is None:
        ctx.log.warning(
            "replay: subtool row %s carries %d image ref(s) but no image store "
            "was supplied",
            row.id,
            len(row.llm_images),
        )
        return []
    blocks = []
    for ref in row.llm_images:
        data = ctx.store.get(ref.get("key", ""))
        if data is None:
            ctx.log.warning("replay: image blob missing: %s", ref.get("key"))
            continue
        mime = ref.get("mime", "image/png")
        blocks.append(
            tool_content(
                image_block(data=base64.b64encode(data).decode(), mime_type=mime)
            )
        )
    return blocks
