"""Goal continuation policy — the rules that decide whether the loop goes round
again, and the text it sends when it does.

Real rows over a temp sqlite db, not constructed objects: the point of the
module is that it reads the same row the driver, the slash command and the
subtools all read, and a hand-built ``Goal(...)`` in a test would let a column
default drift without anything noticing.
"""

from crow_cli.agent2.goal import (
    CONTINUATION_PROMPT,
    Verdict,
    continuation_text,
    eligible,
    progress,
)
from crow_cli.memory.db import create_database, get_engine
from crow_cli.memory.models import (
    GOAL_ACTIVE,
    GOAL_BLOCKED,
    GOAL_BUDGET_LIMITED,
    GOAL_COMPLETE,
    GOAL_PAUSED,
)
from crow_cli.memory.reads import get_goal
from crow_cli.memory.writes import account_goal_usage, set_goal, update_goal_status


def _goal(tmp_path, objective="port the widget", **kw):
    uri = f"sqlite:///{tmp_path / 'goal.db'}"
    create_database(uri)
    engine = get_engine(uri)
    goal_id = set_goal(engine, "s", objective, **kw)
    return engine, get_goal(engine, "s"), goal_id


def _go(engine, goal_id, **kw):
    account_goal_usage(engine, "s", goal_id=goal_id, **kw)
    return get_goal(engine, "s")


def test_an_active_goal_that_did_work_may_continue(tmp_path):
    _, goal, _ = _goal(tmp_path)
    assert goal.status == GOAL_ACTIVE
    assert eligible(goal, tools_used=3, was_continuation=True, max_goal_turns=25) is None
    assert eligible(goal, tools_used=1, was_continuation=False, max_goal_turns=25) is None


def test_no_goal_is_a_verdict_not_a_crash(tmp_path):
    """The function is total: the driver reads a row that may not exist, and a
    None that has to be guarded at every call site is a guard that gets
    forgotten at one of them."""
    v = eligible(None, tools_used=9, was_continuation=True, max_goal_turns=25)
    assert v == Verdict(None, "no active goal")
    # Nothing to persist — there is no row.
    assert v.status is None


def test_a_goal_someone_else_stopped_is_left_alone(tmp_path):
    """status is None for every non-active row: a paused goal was stopped by
    the USER and a complete goal by the MODEL, and this module writing a status
    over either decision would be the policy layer overruling the person."""
    engine, goal, goal_id = _goal(tmp_path)
    for status in (GOAL_PAUSED, GOAL_BLOCKED, GOAL_BUDGET_LIMITED, GOAL_COMPLETE):
        update_goal_status(engine, "s", status)
        row = get_goal(engine, "s")
        v = eligible(row, tools_used=5, was_continuation=True, max_goal_turns=25)
        assert v.status is None
        assert status in v.reason
        update_goal_status(engine, "s", GOAL_ACTIVE)


def test_a_text_only_continuation_ends_the_goal(tmp_path):
    """THE loop guard. Without it the cycle is "model talks -> continue ->
    model talks", which ends only when the budget does."""
    _, goal, _ = _goal(tmp_path)
    v = eligible(goal, tools_used=0, was_continuation=True, max_goal_turns=25)
    assert v.status == GOAL_BLOCKED
    assert "no tools" in v.reason


def test_a_text_only_USER_turn_does_not(tmp_path):
    """The other half, and the reason ``was_continuation`` exists: a person who
    interjects "what's the status?" mid-goal gets a text-only answer, and
    blocking the goal because they asked a question punishes them for using
    it."""
    _, goal, _ = _goal(tmp_path)
    assert eligible(goal, tools_used=0, was_continuation=False, max_goal_turns=25) is None


def test_the_turn_ceiling_is_budget_limited_not_blocked(tmp_path):
    """A configured limit running out is the arithmetic's decision, and the
    status vocabulary keeps that separate from "the model claims it is stuck" —
    collapsing them loses the one distinction the user can act on."""
    engine, goal, goal_id = _goal(tmp_path)
    goal = _go(engine, goal_id, turns=25)

    v = eligible(goal, tools_used=7, was_continuation=True, max_goal_turns=25)
    assert v.status == GOAL_BUDGET_LIMITED
    assert "25 of 25" in v.reason
    # One under the ceiling still goes.
    goal = _go(engine, goal_id, turns=0)
    assert eligible(get_goal(engine, "s"), tools_used=7, was_continuation=True, max_goal_turns=26) is None


def test_no_configured_ceiling_means_no_ceiling(tmp_path):
    engine, goal, goal_id = _goal(tmp_path)
    goal = _go(engine, goal_id, turns=10_000)
    assert eligible(goal, tools_used=1, was_continuation=True, max_goal_turns=None) is None


def test_the_ceiling_is_checked_before_progress(tmp_path):
    """A goal that ran out of turns AND made no progress reports the ceiling:
    it is the more useful of the two, because "stalled" invites a nudge and a
    nudge cannot buy more turns."""
    engine, goal, goal_id = _goal(tmp_path)
    goal = _go(engine, goal_id, turns=25)
    v = eligible(goal, tools_used=0, was_continuation=True, max_goal_turns=25)
    assert v.status == GOAL_BUDGET_LIMITED


def test_continuation_text_names_the_objective_and_the_exits(tmp_path):
    _, goal, _ = _goal(tmp_path, objective="make the tests pass")
    text = continuation_text(goal, max_goal_turns=25)

    assert "make the tests pass" in text
    assert "the user did not send this" in text
    assert "goal_done" in text
    assert "goal_blocked" in text
    assert "Turn 1 of at most 25" in text


def test_continuation_text_shows_the_budget_when_there_is_one(tmp_path):
    """A model that cannot see the ceiling cannot budget against it."""
    engine, goal, goal_id = _goal(tmp_path, token_budget=5000)
    goal = _go(engine, goal_id, tokens=1200, turns=2)
    text = continuation_text(goal, max_goal_turns=25)

    assert "Tokens 1200 of 5000" in text
    assert "Turn 3 of at most 25" in text  # the NEXT turn, not the count so far


def test_continuation_text_without_a_budget_or_a_ceiling(tmp_path):
    _, goal, _ = _goal(tmp_path)
    text = continuation_text(goal)
    assert "No token ceiling" in text
    assert "Turn 1 of this goal" in text


def test_a_stopped_goal_reports_the_turns_it_spent_not_one_more(tmp_path):
    """``progress`` is one function with two callers in different states of the
    world. A continuation is injected at the START of the turn it counts, so the
    model is told which turn it is about to spend; a goal that has stopped has
    no turn in flight and the person is told what it cost.

    Found by the manual eyeball — a complete row with ``turns_used == 1``
    rendered "Turn 2 of at most 4", which reads as a turn nobody is running.
    The row's own status is what distinguishes the two, so a continuation is
    unaffected: only a goal that can no longer be continued renders differently,
    and by definition nothing injects into one of those.
    """
    engine, goal, goal_id = _goal(tmp_path, token_budget=400_000)
    goal = _go(engine, goal_id, turns=1, tokens=75_116)

    assert goal.status == GOAL_ACTIVE
    assert "Turn 2 of at most 4" in progress(goal, 4)  # the NEXT turn

    update_goal_status(engine, "s", GOAL_COMPLETE)
    done = get_goal(engine, "s")
    line = progress(done, 4)
    assert "Turn 1 of at most 4" in line  # what it SPENT
    assert "Tokens 75116 of 400000" in line

    update_goal_status(engine, "s", GOAL_PAUSED)
    assert "Turn 1 of at most 4" in progress(get_goal(engine, "s"), 4)


def test_the_prompt_stays_short(tmp_path):
    """Encodes the design decision so it cannot rot silently: codex's
    continuation.md is 56 lines of completion-audit ritual, and this fires on
    EVERY continuation turn, so every line is a tax on every turn. If this
    assertion fails, someone added a cathedral — either justify it here or cut
    it back."""
    assert len(CONTINUATION_PROMPT.strip().splitlines()) <= 16
    assert len(CONTINUATION_PROMPT) < 900
