"""Goal state in sqlite — the row that decides whether the agent keeps going.

One row per session, keyed by the WIRE session id because that is the only id
that survives compaction. The status column is the whole mechanism: the driver
asks ``active_goal`` at the idle transition and continues if and only if it
gets a row back, so every way of stopping a goal is a way of writing a status.

The two invariants that get their own tests because they are the two that are
easy to lose:

- ``set_goal`` always mints a fresh ``goal_id`` and zeroes the counters, so a
  spent budget cannot survive a restart gesture and an accounting write from a
  turn that was already running cannot charge the new goal.
- the budget flip is a ``CASE`` inside the same UPDATE as the arithmetic, so
  two turns finishing together cannot both read under-budget and sail the goal
  past its ceiling while it is still marked active.
"""

from crow_cli.memory.db import create_database, get_engine
from crow_cli.memory.models import (
    GOAL_ACTIVE,
    GOAL_BLOCKED,
    GOAL_BUDGET_LIMITED,
    GOAL_COMPLETE,
    GOAL_PAUSED,
)
from crow_cli.memory.reads import active_goal, get_goal
from crow_cli.memory.writes import (
    account_goal_usage,
    clear_goal,
    set_goal,
    update_goal_status,
)


def _uri(tmp_path):
    uri = f"sqlite:///{tmp_path / 'goals.db'}"
    create_database(uri)
    return uri


def test_set_goal_registers_an_active_row(tmp_path):
    engine = get_engine(_uri(tmp_path))
    goal_id = set_goal(engine, "brave-otter", "port the widget")

    row = get_goal(engine, "brave-otter")
    assert row is not None
    assert row.goal_id == goal_id
    assert row.objective == "port the widget"
    assert row.status == GOAL_ACTIVE
    assert row.blocked_reason is None
    assert row.token_budget is None
    assert (row.tokens_used, row.time_used_seconds, row.turns_used) == (0, 0, 0)
    assert row.created_at is not None
    # Another session has no goal — the key is the session, not the process.
    assert get_goal(engine, "some-other-session") is None


def test_active_goal_is_the_row_the_driver_asks_for(tmp_path):
    """``active_goal`` is the only read that means "keep going": it returns the
    row for an active goal and None for every other status, so the driver never
    has to know the status vocabulary."""
    engine = get_engine(_uri(tmp_path))
    set_goal(engine, "s", "do the thing")

    assert active_goal(engine, "s").objective == "do the thing"

    for status in (GOAL_PAUSED, GOAL_BLOCKED, GOAL_BUDGET_LIMITED, GOAL_COMPLETE):
        assert update_goal_status(engine, "s", status) is True
        assert active_goal(engine, "s") is None
        # ...but the row is still there to show the user.
        assert get_goal(engine, "s").status == status
        assert update_goal_status(engine, "s", GOAL_ACTIVE) is True


def test_active_goal_none_when_there_is_no_goal(tmp_path):
    engine = get_engine(_uri(tmp_path))
    assert get_goal(engine, "s") is None
    assert active_goal(engine, "s") is None


def test_replacing_the_objective_resets_the_spending(tmp_path):
    """A new objective is new work: fresh id, zeroed counters, active again even
    if the old goal had stopped. The old budget must not judge the new goal."""
    engine = get_engine(_uri(tmp_path))
    first = set_goal(engine, "s", "one", token_budget=100)
    account_goal_usage(engine, "s", goal_id=first, tokens=80, seconds=30, turns=4)
    update_goal_status(engine, "s", GOAL_BLOCKED, blocked_reason="gave up")

    second = set_goal(engine, "s", "two", token_budget=100)

    assert second != first
    row = get_goal(engine, "s")
    assert row.objective == "two"
    assert row.status == GOAL_ACTIVE
    assert row.blocked_reason is None
    assert (row.tokens_used, row.time_used_seconds, row.turns_used) == (0, 0, 0)
    assert active_goal(engine, "s").goal_id == second
    # Still ONE row per session, not a history.
    assert clear_goal(engine, "s") is True
    assert get_goal(engine, "s") is None


def test_resetting_the_same_objective_is_also_a_restart(tmp_path):
    """No special case for the objective that is already there. One rule rather
    than two: re-setting is a restart gesture, and preserving a spent budget
    would make it a no-op that looks like a fresh start."""
    engine = get_engine(_uri(tmp_path))
    first = set_goal(engine, "s", "same", token_budget=100)
    account_goal_usage(engine, "s", goal_id=first, tokens=100)
    assert get_goal(engine, "s").status == GOAL_BUDGET_LIMITED

    second = set_goal(engine, "s", "same", token_budget=100)

    assert second != first
    row = get_goal(engine, "s")
    assert row.status == GOAL_ACTIVE
    assert row.tokens_used == 0


def test_stale_goal_id_loses_the_status_write(tmp_path):
    """The guard the fresh id exists for: a turn that errored five minutes ago
    must not block the goal the user set four minutes ago."""
    engine = get_engine(_uri(tmp_path))
    stale = set_goal(engine, "s", "old objective")
    fresh = set_goal(engine, "s", "new objective")

    assert update_goal_status(engine, "s", GOAL_BLOCKED, expected_goal_id=stale) is False
    row = get_goal(engine, "s")
    assert row.status == GOAL_ACTIVE
    assert row.goal_id == fresh
    assert row.blocked_reason is None

    # The writer that read the current row wins.
    assert update_goal_status(engine, "s", GOAL_BLOCKED, expected_goal_id=fresh) is True
    assert get_goal(engine, "s").status == GOAL_BLOCKED


def test_a_user_obeying_write_passes_no_id(tmp_path):
    """``expected_goal_id=None`` means whatever is there now — that is what a
    pause or a resume is, and it must work without reading the row first."""
    engine = get_engine(_uri(tmp_path))
    set_goal(engine, "s", "objective")

    assert update_goal_status(engine, "s", GOAL_PAUSED) is True
    assert get_goal(engine, "s").status == GOAL_PAUSED
    assert update_goal_status(engine, "s", GOAL_ACTIVE) is True
    assert active_goal(engine, "s") is not None


def test_status_write_with_no_goal_is_false(tmp_path):
    """Nothing to move is not the same answer as moved."""
    engine = get_engine(_uri(tmp_path))
    assert update_goal_status(engine, "ghost", GOAL_PAUSED) is False
    assert update_goal_status(engine, "ghost", GOAL_COMPLETE, expected_goal_id="x") is False
    assert clear_goal(engine, "ghost") is False


def test_blocked_reason_is_kept_only_for_blocked(tmp_path):
    engine = get_engine(_uri(tmp_path))
    set_goal(engine, "s", "objective")

    update_goal_status(engine, "s", GOAL_BLOCKED, blocked_reason="no network")
    assert get_goal(engine, "s").blocked_reason == "no network"

    # Resuming clears it — a stale reason on a live goal reads as a warning.
    update_goal_status(engine, "s", GOAL_ACTIVE)
    assert get_goal(engine, "s").blocked_reason is None

    # And a reason passed with a non-blocked status is dropped, not stored.
    update_goal_status(engine, "s", GOAL_COMPLETE, blocked_reason="ignored")
    row = get_goal(engine, "s")
    assert row.status == GOAL_COMPLETE
    assert row.blocked_reason is None


def test_accounting_accumulates(tmp_path):
    engine = get_engine(_uri(tmp_path))
    goal_id = set_goal(engine, "s", "objective")

    row = account_goal_usage(engine, "s", goal_id=goal_id, tokens=10, seconds=5, turns=1)
    assert (row.tokens_used, row.time_used_seconds, row.turns_used) == (10, 5, 1)
    assert row.status == GOAL_ACTIVE

    row = account_goal_usage(engine, "s", goal_id=goal_id, tokens=7, turns=1)
    assert (row.tokens_used, row.time_used_seconds, row.turns_used) == (17, 5, 2)


def test_accounting_clamps_negatives(tmp_path):
    """A usage report that arrives malformed must not be able to refund a
    budget by subtracting from the counters."""
    engine = get_engine(_uri(tmp_path))
    goal_id = set_goal(engine, "s", "objective", token_budget=100)
    account_goal_usage(engine, "s", goal_id=goal_id, tokens=20, seconds=9, turns=2)

    row = account_goal_usage(engine, "s", goal_id=goal_id, tokens=-50, seconds=-50, turns=-50)
    assert (row.tokens_used, row.time_used_seconds, row.turns_used) == (20, 9, 2)


def test_budget_flip_happens_in_the_same_commit(tmp_path):
    """Crossing the ceiling is not a separate step that can be forgotten or
    lost to a crash between the two writes: the arithmetic and the transition
    are one UPDATE, and the row that comes back is the row the database decided
    on."""
    engine = get_engine(_uri(tmp_path))
    goal_id = set_goal(engine, "s", "objective", token_budget=100)

    row = account_goal_usage(engine, "s", goal_id=goal_id, tokens=99)
    assert row.status == GOAL_ACTIVE
    assert active_goal(engine, "s") is not None

    # 99 + 1 >= 100 — the very write that crosses it flips the status.
    row = account_goal_usage(engine, "s", goal_id=goal_id, tokens=1)
    assert row.tokens_used == 100
    assert row.status == GOAL_BUDGET_LIMITED
    assert active_goal(engine, "s") is None
    # Still showable, still spent.
    assert get_goal(engine, "s").token_budget == 100


def test_budget_keeps_accruing_but_never_resurrects(tmp_path):
    """budget_limited is terminal for continuation purposes: further turns keep
    charging (the numbers stay honest) but the CASE only fires from active, so
    accounting cannot un-limit a goal. Only the user can, via set_goal."""
    engine = get_engine(_uri(tmp_path))
    goal_id = set_goal(engine, "s", "objective", token_budget=10)
    account_goal_usage(engine, "s", goal_id=goal_id, tokens=10)
    assert get_goal(engine, "s").status == GOAL_BUDGET_LIMITED

    row = account_goal_usage(engine, "s", goal_id=goal_id, tokens=500, turns=3)
    assert row.tokens_used == 510
    assert row.turns_used == 3
    assert row.status == GOAL_BUDGET_LIMITED


def test_no_budget_means_no_ceiling(tmp_path):
    engine = get_engine(_uri(tmp_path))
    goal_id = set_goal(engine, "s", "objective")
    row = account_goal_usage(engine, "s", goal_id=goal_id, tokens=10_000_000)
    assert row.status == GOAL_ACTIVE
    assert active_goal(engine, "s") is not None


def test_accounting_a_replaced_goal_charges_nothing(tmp_path):
    """The other half of the fresh-id guard: the tokens were spent on work that
    is no longer the goal, so they land on no row at all, and the caller can
    tell because it gets None back."""
    engine = get_engine(_uri(tmp_path))
    stale = set_goal(engine, "s", "old")
    fresh = set_goal(engine, "s", "new", token_budget=100)

    assert account_goal_usage(engine, "s", goal_id=stale, tokens=99) is None
    row = get_goal(engine, "s")
    assert row.goal_id == fresh
    assert row.tokens_used == 0
    assert row.status == GOAL_ACTIVE

    assert account_goal_usage(engine, "s", goal_id="never-existed", tokens=5) is None
    assert get_goal(engine, "s").tokens_used == 0


def test_the_row_is_visible_to_another_engine(tmp_path):
    """Cross-process by construction: the tool that ends a goal runs in the
    execute kernel, the driver that reads it runs in the agent process. Two
    engines on one file, no shared memory."""
    uri = _uri(tmp_path)
    tools = get_engine(uri)
    driver = get_engine(uri)

    goal_id = set_goal(tools, "s", "objective", token_budget=100)
    assert active_goal(driver, "s").goal_id == goal_id

    account_goal_usage(tools, "s", goal_id=goal_id, tokens=100)
    assert active_goal(driver, "s") is None
    assert get_goal(driver, "s").status == GOAL_BUDGET_LIMITED

    update_goal_status(tools, "s", GOAL_COMPLETE, expected_goal_id=goal_id)
    assert get_goal(driver, "s").status == GOAL_COMPLETE

    clear_goal(tools, "s")
    assert get_goal(driver, "s") is None
