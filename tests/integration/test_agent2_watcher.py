"""The wake bus, against the redis the compose file actually runs.

No fake, and the reason is the subject matter. What is under test here IS the
wire behaviour of a fire-and-forget pub/sub: what a subscriber does with a
message it cannot decode, what a publisher does when nobody is listening,
whether a bus that stays down takes the agent process with it. An in-memory
stand-in would answer none of those, and would pass whatever it was handed.

Skip rather than fall back when the bus is missing: a wake test that runs
against nothing is a test that asserts the polling path, which is a different
test with a different meaning.
"""

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager

import pytest
import redis
import redis.asyncio as aioredis

from crow_cli.agent2.events import Delivery, new_inbox
from crow_cli.agent2.watcher import WakeWatcher
from crow_cli.wake import CHANNEL, Poke, publish_wake

REDIS_URL = os.getenv("CROW_REDIS_URL", "redis://localhost:6379/0")
#: A port nothing listens on. The dead-bus test needs a real refusal, not a
#: mocked one: ECONNREFUSED and "the client raised what we told it to" are
#: different claims.
DEAD_URL = "redis://localhost:6399/0"


def _bus_available() -> bool:
    try:
        client = redis.from_url(REDIS_URL, socket_connect_timeout=1.0, socket_timeout=1.0)
        client.ping()
        client.close()
        return True
    except Exception:
        return False


requires_bus = pytest.mark.skipif(
    not _bus_available(), reason=f"no redis at {REDIS_URL} (compose up -d redis)"
)


async def _await_subscriber(timeout: float = 10.0) -> None:
    """Block until the server has registered a subscription on our channel.

    ``start()`` returns as soon as the listen task exists, not as soon as it
    has subscribed, so a publish issued straight after it would race. Asking
    the server is the only honest readiness signal — it is the party that
    decides whether a message has anywhere to go.
    """
    client = aioredis.from_url(REDIS_URL)
    try:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            pairs = await client.pubsub_numsub(CHANNEL)
            if pairs and pairs[0][1] >= 1:
                return
            await asyncio.sleep(0.05)
        raise AssertionError(f"nothing subscribed to {CHANNEL} within {timeout}s")
    finally:
        await client.aclose()


@asynccontextmanager
async def bus(inboxes: dict):
    """A watcher routing session id -> inbox, subscribed and ready."""
    watcher = WakeWatcher(REDIS_URL, lambda sid: inboxes.get(sid))
    await watcher.start()
    await _await_subscriber()
    try:
        yield watcher
    finally:
        await watcher.stop()


async def _raw_publish(payload) -> None:
    client = aioredis.from_url(REDIS_URL)
    try:
        await client.publish(CHANNEL, payload)
    finally:
        await client.aclose()


@requires_bus
async def test_a_published_poke_lands_in_the_inbox_that_owns_the_session():
    inbox = new_inbox()
    async with bus({"sess-owned": inbox}):
        published = await publish_wake(
            REDIS_URL,
            Poke(session_id="sess-owned", task_id="task-7", priority="high", kind="celery"),
        )
        assert published is True
        event = await asyncio.wait_for(inbox.get(), timeout=10.0)

    assert isinstance(event, Delivery)
    assert event.task_id == "task-7"
    assert event.priority == "high"
    assert event.kind == "celery"


@requires_bus
async def test_a_poke_for_a_foreign_session_is_dropped_without_disturbing_ours():
    mine = new_inbox()
    async with bus({"sess-mine": mine}):
        await publish_wake(REDIS_URL, Poke(session_id="sess-theirs", task_id="task-1"))
        # Proving a negative needs a positive beside it: a second poke for a
        # session we DO own has to arrive, which is what distinguishes "the
        # watcher saw the first one and chose to drop it" from "the first one
        # never reached anyone and the bus is broken".
        await publish_wake(REDIS_URL, Poke(session_id="sess-mine", task_id="task-2"))
        event = await asyncio.wait_for(mine.get(), timeout=10.0)

    assert event.task_id == "task-2"
    assert mine.empty()


@requires_bus
async def test_garbage_on_the_channel_is_dropped_and_the_watcher_keeps_listening():
    inbox = new_inbox()
    async with bus({"sess-garbage": inbox}) as watcher:
        await _raw_publish("this is not json at all")
        # Well-formed JSON, missing the one required field: decode must reject
        # it rather than build a Poke with no address to route by.
        await _raw_publish(json.dumps({"task_id": "task-orphan", "priority": "high"}))
        await asyncio.sleep(0.3)
        assert watcher.running is True

        await publish_wake(REDIS_URL, Poke(session_id="sess-garbage", task_id="task-3"))
        event = await asyncio.wait_for(inbox.get(), timeout=10.0)

    assert event.task_id == "task-3"
    assert inbox.empty()


@requires_bus
async def test_a_newer_publisher_can_add_keys_an_old_subscriber_ignores():
    inbox = new_inbox()
    async with bus({"sess-forward": inbox}):
        await _raw_publish(
            json.dumps(
                {
                    "session_id": "sess-forward",
                    "task_id": "task-4",
                    "priority": "low",
                    "kind": "self_prompt",
                    # Neither exists on Poke. Publisher and subscriber are
                    # different processes and will not be upgraded together,
                    # so an unknown key has to be survivable.
                    "deliver_at": "2030-01-01T00:00:00Z",
                    "hops": 3,
                }
            )
        )
        event = await asyncio.wait_for(inbox.get(), timeout=10.0)

    assert (event.task_id, event.kind) == ("task-4", "self_prompt")


@requires_bus
async def test_a_bus_that_is_not_there_degrades_instead_of_raising():
    inbox = new_inbox()
    watcher = WakeWatcher(DEAD_URL, lambda sid: inbox)
    await watcher.start()
    try:
        # Give the first connect attempt time to fail and the retry loop time
        # to be inside its backoff. If the exception escaped, the task would
        # be done by now.
        await asyncio.sleep(1.0)
        assert watcher.running is True
        assert inbox.empty()
        # And the publisher says so rather than blowing up a caller that has
        # already committed the mailbox row.
        assert await publish_wake(DEAD_URL, Poke(session_id="sess-dead")) is False

        stopped_at = time.monotonic()
        await watcher.stop()
        elapsed = time.monotonic() - stopped_at
    finally:
        await watcher.stop()
    # stop() cancels; it must not sit out the reconnect backoff. Shutdown
    # latency is the one thing a degraded bus is still allowed to cost us.
    assert elapsed < 4.0, f"stop() took {elapsed:.1f}s"
    assert watcher.running is False


@requires_bus
async def test_no_url_means_no_bus_and_nothing_to_stop():
    watcher = WakeWatcher("", lambda sid: None)
    await watcher.start()
    assert watcher.running is False
    await watcher.stop()  # never started: must be a no-op, not an error
    assert await publish_wake("", Poke(session_id="sess-anywhere")) is False


def test_a_poke_survives_its_own_round_trip():
    poke = Poke(session_id="s", task_id="t", priority="high", kind="timer")
    assert Poke.decode(poke.encode()) == poke
    assert Poke.decode(poke.encode().encode()) == poke
    assert Poke.decode("}{") is None
    assert Poke.decode(None) is None
