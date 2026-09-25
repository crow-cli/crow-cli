"""The v2-only slash commands. Right now that is one: ``/goal``.

It lives here and not in :mod:`crow_cli.agent.slash` with the other four
because the registry is a module-level list that BOTH generations read — v1
dispatches from it and advertises it over ``available_commands_update``. A
command registered there shows up in a v1 session, and v1 runs no continuation
loop, so ``/goal port the widget`` would answer "goal set" and then nothing
would ever happen. Same reasoning as ``goal_done`` sitting in ``_LAZY_V2``
rather than ``_LAZY``: an exit from a loop that does not exist is a call that
succeeds, changes a row, and means nothing.

The two generations are separate processes — ``crow-cli acp`` runs
``crow_cli.agent.main``, ``crow-cli acp2`` runs ``crow_cli.agent2.main`` — so
importing this module from :mod:`crow_cli.agent2.agent` registers ``/goal`` in
exactly the process that can honour it and v1 never sees the name.

The handler contract is :mod:`crow_cli.agent.slash`'s and is not relaxed here:
``async def cmd(session, args, agent) -> str``, keyed by the WIRE session id,
and it must not raise — an exception becomes an ACP internal error, which the
client reads as a failed turn rather than as an answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from crow_cli.agent.slash import register_slash_command
from crow_cli.memory import (
    GOAL_ACTIVE,
    GOAL_BLOCKED,
    GOAL_BUDGET_LIMITED,
    GOAL_PAUSED,
    clear_goal,
    get_goal,
    set_goal,
    update_goal_status,
)

from .goal import progress

if TYPE_CHECKING:
    from crow_cli.agent.session import AgentSession

#: Recognized only when the word is the WHOLE argument. ``/goal clear the build
#: cache`` sets an objective called "clear the build cache"; ``/goal clear``
#: deletes the row. One rule, and it is a rule that fits in a help line — the
#: alternative, first-word-wins, makes an ordinary imperative objective
#: untypeable, and "clear", "pause" and "resume" all start objectives people
#: actually write.
_SUBCOMMANDS = frozenset({"clear", "pause", "resume"})

#: What ``resume`` picks back up: the two statuses that mean "the work is
#: unfinished and the reason it stopped has been addressed". A budget-limited
#: goal has spent its rope, so resuming it without more would stop again on the
#: next turn and read as a bug; a complete goal is the model saying it
#: finished. Both are started again with ``/goal <objective>``, which mints a
#: fresh id and zeroes the counters — the gesture "start this over" wants.
_RESUMABLE = frozenset({GOAL_PAUSED, GOAL_BLOCKED})

_NO_GOAL = "No goal is set on this session."


@register_slash_command(
    "goal",
    "Set, show or stop the goal this session keeps working on"
    " (/goal | /goal <objective> | /goal clear|pause|resume)",
)
async def goal_command(session: AgentSession, args: str, agent: Any) -> str:
    """Show the goal, set one, or move it. Never raises."""
    engine = agent._engine
    if engine is None:
        # No db_uri, so there is nowhere to keep a row and nothing that could
        # read one back. Said plainly rather than answering "goal set" over a
        # write that went nowhere.
        return "No database is configured, so there is nowhere to keep a goal."
    session_id = session.session_id
    args = (args or "").strip()
    try:
        if not args:
            return _show(engine, session_id, agent._config.goal.max_turns)
        if args in _SUBCOMMANDS:
            return _transition(engine, session_id, args)
        return _set(engine, session_id, args, agent._config.goal)
    except Exception as exc:  # the contract: a handler answers, it does not throw
        agent._logger_for(session_id).error("/goal failed: %s", exc, exc_info=True)
        return f"Error handling /goal: {exc}"


def _set(engine, session_id: str, objective: str, goal_config: Any) -> str:
    """Arm the latch. Always a fresh goal: new id, zeroed counters, active."""
    set_goal(engine, session_id, objective, token_budget=goal_config.max_tokens)
    budget = (
        f" Token budget {goal_config.max_tokens:,}." if goal_config.max_tokens else ""
    )
    return "\n".join(
        [
            f'Goal set: "{objective}"',
            "This session will keep working on it — a turn that ends with the"
            " goal still active sends itself another, until the model calls"
            f" goal_done or goal_blocked, or a ceiling fires.{budget}",
            "/goal shows where it is, /goal pause stops it.",
        ]
    )


def _show(engine, session_id: str, max_turns: int | None) -> str:
    row = get_goal(engine, session_id)
    if row is None:
        return (
            f"{_NO_GOAL}\n"
            "/goal <objective> sets one, and this session will keep working on"
            " it until the model says it is done or stuck, or a ceiling fires."
        )
    minutes, seconds = divmod(row.time_used_seconds or 0, 60)
    lines = [
        f'goal {row.status} — "{row.objective}"',
        # The same line the model is sent, so the person and the agent are
        # never told two different ceilings.
        progress(row, max_turns),
        f"{minutes}m{seconds:02d}s of agent time on it.",
    ]
    if row.status == GOAL_BLOCKED and row.blocked_reason:
        lines.append(f"why: {row.blocked_reason}")
    return "\n".join(lines)


def _transition(engine, session_id: str, verb: str) -> str:
    """clear | pause | resume.

    The user's gesture, so no ``expected_goal_id``: the write means whatever
    row is there now, unlike the driver's automatic ones, which carry the id
    they read so a goal replaced mid-turn is left alone.
    """
    if verb == "clear":
        if clear_goal(engine, session_id):
            return "Goal cleared. This session stops continuing itself."
        return f"{_NO_GOAL} Nothing to clear."

    row = get_goal(engine, session_id)
    if row is None:
        return f"{_NO_GOAL} Nothing to {verb}."

    if verb == "pause":
        if row.status != GOAL_ACTIVE:
            return f"The goal is already {row.status}, so there is nothing to pause."
        update_goal_status(engine, session_id, GOAL_PAUSED)
        return (
            "Goal paused — this session stops continuing itself, and the"
            " objective and its spend are kept as they are. /goal resume picks"
            " it back up."
        )

    if row.status == GOAL_ACTIVE:
        return "The goal is already active and this session is already continuing it."
    if row.status not in _RESUMABLE:
        # Two statuses and two different reasons, neither of them a refusal to
        # be helpful: resuming either would stop again at once, which reads as
        # a bug rather than as an answer.
        why = (
            "its budget is spent, and resuming it would hit the same ceiling on"
            " the next turn"
            if row.status == GOAL_BUDGET_LIMITED
            else "the model finished it"
        )
        return (
            f"The goal is {row.status}: {why}. /goal <objective> starts it over"
            " — a fresh id, zeroed counters, and the objective can be the same"
            " one."
        )
    # blocked_reason goes with it: update_goal_status keeps a reason only for
    # blocked, so a resumed goal does not carry the excuse it was resumed from.
    update_goal_status(engine, session_id, GOAL_ACTIVE)
    return (
        f'Goal resumed from {row.status}: "{row.objective}"\n'
        "This session continues it again at the next idle."
    )
