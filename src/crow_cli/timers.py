"""Scheduled wakes: celery is the timer wheel, the mailbox is still the truth.

A session that wants to be woken later — "check the build in ten minutes",
"come back to this queue once it has drained" — has nowhere to put that want.
The agent process cannot hold it. A driver that sleeps is a driver that cannot
be prompted or cancelled, and a sleep that outlives the process is a sleep that
never fires; restarts, compaction and client disconnects are all ordinary here.

So the wait goes to a scheduler that lives somewhere else, and celery is that
scheduler and nothing more. ``apply_async(countdown=N)`` is a timer wheel with
a broker behind it, which is precisely the piece crow has no business
reimplementing: there is no ``deliver_at`` column, no wheel in the driver, no
cron sweep and no migration. What crow keeps is the part that has to be durable
and inspectable — the mailbox — and the job body below does the same two things
a task watcher does, in the same order:

1. :func:`crow_cli.memory.writes.finish_task` flips the row terminal and lands
   the delivery in the owner's mailbox in ONE commit;
2. :func:`crow_cli.wake.publish_wake` tells the owner to go look.

Row first, poke second, so a worker killed between the two costs latency — the
owner's backstop poll finds the row — rather than spending a turn on a wake
with nothing behind it. And ``finish_task`` is idempotent, which is what makes
celery's at-least-once delivery safe instead of merely tolerable: a job
redelivered after a crash finds the row already terminal, lands nothing a
second time, and publishes nothing.

Everything the job needs rides in the message. A worker is not an agent and has
no rail — no cell identity, no prologue-injected ``db_uri``, no config object —
so the scheduling side puts the database and the bus on the payload and the
worker reads them back. The owner, the priority, the kind and the note do NOT
ride along: they are on the row, and the row is the truth. A payload that
carried them could disagree with it, and then there would be two answers.

The worker therefore needs a broker and nothing else. It does need to reach
the same database — for sqlite that means the same filesystem, which is the
same constraint every other crow process already lives under.

This module is a sibling of :mod:`crow_cli.wake` rather than part of
:mod:`crow_cli.agent2` for the reason ``wake`` is: it is imported by a process
that will never serve a session.
"""

from __future__ import annotations

import asyncio
import os
from urllib.parse import urlsplit, urlunsplit

from celery import Celery
from sqlalchemy.exc import OperationalError

from crow_cli.memory import get_engine
from crow_cli.memory.reads import get_task
from crow_cli.memory.writes import finish_task, launch_next_task
from crow_cli.wake import Poke, publish_wake

#: The wake bus is db 0. Celery gets two of its own so that walking the
#: broker's keyspace never walks the bus's, and so a test that has to flush a
#: stale queue cannot take somebody's subscription with it. Pub/sub itself is
#: NOT namespaced by database — a poke published from db 1 is received by a
#: subscriber on db 0 — which is what lets the worker reuse ``publish_wake``
#: unchanged.
BROKER_DB = 1
RESULT_DB = 2

#: ``Task.kind`` for a scheduled wake. Free text on the row, so a new wake
#: source costs no migration, and a client that has never heard of this one
#: still renders the task and still gets its mailbox message.
KIND = "timer"

#: One queue, one name. A worker started against a different queue starves
#: silently, which is worse than a constant nobody has a reason to override.
QUEUE = "crow"

#: How many times a job survives the database being briefly unavailable.
#: sqlite's busy_timeout is 5s and the agent writes constantly, so the first
#: attempt can lose — and giving up there loses the wake outright, which is
#: the one outcome the mailbox exists to prevent.
MAX_RETRIES = 5


def default_redis_url() -> str:
    """The fallback chain :meth:`Config.load` uses, for the one caller that
    has no config: ``celery -A crow_cli.timers:app worker``."""
    return os.getenv("CROW_REDIS_URL") or (
        f"redis://localhost:{os.getenv('REDIS_PORT', '6379')}/0"
    )


def database_url(redis_url: str, db: int) -> str:
    """The same redis server, a different logical database.

    The path is replaced wholesale rather than edited: no path, ``/0`` and
    ``/07`` all mean the same thing to this function, and the query string —
    ``?ssl=true``, a credential — is the part that has to survive.
    """
    parts = urlsplit(redis_url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{db}", parts.query, ""))


def configure(target: Celery, redis_url: str) -> Celery:
    """Point an app at one redis. Returns it, so a caller can chain."""
    target.conf.update(
        broker_url=database_url(redis_url, BROKER_DB),
        result_backend=database_url(redis_url, RESULT_DB),
    )
    return target


#: Settings that do not depend on which redis we are pointed at.
_SETTINGS: dict = {
    "task_default_queue": QUEUE,
    "task_default_routing_key": QUEUE,
    # A worker that dies mid-job must not swallow the wake. Safe precisely
    # because finish_task is idempotent: a redelivery that finds a terminal
    # row does nothing at all.
    "task_acks_late": True,
    "task_reject_on_worker_lost": True,
    "broker_connection_retry_on_startup": True,
    "timezone": "UTC",
    "enable_utc": True,
}

#: The job's wire name. A worker finds the body by this string in
#: ``app.tasks``, so renaming it is a deployment event and not a refactor: a
#: job enqueued by an old scheduler arrives at a new worker that has never
#: heard of it, and sits in the queue unclaimed.
TASK_NAME = "crow.fire_timer"


def fire_timer(task_id: str, db_uri: str, redis_url: str) -> dict:
    """Close one timer row and wake its owner. This is the whole job.

    A plain function, registered onto an app by :func:`make_app` rather than
    declared with a decorator, so the row-and-mailbox half of it is callable
    with no broker in sight. Everything below the ``publish_wake`` line is
    celery's; everything above it is crow's, and only crow's half needs a
    database to test against.

    Returns a dict rather than None because the result backend is already
    there and "did the timer fire" is exactly what somebody asks afterwards.
    ``landed`` False means the row was already terminal — a redelivery, or a
    ``task_cancel`` that won the race — or never existed; in neither case is
    there anything to deliver and nothing is published.
    """
    engine = get_engine(db_uri)
    try:
        row = get_task(engine, task_id)
        if row is None:
            return {"task_id": task_id, "landed": False, "reason": "no such task"}
        note = row.prompt or ""
        content = f"[{task_id}: timer fired]"
        if note:
            content = f"{content}\n{note}"
        landed = finish_task(
            engine, task_id, result=note, status="completed", content=content
        )
        if not landed:
            return {"task_id": task_id, "landed": False, "reason": "already terminal"}
        poked = asyncio.run(
            publish_wake(
                redis_url,
                Poke(
                    session_id=row.owner_session,
                    task_id=task_id,
                    priority=row.priority,
                    kind=row.kind,
                ),
            )
        )
        return {"task_id": task_id, "landed": True, "poked": poked}
    finally:
        engine.dispose()


def make_app(redis_url: str) -> Celery:
    """Build one configured app, job registered, against one redis.

    A factory rather than a reconfigured global because celery caches the
    broker connection ON the app, and a connection that failed once keeps
    failing — "the Celery application must be restarted" — for the life of the
    process. Anything that wants a different broker therefore wants a
    different app, not a mutation of this one.
    """
    target = Celery("crow")
    target.conf.update(_SETTINGS)
    configure(target, redis_url)
    target.task(
        name=TASK_NAME,
        autoretry_for=(OperationalError,),
        retry_backoff=True,
        retry_backoff_max=60,
        retry_jitter=True,
        max_retries=MAX_RETRIES,
    )(fire_timer)
    return target


#: The app a deployment uses. ``celery -A crow_cli.timers:app worker``
#: resolves this, and so does ``crow-cli timers``.
app = make_app(default_redis_url())


def schedule_timer(
    engine,
    *,
    db_uri: str,
    redis_url: str,
    owner: str,
    delay: float,
    note: str = "",
    priority: str = "low",
    tool_call_id: str | None = None,
    target: Celery | None = None,
) -> str:
    """Mint a timer row and enqueue its wake ``delay`` seconds from now.

    Returns the ``task_id``, which is the owner's handle from then on:
    ``task_read`` it, or ``task_cancel`` it before it fires and the row goes
    terminal with the cancel winning the race against the job. It is an
    ordinary task row in every respect but ``kind``, and that is the point —
    the mailbox, the poke, the parking driver and the read surface all already
    work, and none of them had to learn anything new.

    The row is committed BEFORE the enqueue, and closed as ``failed`` with no
    delivery if the enqueue raises: the caller gets the exception, and a
    mailbox message saying the same thing would be the second telling. Leaving
    it ``running`` instead would be worse than either — the owner would park on
    a wake that is never coming.

    ``target`` is the app to enqueue on, and defaults to this module's. It
    exists because an app whose broker connection has failed once is unusable
    for the rest of the process (see :func:`make_app`), so a caller that wants
    to point at a different redis — or to find out what a dead one does —
    needs its own.
    """
    task_id = launch_next_task(
        engine,
        owner_session=owner,
        kind=KIND,
        tool_call_id=tool_call_id,
        prompt=note,
        priority=priority,
    )
    try:
        (target or app).tasks[TASK_NAME].apply_async(
            args=(task_id, db_uri, redis_url), countdown=delay
        )
    except Exception as exc:
        finish_task(
            engine,
            task_id,
            result=f"{type(exc).__name__}: {exc}",
            status="failed",
            deliver=False,
        )
        raise
    return task_id


def run_worker(redis_url: str, *, concurrency: int = 1, loglevel: str = "INFO") -> None:
    """Start the worker against one redis and block.

    One worker process is enough: a timer job is two sqlite statements and a
    publish, so the queue is never the bottleneck and a second consumer would
    only make the ordering of two timers that fire together less predictable.
    """
    configure(app, redis_url)
    app.worker_main(
        argv=[
            "worker",
            f"--concurrency={concurrency}",
            f"--loglevel={loglevel}",
            f"--queues={QUEUE}",
            "--hostname=crow-timers@%h",
        ]
    )
