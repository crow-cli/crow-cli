"""The mailbox: how work that finished elsewhere reaches this session.

:class:`crow_cli.memory.models.TaskDelivery` is durable truth — a row per
wake, ``status`` pending or delivered, claimed atomically by
:func:`crow_cli.memory.writes.claim_deliveries` (one ``UPDATE...RETURNING``,
so concurrent consult points race for the same rows and each delivery is still
injected exactly once).

This module is the *consult* half: land pending deliveries as synthetic user
messages. The *wake* half — noticing a row appeared while the session was
parked — lives in :mod:`crow_cli.agent2.watcher` and
:meth:`crow_cli.agent2.driver.SessionDriver.park`.

The split matters. v1 had no out-of-loop watcher, so the mailbox could only be
read at breakpoints inside a live turn, and a session with nothing running
could never be told anything. That forced the delegation hold: block inside
the turn, polling every two seconds, because a returned loop was a deaf loop.
Here the mailbox is level-triggered underneath an edge trigger — a redis poke
is what makes wake prompt, but a missed poke is not a lost wake, because any
later event re-consults the same rows and a slow backstop poll catches the
rest.
"""

from __future__ import annotations

import logging

from crow_cli.memory.writes import claim_deliveries

from .emitter import Emitter

logger = logging.getLogger(__name__)


async def consult(
    engine,
    session,
    emitter: Emitter,
    *,
    high_only: bool = False,
) -> bool:
    """Claim pending deliveries and inject them as user messages.

    Returns True when anything was injected, which tells the react loop it
    must react rather than end the turn. With ``high_only`` only
    high-priority rows are claimed — the mid-turn breakpoint, so cancels and
    urgencies surface immediately while low-priority completions hold to end
    of turn by design.

    Each delivery is echoed to the client as a ``user_message_chunk``: the
    model is about to respond to something the user did not type, and a
    conversation that hides its own inputs cannot be followed or replayed.
    """
    deliveries = claim_deliveries(engine, emitter.session_id, "high" if high_only else None)
    if not deliveries:
        return False
    for d in deliveries:
        await session.add_message({"role": "user", "content": d["content"]})
        await emitter.user_chunk(emitter.start_message(), d["content"])
        logger.info(
            "DELIVERY: injected %s (%s) into %s",
            d["task_id"],
            d["priority"],
            emitter.session_id,
        )
    return True
