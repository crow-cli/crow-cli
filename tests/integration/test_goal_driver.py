"""The driver continues an active goal at the idle transition.

This is ACP_V2.md §5.4 built: the transition into idle is the trigger, the goal
is the thing that defers, and the deferral is an ordinary ``TaskDelivery`` row
that the loop's existing mailbox check picks up. No new event type, no wake
path, no clock, no worker — which is §5.3's argument for why a timer was the
wrong answer, vindicated rather than sidestepped.

Everything is real: the agent, the transport, the sqlite store, the react loop,
and (where a turn needs to have done work) a real FastMCP server spawned as a
subprocess. The model is scripted, because a gate that needs a provider is not
a gate. The harness is imported from ``test_agent2_gate`` rather than rebuilt —
one set of wire fakes.

What the assertions are about, in order of how badly they would fail in
production:

- a goal that keeps doing work keeps going, and the client never sees an idle
  it did not reach;
- a continuation that ran no tools STOPS, which is the whole difference
  between a feature and a token fire;
- a turn the USER caused is never judged by that rule, so asking a question
  mid-goal does not block your own goal;
- an errored turn blocks and a cancelled turn pauses, so neither loops;
- a goal the MODEL ended is not continued, and the turn that carried the
  ending cannot reopen it;
- the ceilings — turns and tokens — actually fire from here.
"""

from __future__ import annotations

import pytest
from acp.experimental import v2

from crow_cli.memory import (
    GOAL_BLOCKED,
    GOAL_BUDGET_LIMITED,
    GOAL_COMPLETE,
    GOAL_PAUSED,
    get_goal,
    pending_deliveries,
    set_goal,
    update_goal_status,
)
from crow_cli.tools.goal import _dispose, goal_done
from crow_cli.tools.register import begin_cell, clear

from tests.integration.test_agent2_gate import (
    HANG,
    call,
    gate,
    make_config,
    stdio_server,
    text,
    usage,
)

ECHO = '{"text": "hi"}'


def _config(tmp_path, **goal_kwargs):
    """The gate's config with the goal ceilings set. Assigned on the object
    rather than written into config.yaml because that is how a harness installs
    a setting it needs to vary per test, and ``Config.load`` already has its own
    test for the YAML path."""
    config = make_config(tmp_path)
    for key, value in goal_kwargs.items():
        setattr(config.goal, key, value)
    return config


@pytest.fixture
def rail():
    """The subtool identity rail, set the way execute's prologue sets it and
    taken down again afterwards. It is process-global — a contextvar plus the
    register's write-through sink — so leaving it standing would point the next
    test's subtool calls at this one's throwaway database."""
    yield begin_cell
    clear()
    _dispose()


def _row(g):
    return get_goal(g.agent.sessions.engine, g.session_id)


def _mailbox(g):
    return pending_deliveries(g.agent.sessions.engine, g.session_id)


def _last_user_text(call_kwargs: dict) -> str:
    """The most recent user message the model was sent, as text."""
    message = call_kwargs["messages"][-1]
    assert message["role"] == "user", message
    content = message["content"]
    if isinstance(content, str):
        return content
    return "".join(block.get("text", "") for block in content)


async def test_an_active_goal_continues_and_the_client_never_sees_an_idle_between(
    tmp_path,
):
    """THE mechanism. A turn that did work ends, the driver writes a
    continuation to the mailbox instead of announcing idle, the loop's existing
    ``_mailbox_pending()`` picks it up, and react's prompt-start consult injects
    it — so the session goes running -> running and the client sees one turn
    that kept going rather than two with a finished one in the middle.

    The ceiling is one turn so the test terminates on the budget rather than on
    a scripted stall: ``budget_limited`` at the end is the proof the counter
    moved, not just that a delivery landed.
    """
    scripts = [
        call(0, "c1", "echo", ECHO) + [usage(10)],
        text("first turn") + [usage(11)],
        call(0, "c2", "echo", ECHO) + [usage(20)],
        text("second turn") + [usage(5)],
    ]
    async with gate(tmp_path, scripts, config=_config(tmp_path, max_turns=1)) as g:
        await g.new_session(mcp_servers=[stdio_server(tmp_path)])
        await g.wait_for_idle(1)
        set_goal(g.agent.sessions.engine, g.session_id, "keep the widget ported")

        await g.prompt(v2.schema.TextContentBlock(text="go"))
        await g.wait_for_idle(2)

        # Two turns, four model calls, and only ONE running between the idles:
        # the second turn never announced itself because the session never
        # stopped being busy.
        assert len(g.llm.calls) == 4
        assert [s["state"] for s in g.states()] == ["idle", "running", "idle"]
        assert len(g.idles()) == 2

        row = _row(g)
        assert row.status == GOAL_BUDGET_LIMITED
        assert row.turns_used == 1
        # The continuation turn's WHOLE bill (20 + 5), and not the user turn's
        # (10 + 11): a turn the user prompted is spend they asked for and
        # watched happen, and charging it to the goal would make the ceiling
        # fire on conversation length rather than on autonomy.
        assert row.tokens_used == 25
        assert g.tokens_spent == 25
        assert _mailbox(g) == []

        # The continuation reached the model as a user message naming the
        # objective and the ceiling it is working under.
        injected = _last_user_text(g.llm.calls[2])
        assert injected.startswith("[goal: continuing automatically")
        assert "keep the widget ported" in injected
        assert "Turn 1 of at most 1" in injected
        assert "goal_done" in injected

        # And it reached the client, because a conversation that hides its own
        # inputs cannot be followed or replayed.
        chunks = g.of_kind("user_message_chunk")
        assert len(chunks) == 1
        assert chunks[0]["content"]["text"] == injected


async def test_a_continuation_that_ran_no_tools_ends_the_goal(tmp_path):
    """The loop guard, end to end. Without it the cycle is "model talks ->
    continue -> model talks", which terminates only when a budget does — and
    the default token budget is no budget at all."""
    scripts = [
        call(0, "c1", "echo", ECHO) + [usage(10)],
        text("did the work") + [usage(10)],
        text("I believe that is everything") + [usage(10)],
    ]
    async with gate(tmp_path, scripts) as g:
        await g.new_session(mcp_servers=[stdio_server(tmp_path)])
        await g.wait_for_idle(1)
        set_goal(g.agent.sessions.engine, g.session_id, "objective")

        await g.prompt(v2.schema.TextContentBlock(text="go"))
        await g.wait_for_idle(2)

        # Three calls and no fourth: the third was a continuation that touched
        # nothing, so there is no fourth.
        assert len(g.llm.calls) == 3
        row = _row(g)
        assert row.status == GOAL_BLOCKED
        assert "no tools" in row.blocked_reason
        assert row.turns_used == 1
        assert _mailbox(g) == []


async def test_a_text_only_turn_the_user_caused_does_not_end_the_goal(tmp_path):
    """The other half of the rule, and the reason the driver tracks whether IT
    wrote the continuation. A person who interjects a question mid-goal gets a
    text-only answer; blocking the goal for that punishes them for using it."""
    scripts = [
        text("just an answer, no tools") + [usage(10)],
        call(0, "c1", "echo", ECHO) + [usage(20)],
        text("worked") + [usage(20)],
    ]
    async with gate(tmp_path, scripts, config=_config(tmp_path, max_turns=1)) as g:
        await g.new_session(mcp_servers=[stdio_server(tmp_path)])
        await g.wait_for_idle(1)
        set_goal(g.agent.sessions.engine, g.session_id, "objective")

        await g.prompt(v2.schema.TextContentBlock(text="what is the status?"))
        await g.wait_for_idle(2)

        assert len(g.llm.calls) == 3  # the text-only turn DID continue
        row = _row(g)
        # Stopped by the ceiling, not by the no-progress rule.
        assert row.status == GOAL_BUDGET_LIMITED
        assert row.blocked_reason is None


async def test_a_turn_that_errored_blocks_the_goal(tmp_path):
    """A crash must stop the loop, not feed it: continuing re-runs a repeating
    failure and spends tokens learning nothing new. This is what codex does on
    a turn error and for the same reason."""
    async with gate(tmp_path, []) as g:  # nothing scripted: the first call raises
        await g.new_session()
        await g.wait_for_idle(1)
        set_goal(g.agent.sessions.engine, g.session_id, "objective")

        await g.prompt(v2.schema.TextContentBlock(text="go"))
        await g.wait_for_idle(2)

        assert g.idles()[1]["stopReason"] == "error"
        row = _row(g)
        assert row.status == GOAL_BLOCKED
        assert row.blocked_reason == "the turn errored"
        assert _mailbox(g) == []
        assert len(g.llm.calls) == 1


async def test_a_cancelled_turn_pauses_the_goal(tmp_path):
    """A cancel is the person stopping the work, not the work failing, so it
    pauses: the objective survives exactly as it was and ``/goal resume`` picks
    it back up. Leaving it active would mean the next idle immediately
    continues the turn the user just interrupted."""
    async with gate(tmp_path, [text("partial ") + [HANG]]) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        set_goal(g.agent.sessions.engine, g.session_id, "objective")

        await g.prompt(v2.schema.TextContentBlock(text="go on forever"))
        await g.wait_for(lambda: g.of_kind("agent_message_chunk"))
        await g.cancel()
        await g.wait_for_idle(2)

        assert g.idles()[1]["stopReason"] == "cancelled"
        row = _row(g)
        assert row.status == GOAL_PAUSED
        assert row.blocked_reason is None
        assert _mailbox(g) == []
        # Nothing was charged: the driver builds the cancelled Done itself and
        # the provider never reported a usage.
        assert row.tokens_used == 0


@pytest.mark.parametrize(
    "status", [GOAL_PAUSED, GOAL_BLOCKED, GOAL_BUDGET_LIMITED, GOAL_COMPLETE]
)
async def test_a_goal_that_is_not_active_is_not_continued(tmp_path, status):
    """``active_goal`` is the only read the driver makes, so every way of
    stopping a goal is one column compare — and a status someone else wrote is
    never overwritten by the policy layer."""
    scripts = [
        call(0, "c1", "echo", ECHO) + [usage(10)],
        text("done") + [usage(10)],
    ]
    async with gate(tmp_path, scripts) as g:
        await g.new_session(mcp_servers=[stdio_server(tmp_path)])
        await g.wait_for_idle(1)
        engine = g.agent.sessions.engine
        set_goal(engine, g.session_id, "objective")
        update_goal_status(engine, g.session_id, status)

        await g.prompt(v2.schema.TextContentBlock(text="go"))
        await g.wait_for_idle(2)

        assert len(g.llm.calls) == 2  # the tool round trip, and nothing more
        assert _row(g).status == status
        assert _mailbox(g) == []
        assert [s["state"] for s in g.states()] == ["idle", "running", "idle"]


async def test_the_token_budget_stops_a_goal_that_keeps_working(tmp_path):
    """The ceiling fires from the SQL ``CASE`` inside ``account_goal_usage``,
    during the settle, before the continuation is ever asked — so there is no
    window where an over-budget goal is still marked active and no Python
    re-check to get wrong."""
    scripts = [
        call(0, "c1", "echo", ECHO) + [usage(10)],
        text("user turn") + [usage(10)],
        call(0, "c2", "echo", ECHO) + [usage(100)],
        text("continuation one") + [usage(100)],
        call(0, "c3", "echo", ECHO) + [usage(50)],
        text("continuation two") + [usage(50)],
    ]
    async with gate(tmp_path, scripts, config=_config(tmp_path, max_turns=25)) as g:
        await g.new_session(mcp_servers=[stdio_server(tmp_path)])
        await g.wait_for_idle(1)
        set_goal(g.agent.sessions.engine, g.session_id, "objective", token_budget=250)

        await g.prompt(v2.schema.TextContentBlock(text="go"))
        await g.wait_for_idle(2)

        assert len(g.llm.calls) == 6
        row = _row(g)
        # 200 under the ceiling, then 300 over it — the write that crossed it
        # is the write that flipped the status.
        assert row.tokens_used == 300
        assert row.status == GOAL_BUDGET_LIMITED
        assert row.turns_used == 2
        assert row.blocked_reason is None
        assert _mailbox(g) == []


async def test_goal_done_from_the_kernel_ends_the_loop(tmp_path, rail):
    """The model's exit, and the claim the whole design rests on.

    ``goal_done`` runs in the execute kernel — a different process from the
    driver, with its own engine on the same file — and the row is the only
    thing between them. What it writes here is what ``_goal_continuation``
    reads at the idle transition, so the loop stops with nothing told to
    anybody: no event, no wake, no client round trip.

    The turn is text-only on purpose. A text-only turn the USER caused does
    continue (see above), so "no continuation" here can only mean
    ``active_goal`` found nothing.
    """
    scripts = [text("that is everything") + [usage(10)]]
    async with gate(tmp_path, scripts) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        set_goal(g.agent.sessions.engine, g.session_id, "finish the port")

        rail(session_id=g.session_id, db_uri=g.config.db_uri)
        result = await goal_done()
        assert (result.status, result.changed) == (GOAL_COMPLETE, True)

        await g.prompt(v2.schema.TextContentBlock(text="go"))
        await g.wait_for_idle(2)

        assert len(g.llm.calls) == 1
        assert _row(g).status == GOAL_COMPLETE
        assert _mailbox(g) == []
        assert [s["state"] for s in g.states()] == ["idle", "running", "idle"]


async def test_a_turn_that_errors_after_the_goal_was_ended_does_not_reopen_it(
    tmp_path, rail
):
    """The guard on ``_settle_goal``: only a goal that is still running is
    moved by how its turn ended.

    An exit that a later failure in the same turn can overwrite is not an
    exit. Without the guard this row comes back ``blocked`` — the model is
    told its finished work is stuck, and ``/goal`` shows a person a problem
    that does not exist.
    """
    async with gate(tmp_path, []) as g:  # nothing scripted: the first call raises
        await g.new_session()
        await g.wait_for_idle(1)
        set_goal(g.agent.sessions.engine, g.session_id, "finish the port")

        rail(session_id=g.session_id, db_uri=g.config.db_uri)
        assert (await goal_done()).status == GOAL_COMPLETE

        await g.prompt(v2.schema.TextContentBlock(text="go"))
        await g.wait_for_idle(2)

        assert g.idles()[1]["stopReason"] == "error"
        row = _row(g)
        assert row.status == GOAL_COMPLETE
        assert row.blocked_reason is None
        assert _mailbox(g) == []


async def test_cancelling_a_turn_that_already_ended_the_goal_does_not_pause_it(
    tmp_path, rail
):
    """The other half of the same guard. A cancel pauses a RUNNING goal so
    ``/goal resume`` can pick it back up; pausing a goal the model already
    completed would tell the user there is work left to resume."""
    async with gate(tmp_path, [text("partial ") + [HANG]]) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        set_goal(g.agent.sessions.engine, g.session_id, "finish the port")

        rail(session_id=g.session_id, db_uri=g.config.db_uri)
        assert (await goal_done()).status == GOAL_COMPLETE

        await g.prompt(v2.schema.TextContentBlock(text="go on forever"))
        await g.wait_for(lambda: g.of_kind("agent_message_chunk"))
        await g.cancel()
        await g.wait_for_idle(2)

        assert g.idles()[1]["stopReason"] == "cancelled"
        assert _row(g).status == GOAL_COMPLETE


async def test_a_session_with_no_goal_parks_as_before(tmp_path):
    """The regression half: no goal, no behaviour change. One prompt, one turn,
    one idle, and nothing written to a mailbox nobody is reading."""
    async with gate(tmp_path, [text("hi") + [usage(5)]]) as g:
        await g.new_session()
        await g.wait_for_idle(1)

        await g.prompt(v2.schema.TextContentBlock(text="say hi"))
        await g.wait_for_idle(2)

        assert len(g.llm.calls) == 1
        assert [s["state"] for s in g.states()] == ["idle", "running", "idle"]
        assert _row(g) is None
        assert _mailbox(g) == []
        assert g.of_kind("user_message_chunk") == []
