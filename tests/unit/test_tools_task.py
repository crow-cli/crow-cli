"""task: the four subtools that launch, steer, stop and read a subagent.

Everything here stops BEFORE a subprocess. The refusals are real code paths —
no identity rail, no database, a task mid-turn, an orphaned row — and a refused
launch spawns nothing. The one test that reaches ``SubagentDriver.start`` gets
there by pointing ``sys.executable`` at a file that does not exist, so the
spawn itself raises: a real branch, not a patched-out collaborator, and the
branch whose bookkeeping (row terminal, mailbox empty) is the whole reason
``finish_task`` grew a ``deliver`` flag.

The launch itself, the watcher's waiter arithmetic and the poke are exercised
against a real child process in tests/integration/test_agent2_task_subtool.py.
"""

import sys

import pytest

from crow_cli.client2.subagent import SubagentDriver
from crow_cli.memory import (
    add_message,
    create_agent,
    create_database,
    get_engine,
)
from crow_cli.memory.reads import get_task, owner_tasks, pending_deliveries
from crow_cli.memory.writes import finish_task, launch_task
from crow_cli.tools.register import CellContext, begin_cell, clear, pending
from crow_cli.tools.results import TaskError, TaskListResult, TaskResult
from crow_cli.tools.task import (
    LiveTask,
    _child_answer,
    _dispose,
    _engine,
    _live,
    _register_task,
    _resolve,
    _state,
    task,
    task_cancel,
    task_read,
    task_send,
)

OWNER = "brave-otter-of-judgment"


@pytest.fixture(autouse=True)
def _clean():
    clear()
    yield
    clear()
    _dispose()
    _live().clear()


def _rail(tmp_path, session=OWNER):
    """Point the identity rail at a fresh database and hand back its engine.

    ``begin_cell`` is what execute's prologue does, so this is the real rail
    and not a stand-in for one — including ``parent_tool_call_id``, which is
    how a task row learns which execute call launched it.
    """
    uri = f"sqlite:///{tmp_path}/crow.db"
    create_database(uri)
    begin_cell(session_id=session, db_uri=uri, parent_tool_call_id="call-abc")
    return uri, _engine()


def _cell_of(session):
    return CellContext(session_id=session, parent_tool_call_id="call-abc", cell_seq=1)


def _launch(engine, task_id, *, owner=OWNER, sub=None, **kw):
    launch_task(engine, task_id=task_id, owner_session=owner, sub_session=sub, **kw)


# ---------------------------------------------------------------------------
# The rail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outside_a_cell_there_is_nobody_to_deliver_to():
    """The owner is the mailbox a completion has to reach, and it comes off the
    rail — never off an argument, or a model could deliver into somebody
    else's inbox."""
    with pytest.raises(TaskError, match="no session identity"):
        await task("do the thing")
    with pytest.raises(TaskError, match="no session identity"):
        await task_send("task-1", "do the thing")


@pytest.mark.asyncio
async def test_a_rail_without_a_database_raises():
    begin_cell(session_id=OWNER)
    for call in (
        task("do the thing"),
        task_read(),
        task_read("task-1"),
        task_cancel("task-1"),
        task_send("task-1", "do the thing"),
    ):
        with pytest.raises(TaskError, match="no database"):
            await call


@pytest.mark.asyncio
async def test_the_engine_is_cached_per_uri_and_disposable(tmp_path):
    u1 = f"sqlite:///{tmp_path}/a.db"
    u2 = f"sqlite:///{tmp_path}/b.db"
    create_database(u1)
    create_database(u2)

    begin_cell(session_id=OWNER, db_uri=u1)
    e1 = _engine()
    assert _engine() is e1

    begin_cell(session_id=OWNER, db_uri=u2)
    assert _engine() is not e1

    _dispose()
    assert _state["engine"] is None
    assert _state["uri"] is None


# ---------------------------------------------------------------------------
# Registration: global numbering, state first
# ---------------------------------------------------------------------------


def test_task_numbering_is_global_not_per_owner(tmp_path):
    """task_id is UNIQUE across the database, so a per-owner counter collides
    the moment a second session launches its first task."""
    _, engine = _rail(tmp_path)
    a, b = _cell_of("session-a"), _cell_of("session-b")
    kw = dict(prompt="x", model=None, priority="low", kind="subagent")
    assert _register_task(engine, a, **kw) == "task-1"
    assert _register_task(engine, b, **kw) == "task-2"
    assert _register_task(engine, a, **kw) == "task-3"
    assert get_task(engine, "task-2").owner_session == "session-b"


def test_a_taken_id_is_retried_not_reused(tmp_path):
    """The retry absorbs a gap: one row exists, so the counter says 2, and 2 is
    exactly the id that is taken."""
    _, engine = _rail(tmp_path)
    _launch(engine, "task-2", owner="somebody-else")
    got = _register_task(
        engine, _cell_of(OWNER), prompt="x", model=None, priority="low",
        kind="subagent",
    )
    assert got == "task-3"


def test_the_row_carries_the_execute_call_that_launched_it(tmp_path):
    _, engine = _rail(tmp_path)
    task_id = _register_task(
        engine, _cell_of(OWNER), prompt="go", model="m", priority="high",
        kind="timer",
    )
    row = get_task(engine, task_id)
    assert row.tool_call_id == "call-abc"
    assert row.priority == "high"
    assert row.kind == "timer"
    assert row.model == "m"
    assert row.status == "running"


# ---------------------------------------------------------------------------
# Handles
# ---------------------------------------------------------------------------


def test_resolve_takes_a_task_id_or_a_subagent_session(tmp_path):
    _, engine = _rail(tmp_path)
    _launch(engine, "task-1", sub="child-wire-id")
    assert _resolve(engine, "task-1").task_id == "task-1"
    assert _resolve(engine, "child-wire-id").task_id == "task-1"


def test_resolve_refuses_a_ref_that_matches_neither(tmp_path):
    _, engine = _rail(tmp_path)
    _launch(engine, "task-1", sub="child-wire-id")
    with pytest.raises(TaskError, match="no task matches 'nope'"):
        _resolve(engine, "nope")


# ---------------------------------------------------------------------------
# The answer read
# ---------------------------------------------------------------------------


def _transcript(engine, session="child"):
    """A child that took two trunk turns and forked once on the way."""
    create_agent(
        engine, agent_id=f"{session}-1-1", session_id=session, agent_idx=1,
        fork_idx=1, system_prompt="", cwd="/tmp",
    )
    add_message(
        engine, f"{session}-1-1",
        {"role": "assistant", "content": [{"type": "text", "text": "first turn"}]},
    )
    create_agent(
        engine, agent_id=f"{session}-2-1", session_id=session, agent_idx=2,
        fork_idx=1, system_prompt="", cwd="/tmp",
    )
    add_message(
        engine, f"{session}-2-1",
        {"role": "assistant", "content": [{"type": "text", "text": "the answer"}]},
    )
    create_agent(
        engine, agent_id=f"{session}-2-2", session_id=session, agent_idx=2,
        fork_idx=2, system_prompt="", cwd="/tmp",
    )
    add_message(
        engine, f"{session}-2-2",
        {"role": "assistant", "content": [{"type": "text", "text": "a fork's aside"}]},
    )


def test_the_answer_is_the_trunks_highest_agent(tmp_path):
    """Not the fork's, and not the first turn's: the trunk's last word, which
    is the same read memory("list", session_id=...) resolves."""
    _, engine = _rail(tmp_path)
    _transcript(engine)
    assert _child_answer(engine, "child") == "the answer"


def test_a_child_with_no_transcript_says_so(tmp_path):
    _, engine = _rail(tmp_path)
    assert _child_answer(engine, "ghost") == "(the subagent produced no transcript)"


def test_a_child_that_never_spoke_says_so(tmp_path):
    _, engine = _rail(tmp_path)
    create_agent(
        engine, agent_id="child-1-1", session_id="child", agent_idx=1,
        fork_idx=1, system_prompt="", cwd="/tmp",
    )
    add_message(engine, "child-1-1", {"role": "user", "content": "answer me"})
    assert _child_answer(engine, "child") == "(the subagent produced no final answer)"


# ---------------------------------------------------------------------------
# Launch failure: the row closes, the mailbox stays empty
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_launch_that_cannot_spawn_its_child_closes_the_row_alone(
    tmp_path, monkeypatch
):
    """An interpreter that is not there, so the real spawn raises.

    ``agent_argv`` builds ``[sys.executable, "-m", "crow_cli.agent2.main"]``
    and ``spawn_stdio_transport`` execs it; pointing ``sys.executable`` at a
    missing file makes that a ``FileNotFoundError`` out of the real launch
    path, with nothing patched out between ``task()`` and the OS.

    Two things have to be true. The row goes terminal — a task left "running"
    is a task its owner parks on forever. And NO delivery lands: the caller is
    right here, holding the exception, and a mailbox message would tell it the
    same thing twice, once as an error it caught and once as a wake it did not
    ask for. That is the double report v1 had.
    """
    _, engine = _rail(tmp_path)
    missing = str(tmp_path / "no-such-interpreter")
    monkeypatch.setattr(sys, "executable", missing)

    with pytest.raises(TaskError, match="task-1: launch failed") as exc:
        await task("do the thing")
    assert "FileNotFoundError" in str(exc.value)
    assert missing in str(exc.value)

    rows = owner_tasks(engine, OWNER)
    assert [t.task_id for t in rows] == ["task-1"]
    assert rows[0].status == "failed"
    assert missing in rows[0].result
    assert pending_deliveries(engine, OWNER) == []


@pytest.mark.asyncio
async def test_a_refusal_is_recorded_as_a_failed_subtool_call(tmp_path):
    """The register's ACP channel: a refusal is not a silent nothing, it is a
    row the client can render."""
    _rail(tmp_path)
    with pytest.raises(TaskError):
        await task_read("nope")
    entries = pending()
    assert [e.tool for e in entries] == ["task_read"]
    assert entries[0].status == "failed"
    assert entries[0].result_kind == "error"
    assert entries[0].error.startswith("TaskError:")
    assert entries[0].session_id == OWNER
    assert entries[0].parent_tool_call_id == "call-abc"


@pytest.mark.asyncio
async def test_a_successful_read_is_recorded_with_its_payload(tmp_path):
    _, engine = _rail(tmp_path)
    _launch(engine, "task-1", sub="child")
    await task_read("task-1")
    entry = pending()[0]
    assert entry.status == "completed"
    assert entry.result_kind == "task"
    assert entry.acp_payload["subject"] == "task-1"


# ---------------------------------------------------------------------------
# Cancel without a child
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_closes_a_row_whose_child_is_gone(tmp_path):
    """A running row with no live child is an orphan: the kernel that launched
    it was reset, which killed the process, which closed the child's stdin.
    Nobody will ever finalize it, so cancel does."""
    _, engine = _rail(tmp_path)
    _launch(engine, "task-1", sub="dead-child", prompt="go")

    r = await task_cancel("task-1")
    assert r.status == "cancelled"
    assert get_task(engine, "task-1").status == "cancelled"
    assert pending_deliveries(engine, OWNER) == []
    assert "orphaned" in r.text


@pytest.mark.asyncio
async def test_cancel_on_a_finished_task_hands_back_its_answer(tmp_path):
    """Not a refusal: the caller asked whether this task was still going, and
    the useful answer is that it stopped, and what it said."""
    _, engine = _rail(tmp_path)
    _launch(engine, "task-1", sub="child", prompt="go")
    finish_task(engine, "task-1", result="42", status="completed", content="c")

    r = await task_cancel("task-1")
    assert r.status == "completed"
    assert "42" in r.text
    # The delivery it already landed is untouched.
    assert len(pending_deliveries(engine, OWNER)) == 1


# ---------------------------------------------------------------------------
# Send refusals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_refuses_a_task_that_is_mid_turn(tmp_path):
    """The ordering the redirect workflow depends on: a second prompt queued
    behind a running turn is a redirect nobody sees."""
    _, engine = _rail(tmp_path)
    _launch(engine, "task-1", sub="busy", prompt="go")
    _live()["busy"] = LiveTask(
        task_id="task-1", owner=OWNER, sub="busy", priority="low",
        kind="subagent", bus="", driver=SubagentDriver(), prompt="go",
    )
    with pytest.raises(TaskError, match="mid-turn") as exc:
        await task_send("task-1", "actually, do this instead")
    assert "task_cancel" in str(exc.value)
    # Nothing was sent, and the row was not touched.
    assert get_task(engine, "task-1").status == "running"


@pytest.mark.asyncio
async def test_send_refuses_an_orphaned_running_row(tmp_path):
    _, engine = _rail(tmp_path)
    _launch(engine, "task-1", sub="gone", prompt="go")
    with pytest.raises(TaskError, match="orphaned"):
        await task_send("task-1", "hello?")


@pytest.mark.asyncio
async def test_send_refuses_a_task_that_never_got_a_child(tmp_path):
    """A launch that failed before session/new left a row with no sub session:
    there is nothing to re-attach to, and pretending otherwise would resume a
    session id that does not exist."""
    _, engine = _rail(tmp_path)
    _launch(engine, "task-1", prompt="go")
    finish_task(engine, "task-1", result="boom", status="failed", deliver=False)
    with pytest.raises(TaskError, match="never got a subagent session"):
        await task_send("task-1", "hello?")


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_lists_only_the_callers_own_tasks(tmp_path):
    _, engine = _rail(tmp_path)
    _launch(engine, "task-1", sub="c1", prompt="one")
    _launch(engine, "task-2", owner="somebody-else", sub="c2", prompt="two")
    finish_task(engine, "task-1", result="the answer was 42", content="d")

    r = await task_read()
    assert isinstance(r, TaskListResult)
    assert len(r) == 1
    assert r.tasks[0].task_id == "task-1"
    assert "task-2" not in r.text
    # The table carries handles and states, not answers: a list that repeated
    # every result would cost exactly the context the system protects.
    assert "the answer was 42" not in r.text
    # ... but the objects do, for filtering in Python.
    assert r.tasks[0].result == "the answer was 42"


@pytest.mark.asyncio
async def test_read_with_no_tasks_says_so(tmp_path):
    _rail(tmp_path)
    r = await task_read()
    assert len(r) == 0
    assert r.text == "no tasks — this session has launched none"


@pytest.mark.asyncio
async def test_read_one_task_by_either_handle(tmp_path):
    _, engine = _rail(tmp_path)
    _launch(engine, "task-1", sub="child", prompt="go")
    finish_task(engine, "task-1", result="done", content="d")

    by_id, by_sub = await task_read("task-1"), await task_read("child")
    assert isinstance(by_id, TaskResult)
    assert by_id.status == "completed" and by_id.result == "done"
    assert by_sub.task_id == "task-1"
    assert by_id.session_id == "child"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_an_async_launch_reads_like_a_handle():
    r = TaskResult(task_id="task-4", status="running", session_id="cool-otter",
                   prompt="go")
    assert r.waited is False and r.poked is False
    assert "no result yet" in r.text
    assert "will not grow one" in r.text
    assert 'memory("list", session_id="cool-otter")' in r.text
    assert 'task_read("task-4")' in r.text
    assert r.acp_payload() == {
        "content": "text", "text": r.text, "subject": "task-4",
    }


def test_a_wait_that_ran_out_says_it_waited():
    """The distinction that stops a model waiting again, and again, until its
    turn is gone: this is a timeout on the WAIT, not a failure of the task."""
    r = TaskResult(task_id="task-4", status="running", session_id="cool-otter",
                   prompt="go", waited=True)
    assert "you waited for it and it is still going" in r.text
    assert "not a failure of the task" in r.text
    assert 'task_cancel("task-4")' in r.text
    assert "no result yet" not in r.text


def test_a_running_note_supersedes_the_generic_prose():
    r = TaskResult(task_id="task-4", status="running", session_id="c",
                   waited=True, result="cancel sent but teardown is in progress")
    assert r.text == (
        "task-4: running (subagent c) — cancel sent but teardown is in progress"
    )


def test_a_cancelled_note_is_appended():
    plain = TaskResult(task_id="task-4", status="cancelled", session_id="c")
    assert plain.text == (
        "task-4: cancelled (subagent c) — cancelled, so there is no delivery"
        " to collect."
    )
    noted = TaskResult(task_id="task-4", status="cancelled", session_id="c",
                       result="the row had been orphaned")
    assert noted.text.endswith("the row had been orphaned")


def test_the_answer_is_windowed_in_text_not_in_the_object():
    r = TaskResult(task_id="task-4", status="completed", session_id="c",
                   result="x" * 6000, waited=True)
    assert "6,000 chars" in r.text
    assert "result[5000:]" in r.text
    assert len(r.result) == 6000
    assert r.chars == 6000


def test_a_result_nobody_waited_for_says_so():
    r = TaskResult(task_id="task-4", status="completed", session_id="c",
                   result="done")
    assert "(this call did not wait for it)" in r.text
    waited = TaskResult(task_id="task-4", status="completed", session_id="c",
                        result="done", waited=True)
    assert "did not wait" not in waited.text


def test_the_list_renders_an_aligned_table():
    rows = [
        TaskResult(task_id="task-1", status="completed", session_id="alpha"),
        TaskResult(task_id="task-10", status="running", session_id=""),
    ]
    text = TaskListResult(tasks=rows).text
    lines = text.splitlines()
    assert lines[0] == "task-1   completed  alpha"
    assert lines[1] == "task-10  running    -"
    assert TaskListResult(tasks=rows).acp_payload()["subject"] == "2 tasks"
