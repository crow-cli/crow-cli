"""goal_done / goal_blocked: the model's two exits from a continuation loop.

Everything here is the real rail and the real database. ``begin_cell`` is what
execute's prologue runs, so the session id these calls act on is the one the
harness injected and not one a test handed them; the writes are read back
through a SECOND engine on the same file, so what is asserted is what landed in
sqlite rather than what an ORM identity map remembered.

The driver half — a goal the model ended is not continued, and an ended goal is
not overwritten by the turn that carried the ending — is
tests/integration/test_goal_driver.py, against a real agent and transport.
"""

import pytest

import crow_cli.memory as cm
from crow_cli.agent2.tools import KIND_BY_RESULT, tool_kind
from crow_cli.memory import (
    GOAL_ACTIVE,
    GOAL_BLOCKED,
    GOAL_COMPLETE,
    GOAL_PAUSED,
    create_database,
    set_goal,
    update_goal_status,
)
from crow_cli.memory.reads import get_goal
from crow_cli.tools.goal import _dispose, _engine, _state, goal_blocked, goal_done
from crow_cli.tools.register import begin_cell, clear, pending
from crow_cli.tools.results import GoalError, GoalResult

SESSION = "worthy-conscious-rat-of-opportunity"
OBJECTIVE = "port the option list widget to ratatui"


@pytest.fixture(autouse=True)
def _clean():
    clear()
    yield
    clear()
    _dispose()


def _rail(tmp_path, session=SESSION, *, objective=OBJECTIVE, **goal_kw):
    """Point the identity rail at a fresh database with one active goal in it.

    Returns a second engine on the same file, so a test can read the row back
    without going through the handle the call under test just wrote with.
    """
    uri = f"sqlite:///{tmp_path}/crow.db"
    create_database(uri)
    engine = cm.get_engine(uri)
    set_goal(engine, session, objective, **goal_kw)
    begin_cell(session_id=session, db_uri=uri, parent_tool_call_id="call-abc")
    return engine


# ---------------------------------------------------------------------------
# The rail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outside_a_cell_there_is_no_session_to_end_the_goal_of():
    """The session id is the whole authority these calls have, and it comes off
    the rail — a model that could name it could end somebody else's goal."""
    with pytest.raises(GoalError, match="no session identity"):
        await goal_done()
    with pytest.raises(GoalError, match="no session identity"):
        await goal_blocked("no rail")


@pytest.mark.asyncio
async def test_a_rail_without_a_database_raises(tmp_path):
    begin_cell(session_id=SESSION)
    for call in (goal_done(), goal_blocked("x")):
        with pytest.raises(GoalError, match="no database"):
            await call


@pytest.mark.asyncio
async def test_a_session_with_no_goal_has_no_exit(tmp_path):
    """Not a no-op and not a crash: the model reached for an exit that was
    never armed, and the message says who arms one."""
    uri = f"sqlite:///{tmp_path}/crow.db"
    create_database(uri)
    begin_cell(session_id=SESSION, db_uri=uri)
    with pytest.raises(GoalError, match="no goal"):
        await goal_done()
    with pytest.raises(GoalError, match="no goal"):
        await goal_blocked("nothing to block")


def test_the_engine_is_cached_per_uri_and_disposable(tmp_path):
    """reload() re-executes the module in its existing dict, so the cache lives
    in ``_state`` and survives it — a module-level handle would leak a pool on
    every reload and drop the uri it was built for."""
    u1 = f"sqlite:///{tmp_path}/a.db"
    u2 = f"sqlite:///{tmp_path}/b.db"
    create_database(u1)
    create_database(u2)

    begin_cell(session_id=SESSION, db_uri=u1)
    e1 = _engine()
    assert _engine() is e1

    begin_cell(session_id=SESSION, db_uri=u2)
    assert _engine() is not e1

    _dispose()
    assert _state["engine"] is None
    assert _state["uri"] is None


# ---------------------------------------------------------------------------
# The two exits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_goal_done_completes_the_row(tmp_path):
    engine = _rail(tmp_path)
    r = await goal_done()

    assert r.changed is True
    assert r.status == GOAL_COMPLETE
    assert r.objective == OBJECTIVE
    assert get_goal(engine, SESSION).status == GOAL_COMPLETE
    assert "will not be continued" in r.text


@pytest.mark.asyncio
async def test_goal_blocked_stores_the_reason_on_the_row(tmp_path):
    """The reason is the only thing a blocked goal has that a complete one does
    not, because somebody has to act on it. Read back through a second engine:
    it has to be in the file, not in this process's session cache."""
    engine = _rail(tmp_path)
    r = await goal_blocked("  the deploy key is not in this environment  ")

    assert r.changed is True
    assert r.status == GOAL_BLOCKED
    row = get_goal(engine, SESSION)
    assert row.status == GOAL_BLOCKED
    # Stripped, because it is stored to be read.
    assert row.blocked_reason == "the deploy key is not in this environment"
    assert r.reason == row.blocked_reason
    assert f"why: {row.blocked_reason}" in r.text


@pytest.mark.asyncio
async def test_goal_blocked_without_a_reason_refuses_and_changes_nothing(tmp_path):
    engine = _rail(tmp_path)
    for bad in ("", "   ", "\n\t "):
        with pytest.raises(GoalError, match="needs the reason"):
            await goal_blocked(bad)
    assert get_goal(engine, SESSION).status == GOAL_ACTIVE
    assert get_goal(engine, SESSION).blocked_reason is None


@pytest.mark.asyncio
async def test_completing_clears_a_previous_blocked_reason(tmp_path):
    """``update_goal_status`` only keeps a reason for ``blocked``, so a goal
    that was blocked and then finished does not carry the old excuse."""
    engine = _rail(tmp_path)
    await goal_blocked("waiting on access")
    assert get_goal(engine, SESSION).blocked_reason == "waiting on access"

    update_goal_status(engine, SESSION, GOAL_ACTIVE)
    r = await goal_done()
    assert r.status == GOAL_COMPLETE
    assert get_goal(engine, SESSION).blocked_reason is None
    assert r.reason == ""


@pytest.mark.asyncio
async def test_the_spend_comes_back_on_the_result(tmp_path):
    """codex asks the model to report final token usage when a budgeted goal
    completes; it can only report what the result carries."""
    engine = _rail(tmp_path, token_budget=200_000)
    cm.account_goal_usage(
        engine, SESSION, goal_id=get_goal(engine, SESSION).goal_id,
        tokens=18_204, seconds=372, turns=4,
    )
    r = await goal_done()

    assert (r.turns_used, r.tokens_used, r.token_budget) == (4, 18_204, 200_000)
    assert r.time_used_seconds == 372
    assert "4 turns, 18,204 of 200,000 tokens, 6m12s." in r.text


# ---------------------------------------------------------------------------
# Idempotence, and not overruling whoever stopped it first
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_goal_done_twice_says_so_rather_than_raising(tmp_path):
    engine = _rail(tmp_path)
    first = await goal_done()
    second = await goal_done()

    assert first.changed is True
    assert second.changed is False
    assert second.status == GOAL_COMPLETE
    assert "changed nothing" in second.text
    assert get_goal(engine, SESSION).status == GOAL_COMPLETE


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [GOAL_PAUSED, GOAL_BLOCKED, "budget_limited"])
async def test_a_goal_somebody_else_stopped_is_not_moved(tmp_path, status):
    """The user paused it, the budget ran out, a turn errored. The model does
    not get to overrule that — the same rule that makes agent2.goal.eligible
    return Verdict(None, ...) instead of a status."""
    engine = _rail(tmp_path)
    update_goal_status(engine, SESSION, status, blocked_reason="the turn errored")

    for call in (goal_done(), goal_blocked("changed my mind")):
        r = await call
        assert r.changed is False
        assert r.status == status
    row = get_goal(engine, SESSION)
    assert row.status == status
    assert row.blocked_reason == ("the turn errored" if status == GOAL_BLOCKED else None)


def test_a_result_for_a_still_active_goal_does_not_promise_a_stop():
    """The write carries the goal_id it read, so a goal the user replaced
    mid-call loses the race and leaves an ACTIVE row behind. Reporting "will
    not be continued" there is the one thing this must not say."""
    r = GoalResult(status=GOAL_ACTIVE, objective=OBJECTIVE, changed=False)
    assert "changed nothing" in r.text
    assert "keeps being continued" in r.text
    assert "will not be continued" not in r.text


# ---------------------------------------------------------------------------
# The other two channels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_call_is_recorded_for_the_drain(tmp_path):
    _rail(tmp_path)
    await goal_blocked("the deploy key is missing")

    (entry,) = pending()
    assert (entry.tool, entry.mode, entry.status) == ("goal_blocked", None, "completed")
    assert entry.result_kind == "goal"
    assert entry.session_id == SESSION
    assert entry.parent_tool_call_id == "call-abc"
    assert entry.args == {"reason": "the deploy key is missing"}
    assert entry.acp_payload["subject"] == OBJECTIVE
    assert "goal blocked" in entry.acp_payload["text"]


@pytest.mark.asyncio
async def test_a_refusal_is_recorded_as_a_failure(tmp_path):
    _rail(tmp_path)
    with pytest.raises(GoalError):
        await goal_blocked("")

    (entry,) = pending()
    assert (entry.tool, entry.status, entry.result_kind) == (
        "goal_blocked", "failed", "error",
    )
    assert "needs the reason" in entry.error


def test_the_wire_kind_is_stated_not_fallen_into():
    """``goal_done`` matches none of tool_kind's substring rules, so without
    the KIND_BY_RESULT entry it would be "other" by accident — and the next
    rule added to that function could quietly reclassify it."""
    assert KIND_BY_RESULT["goal"] == "other"
    assert tool_kind("goal_done") == "other"
    assert tool_kind("goal_blocked") == "other"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_both_names_resolve_through_the_v2_facade():
    """Read the table rather than restating it: the claim is that every name
    this flavour declares resolves to a callable in the module the table
    names. The real-kernel half — PRELUDE_V2 binding them into a live
    namespace — is tests/mcp/test_mcp2_server.py, which reads the same table.
    """
    import importlib

    import crow_cli.tools as T

    assert {"goal_done", "goal_blocked"} <= set(T._LAZY_V2)
    for name, (module_name, attr) in T._LAZY_V2.items():
        # Resolved the way reload() resolves it, NOT getattr(T, name). A test
        # that imported crow_cli.tools.task as a submodule left the MODULE on
        # the package attribute, and that shadows __getattr__ — the wart
        # reload()'s purge exists to undo, and not this test's to trip over.
        value = getattr(importlib.import_module(module_name), attr)
        assert callable(value), name
        assert value.__name__ == attr, name

    # The two new names through the facade itself. Nothing imports
    # crow_cli.tools.goal for its module and then wants the function, so
    # there is no shadow to trip over and this is the path a kernel takes.
    for name in ("goal_done", "goal_blocked"):
        assert callable(getattr(T, name)), name
        assert getattr(T, name).__module__ == "crow_cli.tools.goal", name


def test_the_goal_tools_are_not_ambient_in_a_v1_kernel():
    """v1 runs no continuation loop, so an exit from one is a call that
    succeeds, changes a row, and means nothing."""
    import crow_cli.tools as T

    assert "goal_done" not in T._LAZY
    assert "goal_blocked" not in T._LAZY
    assert set(T._names()) == set(T._LAZY)
