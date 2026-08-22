"""TaskRegistry — the in-process shared state behind delegation interiority."""

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


async def test_wake_queue_only_for_registered_sessions():
    r = TaskRegistry()
    info = r.launch("delegate", "sess-1", "c")
    r.finish(info.task_id, "done!")  # no queue registered -> nothing to wake
    assert r.pending() == []
