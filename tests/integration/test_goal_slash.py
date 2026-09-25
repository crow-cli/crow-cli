"""``/goal``, driven through the real prompt dispatch.

The handler is tested the way :mod:`tests.integration.test_slash_commands`
tests v1's: text in at ``session/prompt``, the reply the client actually saw
out at ``agent_message``, and the row read back from the database the DRIVER
reads. Dispatch and handler together, because a handler that works when called
directly and raises through the dispatch is the failure this command must not
have — a slash handler that throws becomes an ACP internal error, which the
client reads as a failed turn.

Nothing here is patched. The model is absent from most of these tests, which
is itself an assertion — a command is foreground work that never calls one —
and where a script appears it is because the row under test is ACTIVE, and an
active goal on an idle session gets picked up on the spot. That is not a
quirk of the harness: codex does the same thing, ``apply_external_goal_set``
calling ``continue_if_idle()`` for a goal that is Active
(ext/goal/src/runtime.rs:217-234). Most tests therefore run with a zero turn
ceiling, which stops the pickup before it reaches a model and leaves
``budget_limited`` in the row as the trace of an active one.
"""

from __future__ import annotations

import subprocess
import sys

import pytest
from acp.experimental import v2
from sqlalchemy import text as sql_text

from crow_cli.memory import (
    GOAL_ACTIVE,
    GOAL_BLOCKED,
    GOAL_BUDGET_LIMITED,
    GOAL_COMPLETE,
    GOAL_PAUSED,
    account_goal_usage,
    get_goal,
    set_goal,
    update_goal_status,
)

from tests.integration.test_agent2_gate import gate, text, usage
from tests.integration.test_goal_driver import _config, _last_user_text

OBJECTIVE = "port the option list widget to ratatui"


class Slash:
    """One session, commands typed at it, replies collected.

    ``wait_for_idle`` counts idles rather than waiting for "the next one", so
    the running total lives here instead of in every test. Waiting on the idle
    is also waiting on the row: ``_park`` consults the goal BEFORE it
    announces idle, so by the time a command's reply is in hand every
    consequence of that command has been written.
    """

    def __init__(self, g) -> None:
        self.g = g
        self.idles = 1

    async def say(self, command: str) -> str:
        self.idles += 1
        await self.g.prompt(v2.schema.TextContentBlock(text=command))
        await self.g.wait_for_idle(self.idles)
        return self.g.of_kind("agent_message")[-1]["content"][0]["text"]

    @property
    def row(self):
        return get_goal(self.g.agent.sessions.engine, self.g.session_id)

    @property
    def engine(self):
        return self.g.agent.sessions.engine


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


async def test_the_client_is_told_the_command_exists(tmp_path):
    """A command nobody can discover is a command nobody types. The list is
    advertised at ``session/new``, which is the only place the protocol has."""
    async with gate(tmp_path, [], config=_config(tmp_path)) as g:
        await g.new_session()
        await g.wait_for_idle(1)

        (update,) = g.of_kind("available_commands_update")
        commands = update["availableCommands"]
        names = [c["name"] for c in commands]
        assert "goal" in names
        assert {"compact", "help", "clear", "stop"} <= set(names)
        (goal,) = [c for c in commands if c["name"] == "goal"]
        assert "clear|pause|resume" in goal["description"]


def test_a_v1_process_never_sees_it():
    """The registry is one module-level list that BOTH generations read, so
    ``/goal`` is registered from agent2 and not from ``agent/slash.py``.

    Checked in a fresh interpreter that imports only v1, because in THIS
    process agent2 has already been imported and the table is shared — the
    claim is about what a v1 process sees, and only a v1 process can answer it.
    v1 runs no continuation loop, so a ``/goal`` there would answer "goal set"
    and then nothing would ever happen.
    """
    code = (
        "import crow_cli.agent.main, crow_cli.agent.slash as s;"
        "print(sorted(c['name'] for c in s._SLASH_COMMANDS))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=180
    )
    assert out.returncode == 0, out.stderr[-800:]
    assert "goal" not in out.stdout
    assert "compact" in out.stdout


# ---------------------------------------------------------------------------
# Setting and showing
# ---------------------------------------------------------------------------


async def test_bare_goal_with_nothing_set_says_so(tmp_path):
    async with gate(tmp_path, [], config=_config(tmp_path)) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        s = Slash(g)

        reply = await s.say("/goal")
        assert "No goal is set" in reply
        assert "/goal <objective>" in reply
        assert s.row is None
        assert g.llm.calls == []


async def test_setting_a_goal_stores_the_row(tmp_path):
    """The objective and the configured ceiling land in the row the driver
    reads, with the counters at zero.

    ``budget_limited`` at the end is not a second assertion about budgets, it
    is the evidence for the first one: only an ACTIVE row is continued, and
    only a continuation consults the ceiling. A handler that stored nothing,
    or stored it under a status the driver ignores, would leave no row at all.
    """
    config = _config(tmp_path, max_turns=0, max_tokens=200_000)
    async with gate(tmp_path, [], config=config) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        s = Slash(g)

        reply = await s.say(f"/goal {OBJECTIVE}")

        row = s.row
        assert row is not None
        assert row.objective == OBJECTIVE
        # config.goal.max_tokens is the default budget and this is the only
        # place it is consumed — a ceiling nobody passes is a ceiling nobody
        # has.
        assert row.token_budget == 200_000
        assert (row.turns_used, row.tokens_used, row.time_used_seconds) == (0, 0, 0)
        assert row.status == GOAL_BUDGET_LIMITED
        assert OBJECTIVE in reply
        assert "goal_done" in reply and "goal_blocked" in reply
        assert "200,000" in reply
        # Neither a command nor a continuation the ceiling refused reaches one.
        assert g.llm.calls == []


async def test_setting_a_goal_on_an_idle_session_starts_work_at_once(tmp_path):
    """The behaviour the zero ceilings above are working around, asserted
    rather than left to surprise the next reader.

    Codex does this deliberately: ``apply_external_goal_set`` calls
    ``continue_if_idle()`` for a goal whose status is Active
    (ext/goal/src/runtime.rs:217-234), and the deferral table that suppresses
    the pickup exists only for FORKED threads, which inherit a goal snapshot
    nobody has started a turn in yet (its one inserter,
    ``replace_thread_goal_snapshot``, has one caller:
    app-server/src/request_processors/thread_fork_goal.rs:25). crow reaches the
    same place by its own shape — the handler returns without running a turn,
    the loop reaches ``_park``, and ``_goal_continuation`` finds an active goal
    on a session with nothing in flight.

    So a person who types ``/goal`` and walks away comes back to work that was
    done, not to a session sitting idle on the objective it was just handed.
    """
    scripts = [text("on it") + [usage(10)]]
    async with gate(tmp_path, scripts, config=_config(tmp_path, max_turns=1)) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        s = Slash(g)

        await s.say(f"/goal {OBJECTIVE}")

        # One model call, and the driver made it without being asked: the
        # continuation reached the model as a user message naming the objective
        # and the ceiling it is working under.
        (call_kwargs,) = g.llm.calls
        injected = _last_user_text(call_kwargs)
        assert injected.startswith("[goal: continuing automatically")
        assert OBJECTIVE in injected
        assert "Turn 1 of at most 1" in injected

        row = s.row
        assert row.status == GOAL_BUDGET_LIMITED
        assert row.turns_used == 1
        assert row.tokens_used == 10


async def test_a_new_objective_starts_over(tmp_path):
    """``set_goal`` always mints a fresh id and zeroes the counters, with no
    special case for the objective that is already there: a loop guard that
    inherits its predecessor's spend stops guarding.

    codex keeps the id and the usage on a re-set (ext/goal/src/api.rs:194-239).
    This is a deliberate divergence and the counters are where it shows — nine
    turns charged to the first objective would be nine of the second's ceiling
    spent before it started.
    """
    async with gate(tmp_path, [], config=_config(tmp_path, max_turns=0)) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        s = Slash(g)

        await s.say(f"/goal {OBJECTIVE}")
        first = s.row
        account_goal_usage(
            s.engine, g.session_id, goal_id=first.goal_id,
            tokens=99, seconds=60, turns=9,
        )

        await s.say("/goal and then write the tests for it")

        second = s.row
        assert second.goal_id != first.goal_id
        assert second.objective == "and then write the tests for it"
        assert (second.turns_used, second.tokens_used) == (0, 0)
        assert second.time_used_seconds == 0


async def test_bare_goal_shows_the_state_the_model_is_shown(tmp_path):
    """The status line and the continuation prompt are built by the SAME
    function, so the person and the agent cannot be told two different
    ceilings. Asserted on the rendered text, because the drift this guards
    against is a drift in rendering.

    The row is written directly rather than through ``/goal`` because the
    command under test is the bare one, and the scripted turn below is not
    part of it — it is the pickup an active goal on an idle session gets, which
    the command has no say in.
    """
    scripts = [text("noted") + [usage(10)]]
    async with gate(tmp_path, scripts, config=_config(tmp_path, max_turns=25)) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        s = Slash(g)
        set_goal(s.engine, g.session_id, OBJECTIVE, token_budget=40_000)
        account_goal_usage(
            s.engine, g.session_id, goal_id=s.row.goal_id,
            tokens=18_204, seconds=372, turns=3,
        )

        reply = await s.say("/goal")
        assert f'goal {GOAL_ACTIVE} — "{OBJECTIVE}"' in reply
        assert "Turn 4 of at most 25. Tokens 18204 of 40000." in reply
        assert "6m12s of agent time" in reply


# ---------------------------------------------------------------------------
# The three subcommands
# ---------------------------------------------------------------------------


async def test_pause_and_resume_round_trip(tmp_path):
    """Written straight to the row rather than set through ``/goal``, because
    the command under test is ``pause`` and an active goal on an idle session
    is picked up before the test can say anything about it."""
    async with gate(tmp_path, [], config=_config(tmp_path, max_turns=0)) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        s = Slash(g)
        set_goal(s.engine, g.session_id, OBJECTIVE)

        reply = await s.say("/goal pause")
        assert s.row.status == GOAL_PAUSED
        assert "/goal resume" in reply

        # Pausing twice is an answer, not an error.
        assert "already paused" in await s.say("/goal pause")
        assert s.row.status == GOAL_PAUSED

        reply = await s.say("/goal resume")
        assert "Goal resumed from paused" in reply
        assert OBJECTIVE in reply
        # Stronger than asserting the row is active, which is a snapshot the
        # driver has already moved past by the time the reply is in hand: the
        # zero ceiling only writes over a row it found ACTIVE at the idle
        # transition, so this is the resume having taken AND the latch having
        # re-armed on the spot.
        assert s.row.status == GOAL_BUDGET_LIMITED
        assert g.llm.calls == []


async def test_resume_from_blocked_drops_the_reason(tmp_path):
    """``update_goal_status`` keeps a reason only for ``blocked``, so a resumed
    goal does not carry the excuse it was resumed from."""
    async with gate(tmp_path, [], config=_config(tmp_path, max_turns=0)) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        s = Slash(g)
        set_goal(s.engine, g.session_id, OBJECTIVE)
        update_goal_status(
            s.engine, g.session_id, GOAL_BLOCKED, blocked_reason="no deploy key"
        )

        shown = await s.say("/goal")
        assert "why: no deploy key" in shown

        reply = await s.say("/goal resume")
        assert "Goal resumed from blocked" in reply
        assert "no deploy key" not in reply
        row = s.row
        assert row.blocked_reason is None
        assert row.status == GOAL_BUDGET_LIMITED


@pytest.mark.parametrize(
    "status,expect",
    [
        (GOAL_COMPLETE, "the model finished it"),
        (GOAL_BUDGET_LIMITED, "its budget is spent"),
    ],
)
async def test_resume_refuses_a_goal_that_is_finished_or_spent(
    tmp_path, status, expect
):
    """Resuming either would stop again at once — the turn ceiling and the
    token ``CASE`` both read counters that resuming does not reset — and a
    command that appears to work and then does nothing reads as a bug. The
    gesture "start this over" is ``/goal <objective>``, which says so."""
    async with gate(tmp_path, [], config=_config(tmp_path)) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        s = Slash(g)
        set_goal(s.engine, g.session_id, OBJECTIVE)
        update_goal_status(s.engine, g.session_id, status)

        reply = await s.say("/goal resume")
        assert expect in reply
        assert "/goal <objective>" in reply
        assert s.row.status == status


async def test_clear_removes_the_row(tmp_path):
    async with gate(tmp_path, [], config=_config(tmp_path, max_turns=0)) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        s = Slash(g)
        await s.say(f"/goal {OBJECTIVE}")

        assert "Goal cleared" in await s.say("/goal clear")
        assert s.row is None
        # "There was nothing to clear" is a different answer than "done".
        assert "Nothing to clear" in await s.say("/goal clear")


@pytest.mark.parametrize("verb", ["clear", "pause", "resume"])
async def test_the_subcommands_with_no_goal_say_so(tmp_path, verb):
    async with gate(tmp_path, [], config=_config(tmp_path)) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        s = Slash(g)

        reply = await s.say(f"/goal {verb}")
        assert "No goal is set" in reply
        assert s.row is None


@pytest.mark.parametrize("verb", ["clear", "pause", "resume"])
async def test_a_subcommand_word_is_only_one_when_it_is_the_whole_argument(
    tmp_path, verb
):
    """``/goal clear the build cache`` is an objective, because first-word-wins
    would make an ordinary imperative untypeable — and "clear", "pause" and
    "resume" all start objectives people actually write."""
    async with gate(tmp_path, [], config=_config(tmp_path, max_turns=0)) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        s = Slash(g)

        await s.say(f"/goal {verb} the build cache")

        row = s.row
        assert row is not None
        assert row.objective == f"{verb} the build cache"
        # It was stored as an objective and not mistaken for a command, and
        # the ceiling only fires on a row that was active.
        assert row.status == GOAL_BUDGET_LIMITED
        assert g.llm.calls == []


async def test_no_database_means_nowhere_to_keep_a_goal(tmp_path):
    """No ``db_uri``, so no engine, so no row and nothing that could read one
    back. Said plainly rather than answering "goal set" over a write that went
    nowhere."""
    config = _config(tmp_path)
    config.db_uri = None
    async with gate(tmp_path, [], config=config) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        s = Slash(g)

        assert g.agent.sessions.engine is None
        for command in ("/goal", f"/goal {OBJECTIVE}", "/goal clear"):
            assert "No database is configured" in await s.say(command)


# ---------------------------------------------------------------------------
# Answering instead of throwing
# ---------------------------------------------------------------------------


async def test_a_row_it_cannot_render_is_an_answer_not_a_failed_turn(tmp_path):
    """The handler contract from :mod:`crow_cli.agent.slash`: it answers. An
    exception escaping it becomes an ACP internal error, which the client reads
    as a FAILED TURN rather than as "your goal row is unreadable" — and the
    person who typed ``/goal`` to find out where things stand is the one person
    who must not be told the session broke.

    The broken row is a real one rather than a patched engine: SQLite gives an
    INTEGER column numeric AFFINITY, not a type, so a writer that put a string
    in ``time_used_seconds`` stored a string, and ``NOT NULL`` is no defence.
    The goal is paused so the driver's own read of the same row stops at
    ``eligible``'s status check and never reaches the field that raises — which
    is why the session is still alive to be asked again at the end.
    """
    async with gate(tmp_path, [], config=_config(tmp_path)) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        s = Slash(g)
        set_goal(s.engine, g.session_id, OBJECTIVE)
        update_goal_status(s.engine, g.session_id, GOAL_PAUSED)
        with s.engine.begin() as db:
            db.execute(sql_text("UPDATE goals SET time_used_seconds = 'lots'"))

        reply = await s.say("/goal")
        assert reply.startswith("Error handling /goal:")
        assert "divmod" in reply

        # Still a session, still answering: the turn was reported, not thrown.
        assert "Goal cleared" in await s.say("/goal clear")
        assert s.row is None
