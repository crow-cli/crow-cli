"""
Delegation hold (integration — REAL sqlite persistence).

While a subagent is RUNNING, the parent's turn does NOT end: the react loop
withholds end_turn and holds itself open — alive and cancellable — until the
reply lands. There is no out-of-loop watcher; nothing self-wakes a session.

- reply lands during the hold  -> injected in-turn, the model reacts;
- cancel during the hold       -> ONLY the parent turn stops; the subagent
  keeps running and its reply stays QUEUED in the mailbox until the user's
  next prompt (the prompt-start drain);
- task stops running without a delivery (defensive) -> the hold releases
  and the turn ends.
"""

import asyncio
import logging

import crow_cli.agent.react as react_mod
from crow_cli.agent.react import react_loop
from crow_cli.memory import get_engine, pending_deliveries
from crow_cli.memory.reads import get_task
from crow_cli.memory.writes import cancel_task, finish_task, launch_task

from tests.integration.test_react_loop_cancel_integrity import (
    AGENT_ID,
    SESSION_ID,
    FakeConn,
    content_chunk,
    drive_react_loop,
    make_test_session,
    usage_chunk,
    wait_until,
)
from tests.integration.test_react_loop_tool_round import MultiTurnLLM

logger = logging.getLogger(__name__)


async def _run_loop(config, session, llm, conn=None):
    gen = react_loop(
        conn=conn or FakeConn(),
        config=config,
        client_capabilities=None,
        turn_id="turn-1",
        mcp_clients={},
        llm=llm,
        tools=[],
        sessions={AGENT_ID: session},
        agent_id=AGENT_ID,
        state_accumulators={},
        logger=logger,
        hooks=[],
    )
    return await drive_react_loop(gen)


async def test_turn_holds_open_until_running_task_delivers(tmp_path, monkeypatch):
    """Model done + task still running -> NO end_turn. The loop holds
    itself open until the reply lands, injects it, and gives the model one
    reaction round — all inside the SAME turn."""
    monkeypatch.setattr(react_mod, "DELIVERY_POLL_S", 0.01)

    config, session = await make_test_session(tmp_path)
    await session.add_message({"role": "user", "content": "delegate the work"})

    engine = get_engine(config.db_uri)
    launch_task(engine, task_id="task-1", owner_session=SESSION_ID)

    async def child_finishes():
        await asyncio.sleep(0.05)
        finish_task(
            engine,
            "task-1",
            result="42",
            content="[task-1: subagent shy-fox finished]\n42",
        )

    llm = MultiTurnLLM(
        [
            [content_chunk("Delegated — waiting for the subagent."), usage_chunk(10)],
            [content_chunk("Subagent returned 42."), usage_chunk(10)],
        ]
    )
    finisher = asyncio.create_task(child_finishes())
    events, stop = await _run_loop(config, session, llm)
    await finisher
    assert stop == "done", events

    # Two model rounds IN ONE TURN: the pre-hold message, then the reaction
    # to the injected reply. Without the hold the turn would have ended
    # after round one.
    assert len(llm.create_kwargs) == 2
    second_user_texts = [
        str(m.get("content"))
        for m in llm.create_kwargs[1]["messages"]
        if m["role"] == "user"
    ]
    assert any("task-1" in t for t in second_user_texts), second_user_texts

    # Mailbox drained exactly once; the reply persists in history.
    assert pending_deliveries(engine, SESSION_ID) == []
    assert any(
        m["role"] == "user" and "task-1" in str(m.get("content"))
        for m in session.messages
    )
    await session.close()


async def test_cancel_during_hold_queues_reply_until_user_resumes(
    tmp_path, monkeypatch
):
    """Cancel during the hold kills ONLY the parent turn. The subagent
    stays running; its reply, landing later, is NOT auto-injected (there is
    no watcher) — it queues until the user's next prompt drains it."""
    monkeypatch.setattr(react_mod, "DELIVERY_POLL_S", 0.01)

    config, session = await make_test_session(tmp_path)
    await session.add_message({"role": "user", "content": "delegate the work"})

    engine = get_engine(config.db_uri)
    launch_task(engine, task_id="task-1", owner_session=SESSION_ID)

    llm = MultiTurnLLM(
        [[content_chunk("Delegated — waiting."), usage_chunk(10)]]
    )
    gen = react_loop(
        conn=FakeConn(),
        config=config,
        client_capabilities=None,
        turn_id="turn-1",
        mcp_clients={},
        llm=llm,
        tools=[],
        sessions={AGENT_ID: session},
        agent_id=AGENT_ID,
        state_accumulators={},
        logger=logger,
        hooks=[],
    )
    drive_task = asyncio.create_task(drive_react_loop(gen))
    await wait_until(lambda: len(llm.create_kwargs) == 1)
    await asyncio.sleep(0.05)  # let the loop settle into the hold
    drive_task.cancel()
    events, stop = await drive_task
    assert stop == "cancelled", events

    # Cancel did NOT propagate: the subagent's task is still running.
    assert get_task(engine, "task-1").status == "running"

    # The child finishes after the cancel. Its reply lands in the mailbox
    # and STAYS there — nothing self-wakes the session.
    finish_task(
        engine,
        "task-1",
        result="42",
        content="[task-1: subagent shy-fox finished]\n42",
    )
    await asyncio.sleep(0.1)
    assert len(pending_deliveries(engine, SESSION_ID)) == 1

    # RESUME: the user's next prompt drains the queue before the first
    # model call — a reply enters the session only via a user prompt.
    await session.add_message({"role": "user", "content": "continue"})
    llm2 = MultiTurnLLM(
        [[content_chunk("Resumed; the subagent returned 42."), usage_chunk(10)]]
    )
    events2, stop2 = await _run_loop(config, session, llm2)
    assert stop2 == "done", events2

    first_user_texts = [
        str(m.get("content"))
        for m in llm2.create_kwargs[0]["messages"]
        if m["role"] == "user"
    ]
    assert any("task-1" in t for t in first_user_texts), first_user_texts
    assert pending_deliveries(engine, SESSION_ID) == []
    await session.close()


async def test_hold_releases_when_task_stops_without_delivery(
    tmp_path, monkeypatch
):
    """Defensive exit: if the task stops being running without ever
    producing a delivery (e.g. cancelled via task(CancelTurn) by another
    round), the hold releases and the turn ends instead of waiting
    forever."""
    monkeypatch.setattr(react_mod, "DELIVERY_POLL_S", 0.01)

    config, session = await make_test_session(tmp_path)
    await session.add_message({"role": "user", "content": "delegate the work"})

    engine = get_engine(config.db_uri)
    launch_task(engine, task_id="task-1", owner_session=SESSION_ID)

    async def child_cancelled():
        await asyncio.sleep(0.05)
        cancel_task(engine, "task-1")

    llm = MultiTurnLLM(
        [[content_chunk("Delegated — waiting."), usage_chunk(10)]]
    )
    canceller = asyncio.create_task(child_cancelled())
    events, stop = await _run_loop(config, session, llm)
    await canceller
    assert stop == "done", events

    # One model round only — nothing was injected, nothing to react to.
    assert len(llm.create_kwargs) == 1
    assert pending_deliveries(engine, SESSION_ID) == []
    await session.close()
