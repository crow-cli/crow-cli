"""The quiescent delivery watcher — the out-of-loop half of the wake.

While a turn is ACTIVE the react loop consults state at its breakpoints
(prompt start, after each tool batch, end of turn). Once the session is
QUIESCENT nothing runs at all, so a per-session poller watches the
mailbox and wakes the session via _run_internal_round when a delivery
lands. These tests drive the watcher against a REAL sqlite mailbox with
a stubbed internal round.
"""

import asyncio

import pytest

from crow_cli.agent.main import AcpAgent
from crow_cli.config import Config
from crow_cli.memory.db import create_database, get_engine
from crow_cli.memory.reads import pending_deliveries
from crow_cli.memory.writes import finish_task, launch_task

SESSION = "watched-session"

pytestmark = pytest.mark.asyncio


def _agent(tmp_path, monkeypatch) -> AcpAgent:
    # Poll every 10ms instead of the production 2s.
    monkeypatch.setattr("crow_cli.agent.main.DELIVERY_POLL_S", 0.01)
    uri = f"sqlite:///{tmp_path / 'watcher.db'}"
    create_database(uri)
    config = Config(config_dir=tmp_path)
    config.db_uri = uri
    return AcpAgent(config=config)


def _land_delivery(uri: str, task_id: str = "task-1", content: str | None = None):
    engine = get_engine(uri)
    launch_task(engine, task_id=task_id, owner_session=SESSION)
    finish_task(
        engine,
        task_id,
        result="r",
        content=content or f"[{task_id}: subagent shy-fox finished]\nr",
    )
    return engine


async def _until(pred, timeout: float = 5.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if pred():
            return
        await asyncio.sleep(0.005)
    raise TimeoutError("condition never became true")


async def test_watcher_wakes_quiescent_session(tmp_path, monkeypatch):
    """Idle session + delivery in the mailbox -> one wake via
    _run_internal_round carrying the delivery content; mailbox drained."""
    agent = _agent(tmp_path, monkeypatch)
    engine = _land_delivery(agent._memory_db_uri)

    wakes: list[tuple[str, str]] = []

    async def fake_round(session_id: str, text: str) -> None:
        wakes.append((session_id, text))

    monkeypatch.setattr(agent, "_run_internal_round", fake_round)
    agent._ensure_delivery_watcher(SESSION)
    try:
        await _until(lambda: len(wakes) == 1)
    finally:
        for w in agent._delivery_watchers.values():
            w.cancel()

    assert wakes[0][0] == SESSION
    assert "task-1" in wakes[0][1]
    assert pending_deliveries(engine, SESSION) == []


async def test_watcher_skips_while_turn_active(tmp_path, monkeypatch):
    """While the session lock is held (a prompt or internal round is
    running) the watcher does NOTHING — the in-loop consults own that
    window. On release, the same delivery is picked up."""
    agent = _agent(tmp_path, monkeypatch)
    engine = _land_delivery(agent._memory_db_uri)

    wakes: list[tuple[str, str]] = []

    async def fake_round(session_id: str, text: str) -> None:
        wakes.append((session_id, text))

    monkeypatch.setattr(agent, "_run_internal_round", fake_round)
    lock = agent._session_locks.setdefault(SESSION, asyncio.Lock())
    agent._ensure_delivery_watcher(SESSION)
    try:
        async with lock:  # simulate an active turn
            await asyncio.sleep(0.1)  # ~10 poll intervals
            assert wakes == []
            # The delivery is still pending — NOT claimed mid-turn.
            assert len(pending_deliveries(engine, SESSION)) == 1
        await _until(lambda: len(wakes) == 1)
    finally:
        for w in agent._delivery_watchers.values():
            w.cancel()
    assert pending_deliveries(engine, SESSION) == []


async def test_ensure_is_idempotent(tmp_path, monkeypatch):
    agent = _agent(tmp_path, monkeypatch)
    agent._ensure_delivery_watcher(SESSION)
    first = agent._delivery_watchers[SESSION]
    agent._ensure_delivery_watcher(SESSION)
    try:
        assert agent._delivery_watchers[SESSION] is first
        assert len(agent._delivery_watchers) == 1
    finally:
        for w in agent._delivery_watchers.values():
            w.cancel()


async def test_watcher_claims_once_against_in_loop_consult(tmp_path, monkeypatch):
    """The watcher and the in-loop consult race for the same rows: the
    atomic claim means the wake content and the consult never both fire
    for the same delivery."""
    from crow_cli.memory.writes import claim_deliveries

    agent = _agent(tmp_path, monkeypatch)
    engine = _land_delivery(agent._memory_db_uri)

    # The in-loop consult wins the race.
    claimed = claim_deliveries(engine, SESSION)
    assert len(claimed) == 1

    wakes: list[tuple[str, str]] = []

    async def fake_round(session_id: str, text: str) -> None:
        wakes.append((session_id, text))

    monkeypatch.setattr(agent, "_run_internal_round", fake_round)
    agent._ensure_delivery_watcher(SESSION)
    try:
        await asyncio.sleep(0.1)  # plenty of poll intervals
    finally:
        for w in agent._delivery_watchers.values():
            w.cancel()
    assert wakes == []  # nothing left to deliver -> no wake
