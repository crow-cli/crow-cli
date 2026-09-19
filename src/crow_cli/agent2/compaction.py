"""Compaction: when to compact, and what the client gets to see.

Two things live here that v1 had inline in the react loop.

**The guard.** A compaction is only worth its LLM call if the conversation
GREW since the last one. A successor is born ``[system, handoff]``; when that
alone is over the ceiling, re-summarizing the summary cannot help — and models
reliably write a BIGGER one. Measured live in v1: 11.9k -> 12.8k -> 19.5k ->
26.1k prompt tokens, one ~2-minute call per generation, forever, because the
loop's ``continue`` discarded every reply the successor produced. So
:data:`compacted_at_len` carries on over the ceiling until there is new
history to trade away. Ports unchanged.

**The wire representation.** v1 logged compaction and yielded a
``{"type": "compaction"}`` dict that the agent turned into a text chunk — the
client saw a message, not a compaction. v2 has real types:
``compaction_update`` with a status of in_progress/completed/failed/cancelled
and an optional summary, plus ``compaction_summary_chunk`` for streaming. That
maps 1:1 onto the callable contract crow already ships — the strategy's
streaming pass feeds the chunks, and a strategy that does not stream still
leaves a summary behind for the terminal update. (``on_compact`` is not part
of that mapping: :func:`crow_cli.agent.compact.compact` fires it itself, the
moment the new row is durable, which is BEFORE the ``completed`` update goes
out. It is the driver's rebind, not a wire event — the successor is real and
addressable before the client is told the pass finished.)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Awaitable, Callable, Optional

from acp.experimental.v2 import schema as v2

from crow_cli.agent.compact import CompactSystemPrompt, Compactor, compact
from crow_cli.agent.session import AgentSession
from crow_cli.config import Config, max_compact_tokens_for

from .ctx import TurnCtx
from .emitter import Emitter

logger = logging.getLogger(__name__)


def threshold_for(config: Config, model: str) -> int:
    """The compaction ceiling for ``model``, resolved live.

    Never cached at session init: the user can switch models mid-session via
    ``set_config_option``, and models without their own
    ``max_compact_tokens`` keep the global rate.
    """
    return max_compact_tokens_for(config, model)


def over_threshold(usage: Optional[dict], threshold: int) -> bool:
    return bool(usage and usage.get("total_tokens", 0) > threshold)


def worth_compacting(session: AgentSession, compacted_at_len: Optional[int]) -> bool:
    """False when nothing has been added since the last compaction."""
    return compacted_at_len is None or len(session.messages) > compacted_at_len


async def run(
    ctx: TurnCtx,
    llm: Any,
    *,
    on_compact: Callable[[str, AgentSession], Awaitable[None]],
    compactor: Optional[Compactor] = None,
    compact_system_prompt: Optional[CompactSystemPrompt] = None,
) -> AgentSession:
    """Compact ``ctx.session`` into a new agent generation, narrating it.

    Returns the new session. The caller rebinds its turn to it — the wire
    sessionId is unchanged (compaction forks ``agent_idx`` inside a stable
    session) but every later write must land on the new row.

    The narration is the three v2 shapes in the order the spec requires:
    ``in_progress`` first (chunks are only legal after it and before the
    terminal update for the same id), one ``compaction_summary_chunk`` per
    piece of summary the strategy streams, then ``completed``. The terminal
    update carries a ``summary`` ONLY when nothing streamed: ``summary`` is a
    complete REPLACEMENT of what the chunks accumulated, and replacing the
    model's prose with the whole handoff — which is that prose plus a
    flattened dump of the last twenty messages — would trade a readable
    summary for a transcript. A strategy that never streams (a custom
    compactor that asks nothing) gets the replacement, because otherwise the
    client would retain nothing at all.

    A cancel mid-pass reports ``cancelled``. That is a separate branch from
    the failure one because :class:`asyncio.CancelledError` is a
    :class:`BaseException`, so ``except Exception`` sails straight past it and
    the client's compaction entity would sit ``in_progress`` forever.
    """
    emitter: Emitter = ctx.emitter
    compaction_id = uuid.uuid4().hex
    streamed = 0

    async def on_summary_chunk(text: str) -> None:
        nonlocal streamed
        streamed += 1
        await emitter.compaction_chunk(compaction_id, text)

    await emitter.compaction(compaction_id, "in_progress")
    try:
        session = await compact(
            session=ctx.session,
            llm=llm,
            config=ctx.config,
            on_compact=on_compact,
            logger=ctx.logger,
            compactor=compactor,
            system_prompt=compact_system_prompt,
            on_summary_chunk=on_summary_chunk,
        )
    except asyncio.CancelledError:
        await emitter.compaction(compaction_id, "cancelled")
        raise
    except Exception as exc:
        await emitter.compaction(compaction_id, "failed", error=str(exc))
        raise
    await emitter.compaction(
        compaction_id,
        "completed",
        summary=None if streamed else summary_of(session),
    )
    return session


def summary_of(session: AgentSession) -> Optional[list[Any]]:
    """The handoff, as compaction summary content blocks.

    A successor is born ``[system, user(handoff)]`` — the handoff IS the
    summary, so there is nothing extra to compute. Absent one (a custom
    compactor that built the generation differently) the update simply omits
    it, which v2 allows.
    """
    for msg in session.messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return [v2.TextContentBlock(text=content)]
        if isinstance(content, list):
            blocks = [
                v2.TextContentBlock(text=b["text"])
                for b in content
                if isinstance(b, dict) and b.get("type") == "text" and b.get("text", "").strip()
            ]
            return blocks or None
    return None
