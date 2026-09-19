"""The timer worker, for real: a celery process, a redis broker, a countdown.

The unit tier calls ``fire_timer`` directly and asserts on the database. What
it cannot show is the part that makes a timer a timer — a message sitting in a
broker until its countdown expires, a worker that is not this process picking
it up, and a poke arriving on a socket. All three are here.

The worker consumes a queue named for this process, so a crow deployment
sharing the same redis never sees these messages, and an aborted run never
leaves behind a consumer firing timers for tests that are gone.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import pathlib
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field

import pytest
import redis
import redis.asyncio as aioredis

from crow_cli.memory.db import create_database, get_engine
from crow_cli.memory.reads import get_task, owner_tasks, pending_deliveries
from crow_cli.memory.writes import cancel_task
from crow_cli.timers import KIND, make_app, schedule_timer
from crow_cli.wake import CHANNEL, Poke

OWNER = "brave-otter-of-judgment"
REDIS_URL = os.getenv("CROW_REDIS_URL", "redis://localhost:6379/0")
DEAD_URL = "redis://localhost:6399/0"
REPO = pathlib.Path(__file__).resolve().parents[2]

#: A worker start is an interpreter, a celery import and a broker handshake.
READY_TIMEOUT = 120.0
#: The countdowns below are seconds; this is slack for a slow worker.
FIRE_TIMEOUT = 90.0


def _bus_available() -> bool:
    try:
        client = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=2.0)
        client.ping()
        client.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _bus_available(), reason=f"no redis at {REDIS_URL}"
)


# -- the worker ------------------------------------------------------------


@dataclass
class Worker:
    """A celery worker subprocess, and the log it is writing."""

    queue: str
    proc: subprocess.Popen
    lines: list = field(default_factory=list)

    def ready(self, timeout: float = READY_TIMEOUT) -> None:
        """Wait for the banner's "ready." — the only honest signal that the
        consumer exists. Polling the queue instead would prove a message can
        be enqueued, not that anything will take it off."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if any("ready." in line for line in self.lines):
                return
            if self.proc.poll() is not None:
                raise AssertionError(
                    f"the worker exited {self.proc.returncode}:\n"
                    + "\n".join(self.lines[-40:])
                )
            time.sleep(0.05)
        raise AssertionError(
            f"the worker was not ready within {timeout}s:\n"
            + "\n".join(self.lines[-40:])
        )


@pytest.fixture(scope="module")
def worker():
    """One real worker for the module.

    Module scope rather than session: a consumer that outlives the file that
    started it would fire timers for tests that are no longer there to assert
    anything about them.
    """
    pid = os.getpid()
    queue = f"crow-test-{pid}"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "crow_cli.timers:app",
            "worker",
            f"--queues={queue}",
            "--pool=solo",
            "--loglevel=INFO",
            f"--hostname=crow-test-{pid}@%h",
        ],
        cwd=str(REPO),
        env={**os.environ, "CROW_REDIS_URL": REDIS_URL},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    running = Worker(queue=queue, proc=proc)

    def drain() -> None:
        # readline in a thread, never proc.stdout.read(): a pipe nobody is
        # draining fills, and the worker blocks instead of logging.
        for line in proc.stdout:
            running.lines.append(line.rstrip())

    threading.Thread(target=drain, daemon=True).start()
    try:
        running.ready()
        yield running
    finally:
        proc.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=30)
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


@pytest.fixture
def scheduler(worker):
    """An app that publishes onto this worker's queue and nowhere else.

    A fresh app per test, because celery caches the broker connection on the
    app and a connection that has failed once keeps failing for the life of
    the process — the dead-broker test below would otherwise poison this one.
    """
    target = make_app(REDIS_URL)
    target.conf.update(
        task_default_queue=worker.queue,
        task_default_routing_key=worker.queue,
    )
    return target


@pytest.fixture
def rail(tmp_path):
    uri = f"sqlite:///{tmp_path / 'timers.db'}"
    create_database(uri)
    engine = get_engine(uri)
    try:
        yield engine, uri
    finally:
        engine.dispose()


# -- the bus ---------------------------------------------------------------


async def _subscribe():
    """A client, a subscription, and proof the server recorded it.

    Waiting for the count to RISE rather than to reach one: this machine may
    well be running a real crow agent that is already subscribed to the same
    channel, and a test that only checked for "somebody" would publish into
    the gap before its own subscription landed.
    """
    probe = aioredis.from_url(REDIS_URL)
    try:
        pairs = await probe.pubsub_numsub(CHANNEL)
        before = pairs[0][1] if pairs else 0
    finally:
        await probe.aclose()

    client = aioredis.from_url(REDIS_URL)
    pubsub = client.pubsub()
    await pubsub.subscribe(CHANNEL)

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        probe = aioredis.from_url(REDIS_URL)
        try:
            pairs = await probe.pubsub_numsub(CHANNEL)
            if pairs and pairs[0][1] > before:
                return client, pubsub
        finally:
            await probe.aclose()
        await asyncio.sleep(0.05)
    await pubsub.aclose()
    await client.aclose()
    raise AssertionError(f"the subscription to {CHANNEL} never registered")


async def _next_poke(pubsub, session_id: str, timeout: float = FIRE_TIMEOUT) -> Poke:
    """The next poke for ``session_id``, skipping everybody else's.

    One channel serves the whole deployment, so a subscriber has to expect
    traffic it does not own — that is the design, and a test had better not
    trip over it.
    """

    async def poll():
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=0.5
            )
            if message is not None and message.get("type") == "message":
                poke = Poke.decode(message["data"])
                if poke is not None and poke.session_id == session_id:
                    return poke
            await asyncio.sleep(0.02)

    return await asyncio.wait_for(poll(), timeout)


async def settled(engine, task_id: str, timeout: float = FIRE_TIMEOUT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = get_task(engine, task_id)
        if row is not None and row.status != "running":
            return row
        await asyncio.sleep(0.05)
    raise AssertionError(f"{task_id} was still running after {timeout}s")


# -- the tests -------------------------------------------------------------


async def test_a_scheduled_timer_fires_and_wakes_its_owner(rail, scheduler):
    """The whole chain with a real worker in the middle: schedule, broker,
    countdown, a process that is not this one, and then the row terminal, the
    delivery in the mailbox and the poke on the channel."""
    engine, uri = rail
    client, pubsub = await _subscribe()
    try:
        task_id = schedule_timer(
            engine,
            db_uri=uri,
            redis_url=REDIS_URL,
            owner=OWNER,
            delay=1,
            note="check the build",
            priority="high",
            tool_call_id="call-abc",
            target=scheduler,
        )
        row = get_task(engine, task_id)
        assert row.kind == KIND
        assert row.status == "running"
        assert row.tool_call_id == "call-abc"
        assert row.sub_session is None

        poke = await _next_poke(pubsub, OWNER)
        assert poke.task_id == task_id
        assert poke.priority == "high"
        assert poke.kind == KIND

        # Row first, poke second — and read ONCE, with no polling, because
        # that is the whole claim: with the poke in hand the row is already
        # terminal and the delivery already claimable by whoever it just woke.
        # A poll here would pass under the inverted order too, and the
        # inversion is the bug this asserts against.
        row = get_task(engine, task_id)
        assert row.status == "completed"
        assert row.result == "check the build"
        box = pending_deliveries(engine, OWNER)
        assert [d.task_id for d in box] == [task_id]
        assert box[0].priority == "high"
        assert box[0].content == f"[{task_id}: timer fired]\ncheck the build"
    finally:
        await pubsub.aclose()
        await client.aclose()


async def test_the_countdown_is_actually_counting(rail, scheduler):
    """``delay`` is not a hint. A timer that fires early is worse than one
    that fires late: the session gets its turn back before the thing it was
    waiting on has had time to happen."""
    engine, uri = rail
    task_id = schedule_timer(
        engine, db_uri=uri, redis_url="", owner=OWNER, delay=8,
        note="not yet", target=scheduler,
    )
    await asyncio.sleep(3.0)
    assert get_task(engine, task_id).status == "running"
    assert pending_deliveries(engine, OWNER) == []
    row = await settled(engine, task_id)
    assert row.status == "completed"
    assert row.result == "not yet"


async def test_a_cancel_before_the_fire_leaves_nothing_to_deliver(rail, scheduler):
    """The row is an ordinary task row, so ``task_cancel`` works on a timer
    and the job that still arrives finds it terminal. No delivery and no
    poke: the owner asked for the cancel, so it already knows."""
    engine, uri = rail
    client, pubsub = await _subscribe()
    try:
        task_id = schedule_timer(
            engine, db_uri=uri, redis_url=REDIS_URL, owner=OWNER, delay=2,
            note="never mind", target=scheduler,
        )
        assert cancel_task(engine, task_id) is True
        assert get_task(engine, task_id).status == "cancelled"

        # Long enough for the countdown to expire and the job to run into a
        # terminal row. Nothing to wait on: the assertion is that nothing
        # happens, so the only proof is the passage of time.
        await asyncio.sleep(12.0)
        assert get_task(engine, task_id).status == "cancelled"
        assert pending_deliveries(engine, OWNER) == []
        with pytest.raises(TimeoutError):
            await _next_poke(pubsub, OWNER, timeout=2.0)
    finally:
        await pubsub.aclose()
        await client.aclose()


def test_a_dead_broker_closes_the_row_instead_of_stranding_it(rail):
    """The failure that matters. A timer that cannot be scheduled must not
    leave a row saying "running" behind it — the owner would park on a wake
    that is never coming, which is the one outcome the mailbox exists to
    prevent.

    Slow, and deliberately so: celery retries the broker and then the result
    backend before it gives up, and that retry is what a deployment actually
    experiences. The exception type is not asserted for the same reason — it
    is kombu's OperationalError or celery's RuntimeError depending on which of
    the two gave up first, and crow's contract is only that SOMETHING raised.
    """
    engine, uri = rail
    with pytest.raises(Exception):
        schedule_timer(
            engine, db_uri=uri, redis_url=REDIS_URL, owner=OWNER, delay=1,
            note="nowhere", target=make_app(DEAD_URL),
        )

    rows = owner_tasks(engine, OWNER)
    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert rows[0].result, "the reason belongs on the row"
    assert rows[0].finished_at is not None
    assert pending_deliveries(engine, OWNER) == []
