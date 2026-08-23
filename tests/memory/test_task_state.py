"""Task state in sqlite — durable registration for async completions.

The hang diagnosis: no state around finished tasks, no queue. These are
the two tables that fix it:

- ``tasks`` — one row per launched task (subagent). Status lives HERE,
  not in a process.
- ``task_deliveries`` — the durable mailbox. A completion lands here THE
  MOMENT it arrives (STATE FIRST, one commit with the status flip); the
  agent process drains it. Survives process death.

Cross-process by construction: the writer is normally the MCP server
process that owns the child; the reader is the agent process. Simulated
with two engines on one file.
"""

from crow_cli.memory.db import create_database, get_engine
from crow_cli.memory.reads import (
    get_task,
    pending_deliveries,
    running_tasks,
)
from crow_cli.memory.writes import finish_task, launch_task, mark_delivered


def _uri(tmp_path):
    uri = f"sqlite:///{tmp_path / 'tasks.db'}"
    create_database(uri)
    return uri


def test_launch_registers_a_running_task(tmp_path):
    engine = get_engine(_uri(tmp_path))
    launch_task(
        engine,
        task_id="task-1",
        owner_session="brave-otter",
        tool_call_id="call-abc",
        sub_session="shy-fox",
        prompt="call date",
        priority="high",
    )

    task = get_task(engine, "task-1")
    assert task is not None
    assert task.kind == "subagent"
    assert task.status == "running"
    assert task.owner_session == "brave-otter"
    assert task.sub_session == "shy-fox"
    assert task.priority == "high"
    assert task.finished_at is None
    assert [t.task_id for t in running_tasks(engine, "brave-otter")] == ["task-1"]
    assert running_tasks(engine, "some-other-session") == []


def test_finish_flips_state_and_lands_a_delivery_atomically(tmp_path):
    """STATE FIRST: after finish, the task row is terminal AND the
    delivery sits in the mailbox — one commit, visible to a DIFFERENT
    engine (the agent process)."""
    uri = _uri(tmp_path)
    writer = get_engine(uri)  # MCP server process (owns the child)
    reader = get_engine(uri)  # agent process

    launch_task(writer, task_id="task-1", owner_session="brave-otter",
                sub_session="shy-fox", prompt="call date")
    landed = finish_task(
        writer,
        "task-1",
        result="Sat Aug 23 01:00:00 UTC 2026",
        status="completed",
        content="[task-1: subagent shy-fox finished]\nSat Aug 23 01:00:00 UTC 2026",
    )
    assert landed is True

    task = get_task(reader, "task-1")
    assert task.status == "completed"
    assert task.result.startswith("Sat Aug")
    assert task.finished_at is not None
    assert running_tasks(reader, "brave-otter") == []

    deliveries = pending_deliveries(reader, "brave-otter")
    assert len(deliveries) == 1
    d = deliveries[0]
    assert d.task_id == "task-1"
    assert d.status == "pending"
    assert "subagent shy-fox finished" in d.content


def test_finish_is_idempotent_on_a_terminal_task(tmp_path):
    """A crash-retry or a cancel racing a completion must not double-deliver."""
    engine = get_engine(_uri(tmp_path))
    launch_task(engine, task_id="task-1", owner_session="s")

    assert finish_task(engine, "task-1", result="done", content="first") is True
    assert finish_task(engine, "task-1", result="again", content="second") is False

    assert pending_deliveries(engine, "s")[-1].content == "first"
    assert len(pending_deliveries(engine, "s")) == 1
    assert get_task(engine, "task-1").result == "done"


def test_finish_unknown_task_is_a_noop(tmp_path):
    engine = get_engine(_uri(tmp_path))
    assert finish_task(engine, "ghost", result="x", content="x") is False


def test_cancel_flips_state_without_a_delivery(tmp_path):
    """The caller CANCELLED — a mailbox message telling it so is noise.
    cancel_task flips the row to terminal and lands NOTHING."""
    from crow_cli.memory.writes import cancel_task

    engine = get_engine(_uri(tmp_path))
    launch_task(engine, task_id="task-1", owner_session="s")

    assert cancel_task(engine, "task-1") is True
    task = get_task(engine, "task-1")
    assert task.status == "cancelled"
    assert task.finished_at is not None
    assert pending_deliveries(engine, "s") == []

    # idempotent: already terminal
    assert cancel_task(engine, "task-1") is False
    assert cancel_task(engine, "ghost") is False


def test_mark_delivered_drains_the_mailbox(tmp_path):
    engine = get_engine(_uri(tmp_path))
    launch_task(engine, task_id="task-1", owner_session="s")
    launch_task(engine, task_id="task-2", owner_session="s")
    finish_task(engine, "task-1", result="a", content="one")
    finish_task(engine, "task-2", result="b", content="two")

    pending = pending_deliveries(engine, "s")
    assert [d.content for d in pending] == ["one", "two"]  # arrival order

    mark_delivered(engine, [pending[0].id])
    remaining = pending_deliveries(engine, "s")
    assert [d.content for d in remaining] == ["two"]
    assert remaining[0].delivered_at is None  # still pending

    mark_delivered(engine, [remaining[0].id])
    assert pending_deliveries(engine, "s") == []


def test_claim_deliveries_drains_in_arrival_order(tmp_path):
    """claim = read + mark in ONE atomic statement: the caller gets the
    rows and the mailbox is drained in the same move."""
    from crow_cli.memory.writes import claim_deliveries

    engine = get_engine(_uri(tmp_path))
    launch_task(engine, task_id="task-1", owner_session="s")
    launch_task(engine, task_id="task-2", owner_session="s")
    finish_task(engine, "task-1", result="a", content="one")
    finish_task(engine, "task-2", result="b", content="two")

    claimed = claim_deliveries(engine, "s")
    assert [d["content"] for d in claimed] == ["one", "two"]
    assert [d["task_id"] for d in claimed] == ["task-1", "task-2"]
    assert pending_deliveries(engine, "s") == []
    # A second claim finds nothing — the rows are already delivered.
    assert claim_deliveries(engine, "s") == []


def test_claim_deliveries_priority_filter(tmp_path):
    """The mid-turn breakpoint claims HIGHS ONLY; lows stay pending for
    the end-of-turn consult."""
    from crow_cli.memory.writes import claim_deliveries

    engine = get_engine(_uri(tmp_path))
    launch_task(engine, task_id="task-low", owner_session="s", priority="low")
    launch_task(engine, task_id="task-high", owner_session="s", priority="high")
    finish_task(engine, "task-low", result="a", content="low done")
    finish_task(engine, "task-high", result="b", content="high done")

    highs = claim_deliveries(engine, "s", priority="high")
    assert [d["content"] for d in highs] == ["high done"]
    # The low is still pending — held to end of turn.
    assert [d.content for d in pending_deliveries(engine, "s")] == ["low done"]
    # End-of-turn claim takes the rest.
    rest = claim_deliveries(engine, "s")
    assert [d["content"] for d in rest] == ["low done"]
    assert pending_deliveries(engine, "s") == []


def test_claim_deliveries_no_double_claim_across_engines(tmp_path):
    """Two claimers (the in-loop consult vs the quiescent watcher, or two
    processes) race for the same mailbox: every delivery is injected by
    EXACTLY ONE of them."""
    from crow_cli.memory.writes import claim_deliveries

    uri = _uri(tmp_path)
    consult = get_engine(uri)
    watcher = get_engine(uri)
    launch_task(consult, task_id="task-1", owner_session="s")
    finish_task(consult, "task-1", result="a", content="only once")

    first = claim_deliveries(consult, "s")
    second = claim_deliveries(watcher, "s")
    assert [d["content"] for d in first] == ["only once"]
    assert second == []


def test_priority_rides_both_rows(tmp_path):
    """Priority decides delivery (high = cancel->prompt, low = hold to
    end of prompt) — the drain must be able to sort on it."""
    engine = get_engine(_uri(tmp_path))
    launch_task(engine, task_id="task-low", owner_session="s", priority="low")
    launch_task(engine, task_id="task-high", owner_session="s", priority="high")
    finish_task(engine, "task-low", result="a", content="low done")
    finish_task(engine, "task-high", result="b", content="high done")

    pending = pending_deliveries(engine, "s")
    assert {d.task_id: d.priority for d in pending} == {
        "task-low": "low",
        "task-high": "high",
    }


def test_mailboxes_are_per_session(tmp_path):
    engine = get_engine(_uri(tmp_path))
    launch_task(engine, task_id="task-1", owner_session="session-a")
    launch_task(engine, task_id="task-2", owner_session="session-b")
    finish_task(engine, "task-1", result="a", content="for a")
    finish_task(engine, "task-2", result="b", content="for b")

    assert [d.content for d in pending_deliveries(engine, "session-a")] == ["for a"]
    assert [d.content for d in pending_deliveries(engine, "session-b")] == ["for b"]


def test_set_sub_session_and_reopen_cycle(tmp_path):
    """launch registers the row BEFORE the child exists; the sub session
    id lands once session/new does; reopen flips terminal -> running for
    re-prompts, and refuses to double-open a running task."""
    from crow_cli.memory.reads import count_tasks, task_by_sub_session
    from crow_cli.memory.writes import reopen_task, set_task_sub_session

    engine = get_engine(_uri(tmp_path))
    launch_task(engine, task_id="task-1", owner_session="owner")
    assert get_task(engine, "task-1").sub_session is None

    set_task_sub_session(engine, "task-1", "child-wire-id")
    assert get_task(engine, "task-1").sub_session == "child-wire-id"
    assert task_by_sub_session(engine, "child-wire-id").task_id == "task-1"
    assert task_by_sub_session(engine, "no-such-session") is None
    assert count_tasks(engine, "owner") == 1

    # still running -> reopen refuses
    assert reopen_task(engine, "task-1") is False
    assert finish_task(engine, "task-1", result="done", content="d")
    assert reopen_task(engine, "task-1") is True
    task = get_task(engine, "task-1")
    assert task.status == "running" and task.finished_at is None
    # idempotent finish guard: already-terminal flip returned True once;
    # a reopen does NOT re-deliver the old completion.
    assert pending_deliveries(engine, "owner") != []
