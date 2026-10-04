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

**Three things do not survive**, and are not worth a migration:

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
* the subtool calls an execute cell made. They sit in ``subtool_calls`` keyed
  on their parent's live ``<turn_id>/<llm id>``, and the turn id was never
  persisted, so the link died with the process. The cell's own output replays;
  the per-file calls inside it do not.

**Tool call ids are minted, not recovered.** The live id was
``<turn_id>/<llm id>`` and the turn id is gone. ``replay/<seq>/<llm id>`` is
unique within the replay, stable across two replays of the same history (so a
client can dedupe), and can never collide with a live id.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

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
    text_block,
    tool_content,
    tool_diff_content,
    update_tool_call,
)
from crow_cli.agent.tools import get_tool_kind

logger = logging.getLogger(__name__)

ContentBlock = Any


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


async def replay(conn: Any, session_id: str, messages: list[dict], log: Any = None) -> int:
    """Emit ``messages`` as session updates. Returns how many were sent.

    ``messages`` is the session's own list — the same object the next model
    call reads.
    """
    log = log or logger
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
                    sent += await _call(conn, session_id, call, answer, sent)
            continue

        if role == "tool":
            # An answer nobody claimed: the assistant message carrying its call
            # was never written (a crash between the two). It is still history,
            # and it still has the id it was called under, so it replays as a
            # call of its own rather than leaving a hole in the transcript.
            log.warning(
                "replay: tool result with no assistant call at index %d", index - 1
            )
            sent += await _call(conn, session_id, None, message, sent)

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
    conn: Any,
    session_id: str,
    call: Optional[dict],
    answer: Optional[dict],
    seq: int,
) -> int:
    """One finished tool call: the start it would have sent, then its ending.

    Returns the notification count (two — v1 splits create from patch) so the
    caller's tally matches what actually crossed the wire.

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
    await conn.session_update(session_id=session_id, update=start)
    await conn.session_update(
        session_id=session_id,
        update=update_tool_call(acp_id, status=status, content=content),
    )
    return 2


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
