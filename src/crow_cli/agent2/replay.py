"""Replaying persisted history as ``session/update`` notifications.

``session/load`` is gone in v2. ``session/resume`` absorbed it: omit
``replayFrom`` and the agent reattaches silently, send ``{"type": "start"}``
and it replays the whole conversation before responding. This is the second
half of that.

What replay can be faithful about, and what it cannot — and why the losses are
not worth a migration:

**The transcript is the LLM's, not the wire's.** crow persists ONE message
history and it is the one the next model call reads: OpenAI-shaped dicts, not
the notifications that crossed the wire. There is no second store to replay
from, so this reconstructs. Three things do not survive:

* a tool call's ``failed`` status. ``result.isError`` decided it live and the
  tool message that survived carries only text, so every answered call replays
  as ``completed``. A call with NO answer — cancelled turn, dead process —
  replays as ``cancelled``, which is derivable and nearly always true.
* an execute call's raw PTY bytes and exit code. The bytes went to the client
  live and nowhere else; what is durable is the ANSI-stripped text the model
  read, and that is what the terminal snapshot carries.
* the subtool calls an execute cell made. They sit in ``subtool_calls`` keyed
  on their parent's live ``<turn_id>/<llm id>``, and the turn id was never
  persisted, so the link died with the process. The cell's own output replays;
  the per-file calls inside it do not.

**Whole messages, not chunks.** v2's updates are upserts — a whole-message
update replaces content, a chunk appends — so the assembled string history
holds maps onto the replace form directly. Re-splitting it would be theatre:
no client can tell, and it costs N notifications instead of one.

**One ``tool_call_update`` per call.** v2 has no create/patch split to replay
into, and walking a finished call back through ``pending`` and
``in_progress`` would be a lie about a sequence nobody watched.

**Terminal snapshots, never chunks** — the migration guide asks for exactly
this, "terminal replacement snapshots rather than requiring every historical
output chunk".

**Tool call ids are minted, not recovered.** The live id was
``<turn_id>/<llm id>`` and the turn id is gone. ``replay/<seq>/<llm id>`` is
unique within the replay, stable across two replays of the same history (so a
client can dedupe), and can never collide with a live id.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Optional

from acp.experimental.v2 import schema as v2

from .emitter import Emitter
from .tools import deserialize_args, terminal_id_for, tool_kind

logger = logging.getLogger(__name__)


def _data_url(url: Any) -> Optional[tuple[str, str]]:
    """``data:<mime>;base64,<data>`` -> ``(mime, data)``, or None."""
    if not isinstance(url, str) or not url.startswith("data:"):
        return None
    head, sep, data = url.partition(";base64,")
    if not sep or not data:
        return None
    return head[len("data:") :], data


def content_blocks(content: Any) -> list[Any]:
    """Persisted message content -> v2 content blocks.

    Both shapes history carries: a plain string (an assistant completion, a
    mailbox delivery) and the block list ``normalize_prompt`` wrote for a
    prompt that carried an attachment. Images arrive hydrated — ``load`` swaps
    the store's refs back into data URLs — so the decode is the same one the
    model's own view went through.
    """
    if content is None:
        return []
    if isinstance(content, str):
        return [v2.TextContentBlock(text=content)] if content else []
    blocks: list[Any] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "text" and item.get("text"):
            blocks.append(v2.TextContentBlock(text=item["text"]))
        elif kind == "image_url":
            decoded = _data_url((item.get("image_url") or {}).get("url"))
            if decoded is not None:
                mime, data = decoded
                blocks.append(v2.ImageContentBlock(data=data, mime_type=mime))
    return blocks


def _text_of(content: Any) -> str:
    """The text a persisted payload carries, whatever its shape."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


async def replay(
    emitter: Emitter, messages: list[dict], cwd: str, log: Any = None
) -> int:
    """Emit ``messages`` as session updates. Returns how many were sent.

    ``messages`` is the session's own list — the same object the next model
    call reads — so replay and the model cannot disagree about what happened.
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
            blocks = content_blocks(message.get("content"))
            if blocks:
                await emitter.user_message(emitter.start_message(), blocks)
                sent += 1
            continue

        if role == "assistant":
            thought = (message.get("reasoning_content") or "").strip()
            if thought:
                await emitter.agent_thought(
                    emitter.start_message(), [v2.TextContentBlock(text=thought)]
                )
                sent += 1
            blocks = content_blocks(message.get("content"))
            if blocks:
                await emitter.agent_message(emitter.start_message(), blocks)
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
                    await _call(emitter, call, answer, sent, cwd)
                    sent += 1
            continue

        if role == "tool":
            # An answer nobody claimed: the assistant message carrying its call
            # was never written (a crash between the two). It is still history,
            # and it still has the id it was called under, so it replays as a
            # call of its own rather than leaving a hole in the transcript.
            log.warning("replay: tool result with no assistant call at index %d", index - 1)
            await _call(emitter, None, message, sent, cwd)
            sent += 1

    log.info("replayed %d session update(s)", sent)
    return sent


async def _call(
    emitter: Emitter,
    call: Optional[dict],
    answer: Optional[dict],
    seq: int,
    cwd: str,
) -> None:
    """One finished tool call, as the single upsert v2 wants.

    ``call`` is the assistant's ``tool_calls`` entry and may be None for an
    orphaned answer; ``answer`` is the tool message and may be None for a call
    the turn never finished.
    """
    call = call or {}
    function = call.get("function") or {}
    name = function.get("name") or "tool"
    llm_id = call.get("id") or (answer or {}).get("tool_call_id") or str(seq)
    acp_id = f"replay/{seq}/{llm_id}"
    args = deserialize_args(function.get("arguments")) if function else None

    patch: dict[str, Any] = {
        "title": name,
        "kind": tool_kind(name),
        "status": "completed" if answer is not None else "cancelled",
    }
    if args:
        patch["raw_input"] = args

    if name == "execute":
        # The terminal comes first: the call's content is a REFERENCE to it,
        # and a client that renders the reference before it has the terminal
        # has nothing to render. Live traffic has the same ordering constraint
        # and satisfies it the same way.
        terminal_id = terminal_id_for(acp_id)
        text = _text_of((answer or {}).get("content"))
        code = args.get("code") if isinstance(args, dict) else None
        await emitter.terminal(
            terminal_id,
            command=str(code) if code else None,
            cwd=cwd,
            # The stripped text, because that is what survived. Not the raw
            # bytes: those were relayed live and never persisted, and inventing
            # ANSI for a snapshot would be worse than admitting the loss.
            output_b64=base64.b64encode(text.encode()).decode("ascii") if text else None,
        )
        patch["content"] = [v2.TerminalToolCallContent(terminal_id=terminal_id)]
    else:
        content = [
            v2.ContentToolCallContent(content=block)
            for block in content_blocks((answer or {}).get("content"))
        ]
        if content:
            patch["content"] = content

    await emitter.tool_call(acp_id, **patch)
