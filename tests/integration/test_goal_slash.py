"""``/goal`` as the person types it: the help branch and the whole-word rule.

The bug this file exists for is a command that failed by SUCCEEDING. The
handler recognized three words — ``clear``, ``pause``, ``resume`` — and sent
everything else to ``_set``, so ``/goal help`` answered ``Goal set: "help"``
over a row that made the session continue itself. Asking what the loop does
armed the loop. Nothing in the reply said so, and the only way to see it was
``/goal`` a moment later or the token bill.

Everything runs through the real dispatch — ``CrowAgentV2._slash`` over the
registry, the real sqlite store, the real driver at the idle transition — so
what is asserted is the row and the mailbox, not the handler's return value in
isolation. The model is scripted, as ever: a gate that needs a provider is not
a gate.
"""

from __future__ import annotations

import pytest
from acp.experimental import v2

from crow_cli.agent2.slash import _help
from crow_cli.config import GoalConfig
from crow_cli.memory import GOAL_BLOCKED, get_goal, pending_deliveries

from tests.integration.test_agent2_gate import gate, make_config, text, usage


def _config(tmp_path, **goal_kwargs):
    """The gate's config with the goal ceilings set, so the help text can be
    asserted against numbers this test chose rather than against the defaults
    — a help text that echoes a default proves nothing about the lookup."""
    config = make_config(tmp_path)
    for key, value in goal_kwargs.items():
        setattr(config.goal, key, value)
    return config


def _row(g):
    return get_goal(g.agent.sessions.engine, g.session_id)


def _mailbox(g):
    return pending_deliveries(g.agent.sessions.engine, g.session_id)


def _reply(g) -> str:
    return g.of_kind("agent_message")[0]["content"][0]["text"]


@pytest.mark.parametrize("word", ["help", "?"])
async def test_asking_what_goal_does_runs_nothing(tmp_path, word):
    """The regression. No row, no delivery, no model call, and the session
    parks — the reply is the whole effect of the turn.

    ``scripts=[]`` is the assertion doing the work: a help branch that armed a
    goal would reach the model on the continuation and blow up here rather
    than pass quietly.
    """
    config = _config(tmp_path, max_turns=7, max_tokens=4000)
    async with gate(tmp_path, [], config=config) as g:
        await g.new_session()
        await g.wait_for_idle(1)

        await g.prompt(v2.schema.TextContentBlock(text=f"/goal {word}"))
        await g.wait_for_idle(2)

        body = _reply(g)
        assert body.startswith("/goal")
        for fragment in (
            "/goal <objective>",
            "/goal pause",
            "/goal resume",
            "/goal clear",
            "goal_done",
            "goal_start",
            "goal_reset",
        ):
            assert fragment in body, fragment

        assert _row(g) is None
        assert _mailbox(g) == []
        assert g.llm.calls == []
        assert [s["state"] for s in g.states()] == ["idle", "running", "idle"]


async def test_help_shows_the_ceilings_this_config_actually_has(tmp_path):
    """The numbers are the reason to ask, so they are read off the config and
    not hardcoded into the text."""
    body = _help(GoalConfig(max_turns=7, max_tokens=4000))
    assert "at most 7 continuation turns" in body
    assert "at most 4,000 tokens" in body

    unlimited = _help(GoalConfig(max_turns=0, max_tokens=None))
    assert "no turn ceiling" in unlimited
    assert "no token ceiling" in unlimited


async def test_a_reserved_word_counts_only_as_the_whole_argument(tmp_path):
    """``/goal help me port the widget`` is an objective, and a good one.

    The rule is whole-argument for every reserved word, which is what keeps an
    ordinary imperative objective typeable: first-word-wins would swallow
    "clear the build cache" and "help me port the widget" with it. Asserted
    through the driver rather than against ``_set``, because the half that
    matters is that this one DOES arm the loop the help branch refuses to.
    """
    scripts = [text("on it") + [usage(5)]]
    async with gate(tmp_path, scripts) as g:
        await g.new_session()
        await g.wait_for_idle(1)

        await g.prompt(
            v2.schema.TextContentBlock(text="/goal help me port the widget")
        )
        await g.wait_for_idle(2)

        row = _row(g)
        assert row.objective == "help me port the widget"
        # Armed, and the driver went on with it at the same idle transition the
        # help branch leaves empty. The continuation ran no tools, so the
        # no-progress rule ended it — one model call and no second.
        assert row.status == GOAL_BLOCKED
        assert "no tools" in row.blocked_reason
        assert len(g.llm.calls) == 1
        assert _mailbox(g) == []
