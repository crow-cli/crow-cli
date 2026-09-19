"""The wake bus subscriber: one per agent process.

:mod:`crow_cli.wake` is the bus — the channel, the payload and the publisher.
They live outside the agent because the processes that publish are not agents:
the execute kernel running the ``task`` subtool, a celery worker running a
timer. This module is the half only an agent can do: hold a subscription open
and route each poke into the inbox of the driver that owns the session, which
gets a *parked* driver out of its ``await inbox.get()`` the moment a mailbox
row lands instead of at the next backstop poll.

:mod:`crow_cli.agent2.deliveries` is the consult half — it claims the rows.
The contract between them (row committed first, poke published second, and the
poke says "go look" rather than carrying the delivery) is argued in
:mod:`crow_cli.wake`, along with why every failure mode of the bus degrades to
latency rather than to a wrong answer.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from logging import Logger
from typing import Any, Callable, Optional

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from crow_cli.wake import CHANNEL, CONNECT_TIMEOUT_S, Poke

from .events import Delivery, Inbox

logger = logging.getLogger(__name__)

#: How long to wait before retrying a subscription that dropped. Fixed rather
#: than exponential: what we are waiting for is a container to come up, and
#: five seconds already outlasts that when it is going to happen at all.
RECONNECT_S = 5.0


class WakeWatcher:
    """One per agent process: subscribe once, route pokes into driver inboxes.

    ``route`` maps a session id to that session's inbox, or to None when this
    process does not own the session. A callable rather than the registry
    itself, so the watcher stays testable and the registry stays unaware that
    redis exists.
    """

    def __init__(
        self,
        url: str,
        route: Callable[[str], Optional[Inbox]],
        log: Optional[Logger] = None,
    ) -> None:
        self.url = url
        self.route = route
        self.log = log or logger
        self._task: Optional[asyncio.Task] = None
        self._stopping = False

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Begin listening. Idempotent, and a no-op with no bus configured."""
        if not self.url:
            self.log.info("no redis_url configured — wake bus off, mailbox polling only")
            return
        if self.running:
            return
        self._stopping = False
        self._task = asyncio.create_task(self._listen(), name="crow-wake-watcher")

    async def stop(self) -> None:
        self._stopping = True
        task, self._task = self._task, None
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _listen(self) -> None:
        """Subscribe and route, reconnecting until stopped.

        A redis error never escapes: a bus that stays down must degrade to
        polling, not take the agent process with it. Cancellation does escape,
        because that is :meth:`stop` and swallowing it would hang shutdown.
        """
        while not self._stopping:
            client = aioredis.from_url(self.url, socket_connect_timeout=CONNECT_TIMEOUT_S)
            pubsub = client.pubsub()
            try:
                await pubsub.subscribe(CHANNEL)
                self.log.info("wake bus subscribed on %s", CHANNEL)
                while not self._stopping:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0
                    )
                    if message is not None:
                        self._route(message.get("data"))
            except asyncio.CancelledError:
                raise
            except (RedisError, OSError) as exc:
                self.log.warning(
                    "wake bus dropped (%s) — reconnecting in %.0fs", exc, RECONNECT_S
                )
                await asyncio.sleep(RECONNECT_S)
            finally:
                with contextlib.suppress(Exception):
                    await pubsub.aclose()
                with contextlib.suppress(Exception):
                    await client.aclose()

    def _route(self, raw: Any) -> None:
        poke = Poke.decode(raw)
        if poke is None:
            return
        inbox = self.route(poke.session_id)
        if inbox is None:
            self.log.debug("wake for session %s is not ours", poke.session_id)
            return
        inbox.put_nowait(
            Delivery(task_id=poke.task_id, priority=poke.priority, kind=poke.kind)
        )
        self.log.info(
            "wake routed to session %s (task %s, %s)",
            poke.session_id,
            poke.task_id or "-",
            poke.priority,
        )
