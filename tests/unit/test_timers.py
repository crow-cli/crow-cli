"""The timer half of the wake bus, with no broker and no worker in sight.

Everything here is crow's half of :mod:`crow_cli.timers`: the URL arithmetic
that gives celery two databases of its own, and the job body's row-and-mailbox
work. Celery's half — a message crossing a socket, a countdown actually
counting down, a worker picking it up — is
``tests/integration/test_timers_live.py``, because none of it is observable
without a broker and a broker is not a unit.

``fire_timer`` is called directly rather than through ``apply_async``. That is
not a way of getting around the code under test: it is the same function object
a worker resolves out of ``app.tasks`` by name, and calling it here is what
lets the assertions be about the database instead of about a race.
"""

from __future__ import annotations

import pytest

from crow_cli.memory.db import create_database, get_engine
from crow_cli.memory.reads import (
    get_task,
    owner_tasks,
    pending_deliveries,
    running_tasks,
)
from crow_cli.memory.writes import cancel_task, launch_next_task
from crow_cli.timers import (
    BROKER_DB,
    KIND,
    QUEUE,
    RESULT_DB,
    TASK_NAME,
    configure,
    database_url,
    default_redis_url,
    fire_timer,
    make_app,
)

OWNER = "brave-otter-of-judgment"


@pytest.fixture
def rail(tmp_path):
    """A database and a write engine on it: the two things a job body needs.

    No cell, no identity rail, no config — a worker has none of those either,
    and the point of the payload is that it does not need them.
    """
    uri = f"sqlite:///{tmp_path / 'timers.db'}"
    create_database(uri)
    engine = get_engine(uri)
    try:
        yield engine, uri
    finally:
        engine.dispose()


def _mint(engine, *, note="check the build", **kw):
    """A timer row the way schedule_timer mints it, minus the enqueue."""
    return launch_next_task(
        engine, owner_session=OWNER, kind=KIND, prompt=note, **kw
    )


# -- the databases ---------------------------------------------------------


def test_the_bus_keeps_db_zero_and_celery_gets_the_next_two():
    assert (BROKER_DB, RESULT_DB) == (1, 2)
    assert database_url("redis://localhost:6379/0", BROKER_DB) == "redis://localhost:6379/1"
    assert database_url("redis://localhost:6379/0", RESULT_DB) == "redis://localhost:6379/2"


def test_the_swap_keeps_the_credentials_and_the_query():
    """The path is the only part that means "which database". Everything else
    is how you reach the server at all, and dropping it would hand the worker
    a broker it cannot authenticate against."""
    assert (
        database_url("redis://:pw@h:6380/0?ssl=true", BROKER_DB)
        == "redis://:pw@h:6380/1?ssl=true"
    )
    assert database_url("redis://h:6379", RESULT_DB) == "redis://h:6379/2"


def test_the_default_url_is_the_config_fallback_chain(monkeypatch):
    """The same chain Config.load walks, for the one caller that has no
    config: a bare ``celery -A crow_cli.timers:app worker``."""
    monkeypatch.delenv("CROW_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_PORT", raising=False)
    assert default_redis_url() == "redis://localhost:6379/0"
    monkeypatch.setenv("REDIS_PORT", "6390")
    assert default_redis_url() == "redis://localhost:6390/0"
    monkeypatch.setenv("CROW_REDIS_URL", "redis://elsewhere:6379/0")
    assert default_redis_url() == "redis://elsewhere:6379/0"


def test_make_app_points_one_redis_at_three_databases():
    target = make_app("redis://h:6379/0")
    assert target.conf.broker_url == "redis://h:6379/1"
    assert target.conf.result_backend == "redis://h:6379/2"
    assert target.conf.task_default_queue == QUEUE
    assert TASK_NAME in target.tasks
    # acks_late is what makes a worker killed mid-job redeliver rather than
    # swallow the wake. It is only safe because finish_task is idempotent.
    assert target.conf.task_acks_late is True
    assert target.conf.task_reject_on_worker_lost is True


def test_make_app_gives_each_caller_its_own_broker():
    """Two apps, two brokers, no shared connection to poison. Celery caches
    the connection on the app, so this is the only way to talk to a second
    redis from one process."""
    one, two = make_app("redis://one:6379/0"), make_app("redis://two:6379/0")
    assert one is not two
    assert one.conf.broker_url == "redis://one:6379/1"
    assert two.conf.broker_url == "redis://two:6379/1"


def test_configure_repoints_an_app_that_has_not_connected():
    target = make_app("redis://h:6379/0")
    assert configure(target, "redis://other:6379/5") is target
    assert target.conf.broker_url == "redis://other:6379/1"
    assert target.conf.result_backend == "redis://other:6379/2"


# -- the job body ----------------------------------------------------------


def test_a_fired_timer_closes_its_row_and_lands_the_delivery(rail):
    engine, uri = rail
    task_id = _mint(engine)

    # An empty redis_url is the bus being off, which publish_wake treats as a
    # configuration and not an error — so poked is False and nothing dials.
    assert fire_timer(task_id, uri, "") == {
        "task_id": task_id,
        "landed": True,
        "poked": False,
    }

    row = get_task(engine, task_id)
    assert row.status == "completed"
    assert row.result == "check the build"
    assert row.finished_at is not None
    assert running_tasks(engine, OWNER) == []

    box = pending_deliveries(engine, OWNER)
    assert [d.task_id for d in box] == [task_id]
    assert box[0].content == f"[{task_id}: timer fired]\ncheck the build"


def test_a_timer_with_no_note_still_says_it_fired(rail):
    """The wake is the point, not the text. A bare "in ten minutes" with no
    note still has to inject something, or the session wakes to silence."""
    engine, uri = rail
    task_id = _mint(engine, note="")
    assert fire_timer(task_id, uri, "")["landed"] is True
    assert pending_deliveries(engine, OWNER)[0].content == f"[{task_id}: timer fired]"
    assert get_task(engine, task_id).result == ""


def test_a_redelivered_job_does_not_deliver_twice(rail):
    """Celery is at-least-once, and acks_late makes that deliberate: a worker
    killed after the commit gets the message again. The row is already
    terminal, so the second arrival lands nothing and publishes nothing. That
    is why the idempotence lives in finish_task and not in each caller."""
    engine, uri = rail
    task_id = _mint(engine, note="once")
    assert fire_timer(task_id, uri, "")["landed"] is True
    assert fire_timer(task_id, uri, "") == {
        "task_id": task_id,
        "landed": False,
        "reason": "already terminal",
    }
    assert len(pending_deliveries(engine, OWNER)) == 1


def test_a_job_for_a_row_that_never_existed_says_so(rail):
    """A broker that outlives its database — a restored backup, a wiped
    sqlite — will still hand over the message. Nothing to close, nothing to
    deliver, and a reason in the result rather than a KeyError in a log."""
    engine, uri = rail
    assert fire_timer("task-99", uri, "") == {
        "task_id": "task-99",
        "landed": False,
        "reason": "no such task",
    }
    assert pending_deliveries(engine, OWNER) == []


def test_a_cancel_wins_the_race_and_the_job_fires_into_nothing(rail):
    """Cancelling before the countdown ends is supported because the row is an
    ordinary task row, so the ordinary handle works on it. The job still runs;
    it finds a terminal row and stops."""
    engine, uri = rail
    task_id = _mint(engine, note="never mind")
    assert cancel_task(engine, task_id) is True
    assert fire_timer(task_id, uri, "")["landed"] is False
    assert pending_deliveries(engine, OWNER) == []
    assert get_task(engine, task_id).status == "cancelled"


def test_the_owner_and_priority_are_read_off_the_row(rail):
    """Nothing about WHO to wake rides in the message. A payload that carried
    the owner could disagree with the row, and then there would be two answers
    to "whose timer is this" and no way to reconcile them."""
    engine, uri = rail
    task_id = _mint(engine, note="high stakes", priority="high")
    assert fire_timer(task_id, uri, "")["landed"] is True
    box = pending_deliveries(engine, OWNER)
    assert box[0].session_id == OWNER
    assert box[0].priority == "high"


# -- the row ---------------------------------------------------------------


def test_a_timer_row_is_an_ordinary_task_row(rail):
    """The claim the design rests on: kind is free text, so a new wake source
    costs no migration, and every surface that already works on a task row —
    the mailbox, task_read, the parking driver — works on a timer unchanged."""
    engine, _ = rail
    task_id = _mint(engine, note="in ten minutes", tool_call_id="call-abc")
    row = get_task(engine, task_id)
    assert row.kind == "timer"
    assert row.status == "running"
    assert row.owner_session == OWNER
    assert row.tool_call_id == "call-abc"
    assert row.sub_session is None, "no child was ever spawned"
    assert [t.task_id for t in owner_tasks(engine, OWNER)] == [task_id]
    assert [t.task_id for t in running_tasks(engine, OWNER)] == [task_id]


def test_timers_and_subagents_share_one_id_space(rail):
    """One counter, because there is one mailbox and one task_read(). A timer
    minted off its own sequence would collide with the first subagent a
    session launches, and the UNIQUE constraint would turn that into an error
    the model can do nothing about."""
    engine, _ = rail
    first = launch_next_task(engine, owner_session=OWNER, kind="subagent", prompt="a child")
    second = launch_next_task(engine, owner_session=OWNER, kind=KIND, prompt="a timer")
    assert (first, second) == ("task-1", "task-2")
    assert [t.kind for t in owner_tasks(engine, OWNER)] == ["subagent", "timer"]
