"""TaskRegistry — the in-process shared state behind delegation interiority."""

import asyncio

import pytest

from crow_cli.agent.tasks import TaskRegistry


def test_launch_and_pending():
    r = TaskRegistry()
    info = r.launch("delegate", "sess-1", "call-1", sub_session="sub-1")
    assert info.task_id == "task-1"
    assert info.status == "running"
    assert [t.task_id for t in r.pending()] == ["task-1"]
    assert [t.task_id for t in r.pending("sess-1")] == ["task-1"]
    assert r.pending("other-session") == []


def test_finish_clears_pending_and_stores_result():
    r = TaskRegistry()
    info = r.launch("delegate", "sess-1", "call-1")
    r.finish(info.task_id, "the answer")
    assert r.pending() == []
    got = r.get(info.task_id)
    assert got.status == "done"
    assert got.result == "the answer"


def test_finish_statuses():
    r = TaskRegistry()
    a = r.launch("delegate", "s", "c1")
    b = r.launch("delegate", "s", "c2")
    r.finish(a.task_id, None, status="cancelled")
    r.finish(b.task_id, "boom", status="failed")
    assert r.get(a.task_id).status == "cancelled"
    assert r.get(b.task_id).status == "failed"


def test_finish_idempotent():
    r = TaskRegistry()
    info = r.launch("delegate", "s", "c")
    r.finish(info.task_id, "first")
    r.finish(info.task_id, "second")  # a finished task never changes again
    assert r.get(info.task_id).result == "first"


def test_finish_unknown_task_is_noop():
    r = TaskRegistry()
    r.finish("task-999", "x")  # must not raise


async def test_wake_queue_receives_completion():
    r = TaskRegistry()
    q = r.wake_queue("sess-1")
    info = r.launch("delegate", "sess-1", "c")
    r.finish(info.task_id, "done!")
    assert q.get_nowait() is info


async def test_launch_creates_wake_queue():
    """The queue exists from LAUNCH time: a fast subagent that finishes
    while the owner is still streaming cannot be lost (finish puts iff the
    queue exists; the owner drains it whenever it first parks)."""
    r = TaskRegistry()
    info = r.launch("delegate", "sess-1", "c")
    r.finish(info.task_id, "done!")  # owner never parked yet
    assert r.pending() == []
    assert r.wake_queue("sess-1").get_nowait() is info


async def test_cancel_all_marks_cancelled_and_cancels_handles():
    async def hang():
        await asyncio.Event().wait()

    r = TaskRegistry()
    a = r.launch("delegate", "sess-1", "c1", sub_session="sub-a")
    b = r.launch("delegate", "sess-1", "c2", sub_session="sub-b")
    other = r.launch("delegate", "sess-2", "c3")
    a.handle = asyncio.create_task(hang())
    b.handle = asyncio.create_task(hang())
    other.handle = asyncio.create_task(hang())

    handles = r.cancel_all("sess-1")
    assert {id(h) for h in handles} == {id(a.handle), id(b.handle)}
    assert r.get(a.task_id).status == "cancelled"
    assert r.get(b.task_id).status == "cancelled"
    # other session untouched
    assert r.get(other.task_id).status == "running"
    assert [t.task_id for t in r.pending("sess-1")] == []
    # the subagent's own cleanup finish() is an idempotent no-op now
    r.finish(a.task_id, "late result")
    assert r.get(a.task_id).result is None
    assert r.get(a.task_id).status == "cancelled"
    # let the cancelled tasks settle so no warnings leak
    for h in (a.handle, b.handle):
        with pytest.raises(asyncio.CancelledError):
            await h
    other.handle.cancel()
    with pytest.raises(asyncio.CancelledError):
        await other.handle


def test_cancel_all_ignores_finished_tasks():
    r = TaskRegistry()
    done = r.launch("delegate", "sess-1", "c1")
    r.finish(done.task_id, "answer")
    assert r.cancel_all("sess-1") == []
    assert r.get(done.task_id).status == "done"


# ---------------------------------------------------------------------------
# drain_dead — surfacing a cancelled turn's stranded tasks on the next prompt
# ---------------------------------------------------------------------------


def test_drain_dead_returns_cancelled_tasks_never_queued():
    """cancel_all marks cancelled BEFORE finish() runs, so finish() no-ops
    and nothing reaches the wake queue — drain_dead must still find them."""
    r = TaskRegistry()
    info = r.launch("delegate", "sess-1", "c1", sub_session="sub-1")
    r.cancel_all("sess-1")  # marks cancelled; nothing queued
    assert r.wake_queue("sess-1").empty()
    dead = r.drain_dead("sess-1")
    assert [t.task_id for t in dead] == ["task-1"]
    assert dead[0].status == "cancelled"


def test_drain_dead_returns_queued_completions():
    """A completion that landed on the wake queue but was never injected
    (cancel between park and injection) is also dead and must be surfaced."""
    r = TaskRegistry()
    info = r.launch("delegate", "sess-1", "c1")
    r.finish(info.task_id, "the answer")  # now sitting on the queue
    dead = r.drain_dead("sess-1")
    assert [t.task_id for t in dead] == ["task-1"]
    assert dead[0].status == "done"
    # the queue is cleared so a later park cannot re-deliver it
    assert r.wake_queue("sess-1").empty()


def test_drain_dead_is_idempotent():
    r = TaskRegistry()
    info = r.launch("delegate", "sess-1", "c1")
    r.cancel_all("sess-1")
    assert len(r.drain_dead("sess-1")) == 1
    assert r.drain_dead("sess-1") == []  # delivered once, never again


def test_drain_dead_skips_running_and_other_sessions():
    r = TaskRegistry()
    running = r.launch("delegate", "sess-1", "c1")
    other = r.launch("delegate", "sess-2", "c2")
    r.cancel_all("sess-2")  # other session's task dies
    dead = r.drain_dead("sess-1")
    assert dead == []  # running task not dead; other session not ours
    assert r.get(running.task_id).status == "running"
    assert [t.task_id for t in r.drain_dead("sess-2")] == ["task-2"]


def test_drain_dead_dedupes_queued_and_registered():
    """A task both on the queue and in _tasks is returned exactly once."""
    r = TaskRegistry()
    info = r.launch("delegate", "sess-1", "c1")
    r.finish(info.task_id, "x")  # on the queue AND terminal in _tasks
    dead = r.drain_dead("sess-1")
    assert [t.task_id for t in dead] == ["task-1"]
