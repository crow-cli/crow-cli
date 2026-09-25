"""goal_done / goal_blocked — the two exits a goal offers the model.

A goal is a latch. While the row is ``active``, the driver turns "the turn
ended" from a full stop into a loop-back edge and sends itself another turn
with nobody asking (:func:`crow_cli.agent2.driver.SessionDriver` at its idle
transition). Nothing else about the mechanism is model-visible — no new event
type, no client round trip, no second injection path — so the only way the
model can stop the loop is to write the row, and these two calls are the
writes it is allowed. The other three statuses belong to the user
(``paused``) and to the arithmetic (``budget_limited``, and ``blocked`` when a
turn errors or a continuation makes no progress).

Two names, not one ``goal(status=...)``, for the reason
:mod:`crow_cli.tools.task_tool` gives: a capability behind a mode-string dispatcher
is a capability that does not get reached. The asymmetry here is the argument
list — ``goal_blocked`` cannot be called without saying why, and a dispatcher
with an argument that is required on one branch and forbidden on the other is
where a requirement like that goes to die.

Neither raises on a goal that is already stopped, and both are idempotent.
They are called at the end of a turn the model spent real reasoning on, and
the right answer to "I already said that" is "yes, and nothing changed" — not
an exception that reads as though the work failed.

The session id comes off the identity rail execute's prologue injected, never
off an argument: a model that could name the session whose goal it ends could
end somebody else's.
"""

from __future__ import annotations

import contextlib

import crow_cli.memory as cm
from crow_cli.memory.models import GOAL_ACTIVE, GOAL_BLOCKED, GOAL_COMPLETE
from crow_cli.memory.reads import get_goal
from crow_cli.memory.writes import update_goal_status

from .register import CellContext, current_cell, db_uri, subtool
from .results import GoalError, GoalResult

# Same reason task.py, rlm.py and memory.py keep theirs in one:
# importlib.reload re-executes this source in the EXISTING module dict, so a
# module-level ``_engine = None`` would drop the handle on every reload() and
# leak its connection pool.
_state: dict = globals().setdefault("_state", {})


def _dispose() -> None:
    """Drop the cached engine (test hygiene, and a db_uri that changed)."""
    engine = _state.get("engine")
    if engine is not None:
        with contextlib.suppress(Exception):
            engine.dispose()
    _state["engine"] = None
    _state["uri"] = None


def _engine():
    """The WRITE engine for the injected crow.db, cached per uri.

    Ending a goal is a write, so this is not the read-only handle rlm keeps.
    Same rail, same refusal: the kernel reads no config, so a caller outside
    one has to point the rail at a database itself.
    """
    uri = db_uri()
    if uri is None:
        raise GoalError(
            "no database — ending a goal writes to the crow.db that execute's"
            " prologue injects on the identity rail; outside a kernel, point"
            " the rail at one with"
            " crow_cli.tools.register.begin_cell(db_uri=...)"
        )
    if _state.get("uri") != uri:
        _dispose()
        _state["engine"] = cm.get_engine(uri)
        _state["uri"] = uri
    return _state["engine"]


def _session() -> str:
    """The session whose goal this ends, or a refusal.

    Off the rail the prologue injected and never off an argument, so a cell
    can only ever end the goal of the session that is running it.
    """
    cell: CellContext | None = current_cell()
    if cell is None or not cell.session_id:
        raise GoalError(
            "no session identity — a goal belongs to one session and this has"
            " to know which, which only exists inside an execute cell (the"
            " prologue injects it)"
        )
    return cell.session_id


def _result(row, *, changed: bool) -> GoalResult:
    return GoalResult(
        status=row.status,
        objective=row.objective,
        reason=row.blocked_reason or "",
        changed=changed,
        turns_used=row.turns_used or 0,
        tokens_used=row.tokens_used or 0,
        token_budget=row.token_budget,
        time_used_seconds=row.time_used_seconds or 0,
    )


def _end(status: str, reason: str = "") -> GoalResult:
    """Write the exit, then read the row back and report what it says.

    Read back rather than echoed, because the row is the mechanism and three
    processes write it: the status reported has to be the one the driver will
    actually find at the idle transition, not the one this call asked for.
    """
    session = _session()
    engine = _engine()
    row = get_goal(engine, session)
    if row is None:
        raise GoalError(
            "no goal — this session has none set, so there is nothing to end."
            " A goal is the user's to set, and until one exists this session"
            " is not being continued automatically and neither exit applies."
        )
    if row.status != GOAL_ACTIVE:
        # Somebody already stopped it: the user paused it, the budget ran out,
        # a turn errored, or an earlier call from this same model ended it.
        # Not this call's decision to overwrite — the same rule that makes
        # agent2.goal.eligible return Verdict(None, ...) rather than a status.
        return _result(row, changed=False)
    # The id it read, so a goal the user replaced mid-call is left running
    # rather than ended by a call that was about the previous one.
    changed = update_goal_status(
        engine,
        session,
        status,
        expected_goal_id=row.goal_id,
        blocked_reason=reason or None,
    )
    return _result(get_goal(engine, session) or row, changed=changed)


@subtool(tool="goal_done")
async def goal_done() -> GoalResult:
    """End the goal: the objective is met and no required work remains.

    This is how an automatic continuation stops. Call it when what the user
    asked for is actually there — checked by looking, not by remembering the
    conversation — and NOT because the turn is over, the budget is running
    low, or you would like to stop. A goal marked complete that is not
    complete is worse than one left running: the loop stops and nothing tells
    anybody it stopped early.

    Takes no arguments. What was achieved goes in your reply, where the user
    reads prose; this call only moves the row.

    Returns:
        GoalResult: the row's status read back (``complete``), the objective,
        and what the goal spent getting there — turns, tokens against the
        budget, wall clock. ``.changed`` is False if the goal was already
        stopped by someone else and this call did not move it.
    """
    return _end(GOAL_COMPLETE)


@subtool(tool="goal_blocked")
async def goal_blocked(reason: str) -> GoalResult:
    """End the goal because it needs a person: the work cannot proceed.

    ``reason`` is required and is stored on the row verbatim. It is the only
    thing the user gets to read about why the work stopped, so it names the
    missing thing — "the deploy key is not in this environment", not
    "stuck", not "needs input".

    Blocked means an external condition: information that is not available,
    access that is not granted, a decision only the user can make, or the same
    failure recurring with nothing left to try. It does NOT mean hard, slow,
    uncertain, unfinished, or "it would help to ask a question" — a goal that
    is merely not done yet is a goal that keeps going, and that is the
    feature. Do not use it as a way to end a turn.

    Returns:
        GoalResult: the row's status read back (``blocked``) with the reason
        on it, plus the spend. ``.changed`` is False if the goal was already
        stopped by someone else and this call did not move it.
    """
    if not reason or not reason.strip():
        raise GoalError(
            "goal_blocked needs the reason. It is stored on the goal and it is"
            " the only thing the user reads about why the work stopped, so"
            ' call it as goal_blocked("the deploy key is not in this'
            ' environment") — naming the missing thing, not "stuck".'
        )
    return _end(GOAL_BLOCKED, reason.strip())
