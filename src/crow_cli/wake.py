"""The wake bus: how work that finished elsewhere finds the session that owns it.

Crow's state is a mailbox in sqlite — ``task_deliveries``, written by
:func:`crow_cli.memory.writes.finish_task`, read by
:mod:`crow_cli.agent2.deliveries`. A mailbox is level-triggered, so a session
that has nothing to do parks and polls. This module is the edge trigger on top
of it: one redis pub/sub channel, and a message that means "go look".

Two halves live here and one does not. :class:`Poke` is the payload and
:func:`publish_wake` is the publisher; both are used by processes that are not
the agent — the execute kernel running the ``task`` subtool, a celery worker
running a timer — which is why they are not in :mod:`crow_cli.agent2`. The
subscriber, :class:`crow_cli.agent2.watcher.WakeWatcher`, belongs to the agent
process because routing a poke needs the driver table, and only the agent has
one.

The ordering is load-bearing. **The row is committed first, the poke is
published second**, and the poke carries a session id and a task id and nothing
else. It says "go look", never "here is what you will find" — carrying the
delivery text on the wire would make the bus a second source of truth with no
way to reconcile it against the row. So every failure mode of a
fire-and-forget bus degrades to latency rather than to a wrong answer:

* redis down — the publish fails, the driver's ``PARK_BACKSTOP_S`` poll
  delivers the row anyway;
* poke lost in flight — same;
* poke delivered twice — the second consult finds an empty mailbox and the
  turn ends without calling the model;
* poke for a session this process does not own — dropped by the subscriber,
  and whichever process does own it got its own copy of the same broadcast.

That last case is why there is ONE channel for the whole deployment instead of
one per session. Several processes share a sqlite — a TUI, an ACP spawn, an MCP
server running the task subtool, a celery worker — and any of them may have
written the row. Broadcasting to one channel and letting every subscriber
ignore what is not theirs costs one JSON parse per wake and removes the need to
know which process owns a session. Nobody knows that durably: ownership moves
when a client reconnects, and a per-session channel would strand the poke on
the old owner.

v1 had no bus at all, which is why it needed the delegation hold — blocking
inside a turn and polling every two seconds, because a returned loop was a deaf
loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import asdict, dataclass, fields
from typing import Any, Optional

import redis.asyncio as aioredis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

#: One channel for the whole deployment. The payload names the session, so a
#: single subscription serves every driver in a process.
CHANNEL = "crow:wake"

#: Connecting to a bus that is not there must not stall a commit. Shorter than
#: a redis default because the caller is either a tool result the model is
#: waiting on or a commit that already succeeded.
CONNECT_TIMEOUT_S = 2.0


@dataclass(frozen=True, slots=True)
class Poke:
    """One published wake: session ``session_id`` has mail about ``task_id``.

    Decoding keeps only the fields this class knows, so a newer publisher can
    add keys without breaking an older subscriber — the two are different
    processes, running different checkouts, and will not be upgraded together.
    """

    session_id: str
    task_id: str = ""
    priority: str = "low"
    kind: str = "subagent"

    def encode(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def decode(cls, raw: Any) -> Optional["Poke"]:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf8", "replace")
        try:
            data = json.loads(raw)
            known = {f.name for f in fields(cls)}
            return cls(**{k: v for k, v in data.items() if k in known})
        except (ValueError, TypeError):
            logger.warning("undecodable wake poke dropped: %.200r", raw)
            return None


async def publish_wake(url: str, poke: Poke) -> bool:
    """Publish one poke. Returns False rather than raising.

    The caller has just committed the mailbox row, and the bus must not be able
    to blow up a commit that already succeeded: the row is the truth, so a
    failed publish costs latency and nothing else. An empty ``url`` is the
    bus being off, which is a configuration and not an error.

    A connection per poke is the right trade for a publisher. Wakes are rare —
    one per finished task — and the alternative is giving a client lifecycle to
    a process that has nowhere to put one: the task subtool lives in an execute
    kernel that outlives the cell, and a celery job body lives for one job.
    """
    if not url:
        return False
    client = aioredis.from_url(
        url, socket_connect_timeout=CONNECT_TIMEOUT_S, socket_timeout=CONNECT_TIMEOUT_S
    )
    try:
        await client.publish(CHANNEL, poke.encode())
        return True
    except (RedisError, OSError, asyncio.TimeoutError) as exc:
        logger.warning(
            "wake poke for %s not published (%s) — the mailbox poll will deliver it",
            poke.session_id,
            exc,
        )
        return False
    finally:
        with contextlib.suppress(Exception):
            await client.aclose()
