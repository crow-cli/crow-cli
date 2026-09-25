"""Goal continuation: the text it sends and the rules that stop it.

The load-bearing decision, so it is written down where the code is: **a goal
continuation is an ordinary :class:`~crow_cli.memory.models.TaskDelivery`
row.** No new event type in :mod:`crow_cli.agent2.events`, no second injection
path, no client involvement, nothing for the watcher to learn. The driver
notices an active goal at the idle transition, writes a delivery, and the loop
that already exists picks it up — which is ACP_V2.md §5.4, the state-triggered
wake that was designed and never built, with the goal as the thing that defers.

`TaskDelivery.task_id` has no foreign key, so it names the `goal_id` honestly
rather than pretending to be a task.

Why the stop condition lives in a status column and not in this module: the
question "should this session keep going" has to survive a process restart, be
answerable by a slash command, and be writable by a subtool running in the
execute kernel. Those are three different processes. A row is the only thing
all three can reach, so :func:`crow_cli.memory.reads.active_goal` is the
mechanism and this module is only the policy layered on it.

Two rules, and the reason each exists:

- a continuation turn that ran no tools ends the goal. This is the whole
  difference between a feature and a token fire: without it the loop is
  "model talks -> continue -> model talks", which terminates only when the
  budget does. A turn that touched nothing made no observable progress, and
  "no observable progress" is the only honest reading of it.
- `turns_used` against a configured ceiling. The backstop for the case where
  the model keeps finding real work forever.

The token ceiling is deliberately NOT re-checked here. It lives in the
``CASE`` inside :func:`crow_cli.memory.writes.account_goal_usage`'s single
UPDATE, and a Python read-compare-write on top of it would reintroduce exactly
the window that ``CASE`` closes. By the time the driver asks, an over-budget
goal is already `budget_limited` and `active_goal` has already returned None.
"""

from __future__ import annotations

from dataclasses import dataclass

from crow_cli.memory.models import GOAL_ACTIVE, GOAL_BLOCKED, GOAL_BUDGET_LIMITED

#: Injected as a synthetic user message, so it is echoed to the client by
#: :func:`crow_cli.agent2.deliveries.consult` and reads as what it is:
#: something the agent said to itself, not something the user typed.
#:
#: Deliberately short. codex's `continuation.md` is 56 lines of completion
#: audit ritual; the three things that actually change model behaviour are the
#: objective, the fact that the budget is finite, and the names of the two
#: exits. Everything else is repetition, and repetition in a prompt that fires
#: every turn is a tax on every turn.
CONTINUATION_PROMPT = """[goal: continuing automatically — the user did not send this]

Objective: {objective}

{progress}

Keep working. Check your work against what is actually there rather than
against your memory of the conversation: re-read the file, re-run the command,
look at the output.

When the objective is genuinely met, call goal_done. When it is genuinely
stuck — missing information, missing access, a decision only the user can make
— call goal_blocked with the reason. Neither is a way to end the turn: if
there is nothing left to do, that is goal_done, and inventing work to fill the
turn is worse than stopping.
"""


@dataclass(frozen=True, slots=True)
class Verdict:
    """Why a goal may not continue, and what to write down about it.

    ``status`` is the row's new status, or None when the row already says what
    it needs to say — a goal that is paused or complete was stopped by someone
    else, and writing a status over that decision would be this module
    overruling the user. ``reason`` is stored as the blocked reason and shown
    by ``/goal``, so it is written for the person who has to act on it.
    """

    status: str | None
    reason: str


def continuation_text(goal, *, max_goal_turns: int | None = None) -> str:
    """The delivery body for one continuation of ``goal``."""
    return CONTINUATION_PROMPT.format(
        objective=goal.objective,
        progress=progress(goal, max_goal_turns),
    )


def progress(goal, max_goal_turns: int | None) -> str:
    """Where the goal stands, as one line. A model that cannot see the ceiling
    cannot budget against it, and a continuation that never mentions the cap
    gets an even 25 turns of confidence.

    Public because the user's ``/goal`` status shows the same fact. Two
    renderings of one row would drift, and the drift would be invisible: the
    model would be told one ceiling and the person another.
    """
    turns = f"Turn {goal.turns_used + 1}"
    turns += f" of at most {max_goal_turns}" if max_goal_turns else " of this goal"
    if goal.token_budget is None:
        return f"{turns}. No token ceiling."
    return f"{turns}. Tokens {goal.tokens_used} of {goal.token_budget}."


def eligible(
    goal,
    *,
    tools_used: int,
    was_continuation: bool,
    max_goal_turns: int | None = None,
) -> Verdict | None:
    """None when the goal may continue; a :class:`Verdict` when it may not.

    ``was_continuation`` is what makes the no-progress rule safe to have. It
    must fire on a turn the goal itself caused and NOT on a turn the user
    caused: a person who interjects "what's the status?" mid-goal gets a
    text-only answer, and blocking the goal because they asked a question
    would be punishing them for using it. The driver knows which kind of turn
    just finished; this module only decides what to do about it.
    """
    if goal is None:
        return Verdict(None, "no active goal")
    if goal.status != GOAL_ACTIVE:
        # Someone already stopped it. Not this module's call to overwrite.
        return Verdict(None, f"goal is {goal.status}")
    if max_goal_turns is not None and goal.turns_used >= max_goal_turns:
        return Verdict(
            GOAL_BUDGET_LIMITED,
            f"turn budget spent: {goal.turns_used} of {max_goal_turns}",
        )
    if was_continuation and tools_used <= 0:
        return Verdict(
            GOAL_BLOCKED,
            "the last continuation ran no tools — nothing observable happened, "
            "so it stopped rather than spend another turn finding out",
        )
    return None
