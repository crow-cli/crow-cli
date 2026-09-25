"""Events that wake a session driver.

v1 had one channel into the react loop: ``session/prompt``. When the loop ran
out of foreground work it returned, the generator ended, and with it all
awareness of the session — which is why the delegation hold had to block
*inside* the turn polling the mailbox every two seconds.

agent2 splits "the loop has no more foreground work" from "the session is
done". The loop reports; :mod:`crow_cli.agent2.driver` decides. When the
driver has nothing to run it emits ``state_update: idle`` and parks on
``await inbox.get()`` — not a return, not a poll. Everything that can restart
it arrives as one of the events below.

No dependencies on purpose: this module is imported by the driver, the react
loop, the watcher and the tests, and must not drag protocol or DB types in.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Union


@dataclass(frozen=True, slots=True)
class Prompt:
    """A ``session/prompt`` the agent accepted.

    ``blocks`` is the v2 ``ContentBlock`` list exactly as it arrived on the
    wire. The driver hands it to the emitter to render and to the session to
    persist; this module does not need to know its shape.

    ``message_id`` is minted by the ``prompt`` handler, not by the driver that
    echoes it, because the handler has to answer with it: v2's
    ``PromptResponse`` carries the ``messageId`` the accepted user message
    landed under, and the ``user_message`` update the driver emits later must
    carry the SAME one. Two mints would be two identities for one message, and
    the response reaches the client first, so the driver cannot be the one
    that decides.
    """

    blocks: list[Any]
    message_id: str


@dataclass(frozen=True, slots=True)
class Delivery:
    """A poke: this session has mail. Go read the mailbox.

    Identity and nothing else — no content, deliberately. The
    :class:`crow_cli.memory.models.TaskDelivery` rows in sqlite are the truth
    and :func:`crow_cli.agent2.deliveries.consult` claims them atomically, so
    a poke that arrives twice, arrives late, or names a row another process
    already claimed costs one redundant consult rather than one duplicated
    message. Carrying the text on the event would make the bus a second
    source of truth with no way to reconcile the two.

    One poke per wake, whatever woke us: a subagent finishing, a celery job
    completing, a timer expiring, a self-prompt queued for the next idle.
    ``kind`` is :attr:`crow_cli.memory.models.Task.kind` — free text, so new
    wake sources need no migration.
    """

    task_id: str
    priority: str = "low"
    kind: str = "subagent"


@dataclass(frozen=True, slots=True)
class Cancel:
    """``session/cancel``: kill the foreground work, keep the driver.

    Cancellation in v2 is per-foreground-work, not per-connection. The real
    work is done by :meth:`SessionDriver.cancel` cancelling the react task;
    this event exists so a cancel that lands while the driver is between
    events still discards queued prompts instead of starting a new turn.
    """


#: There is no ``Timer`` event, and the reason is :class:`Delivery`.
#:
#: Celery is the scheduler — ``apply_async(countdown=N)`` — so there is no timer
#: wheel, no ``deliver_at`` column and no cron sweep in crow. A fired timer runs
#: ``timers.fire_timer``, which writes the mailbox row and publishes a poke with
#: ``kind="timer"``; the watcher decodes that poke into a ``Delivery`` like any
#: other. A separate event carrying the payload would be a second source of
#: truth for the same wake, which is exactly what ``Delivery`` refuses to be.
Event = Union[Prompt, Delivery, Cancel]

#: The driver's single wake channel. One per session, owned by its driver.
Inbox = "asyncio.Queue[Event]"


def new_inbox() -> asyncio.Queue[Event]:
    return asyncio.Queue()
