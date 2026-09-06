"""The ACP agent's wire-log writer: a background task that has to die when it
is told to, and must not take the tail of the log with it.

The bug this pins: ``_log_writer`` wrapped its flush in
``suppress(asyncio.CancelledError, Exception)``, so a cancel that landed
inside a flush was eaten and the ``while True`` went back to sleep. asyncio's
loop shutdown (``_cancel_all_tasks``) cancels each task ONCE and then waits
for it, so one eaten cancel is a process that hangs forever on exit — which
is what froze tests/integration/test_cancel_under_load.py about one run in
six, and only under load: the flush window is as wide as the wire log is
busy, so a flood makes it hittable and an idle agent does not.

Nothing is stubbed. A real Agent is constructed against a real log file (no
subprocess is spawned until start()), and the writer runs for real.
"""

import asyncio
from pathlib import Path

import pytest

import crow_cli.tui.acp.agent as agent_mod
from crow_cli.tui.acp.agent import Agent

pytestmark = pytest.mark.asyncio


@pytest.fixture
def make_agent(tmp_path, monkeypatch):
    """Build a real Agent with its wire log pointed at tmp (CROW_LOG is read in
    __init__ and wins over paths.get_log()). No subprocess is spawned until
    start(), which these tests never call."""

    def _make(cls=Agent):
        monkeypatch.setenv("CROW_LOG", str(tmp_path / "wire.log"))
        return cls(tmp_path, {"name": "mock", "run_command": ["true"]}, None)

    return _make


def _lines(agent) -> list[str]:
    return Path(agent._log_file_path).read_text().splitlines()


class GatedAgent(Agent):
    """An Agent whose flush can be held open.

    Not a stub — the flush still really runs. The gate exists because the bug
    is a race: whether a cancel lands inside the ``suppress`` block or in the
    ``sleep`` before it decides everything, and aiming it by timing makes the
    test pass on the broken code about as often as it fails.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.in_flush = asyncio.Event()
        self.release = asyncio.Event()

    async def _flush_log(self) -> None:
        self.in_flush.set()
        await self.release.wait()
        await super()._flush_log()


async def test_the_writer_dies_when_cancelled_mid_flush(make_agent, monkeypatch):
    """Cancel ONCE while the writer is inside a flush, then wait — exactly what
    asyncio's _cancel_all_tasks does at loop shutdown, and exactly what hung.
    The eaten cancel sends the `while True` back to sleep, so the task is still
    alive two seconds later and the loop waits for it forever."""
    monkeypatch.setattr(agent_mod, "_LOG_FLUSH_INTERVAL", 0.0)
    agent = make_agent(GatedAgent)
    agent._log_buffer.append("x" * 100)

    writer = asyncio.create_task(agent._log_writer())
    await asyncio.wait_for(agent.in_flush.wait(), 2.0)

    writer.cancel()
    agent.release.set()
    done, _ = await asyncio.wait({writer}, timeout=2.0)

    assert writer in done, (
        "the log writer ate its cancellation and never finished — the loop's"
        " own shutdown waits for it forever"
    )
    assert writer.cancelled()


async def test_stop_cancels_the_writer_and_writes_the_tail(make_agent):
    """stop() owns the task: cancelling it without draining would guarantee
    losing the last 200ms of wire log, which is the part you want when an
    agent has just died."""
    agent = make_agent()
    agent._log_buffer.extend(["last line one", "last line two"])
    writer = asyncio.create_task(agent._log_writer())
    agent._log_task = writer
    await asyncio.sleep(0)  # let it reach its first sleep

    await agent.stop()

    assert agent._log_task is None
    assert writer.done()
    assert _lines(agent) == ["last line one", "last line two"]
    assert agent._log_buffer == []


async def test_the_drain_writes_the_whole_buffer(make_agent, monkeypatch):
    """_flush_log writes _LOG_WRITE_CHUNK lines a call, so one flush on the
    way out would leave most of a busy session's log behind."""
    monkeypatch.setattr(agent_mod, "_LOG_WRITE_CHUNK", 2)
    agent = make_agent()
    agent._log_buffer.extend(f"line {i}" for i in range(5))

    await agent._stop_log_writer()

    assert _lines(agent) == [f"line {i}" for i in range(5)]
    assert agent._log_buffer == []


async def test_stop_is_clean_when_nothing_was_started(make_agent):
    """stop() runs on every shutdown path, including an agent that never got
    as far as start() — there is no task to cancel and nothing to drain."""
    agent = make_agent()
    assert agent._log_task is None
    await agent.stop()
    assert agent._log_task is None
    assert not Path(agent._log_file_path).exists()

