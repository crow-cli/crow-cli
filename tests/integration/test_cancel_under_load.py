"""Cancelling an agent while `session/update` traffic floods the TUI.

Regression cover for the bug where Escape did nothing during a fast stream: the
inbound torrent saturated Textual's single message pump, so key events were
never processed and `session/cancel` was never sent. The mock agent streams at
a realistic fast-endpoint rate (600 tokens/sec), which is what made the failure
visible in production.

Run directly:  pytest tests/integration/test_cancel_under_load.py -x -s
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Callable

from textual import events

from crow_cli.tui import messages
from crow_cli.tui.app import CrowApp
from crow_cli.tui.widgets.conversation import Conversation

CANCEL_DEADLINE = 1.0
"""Cancelling must take effect within this many seconds of the keypress."""


async def wait_until(
    condition: Callable[[], bool], timeout: float, interval: float = 0.02
) -> float:
    """Wait for a condition, returning how long it took.

    Polls on the event loop rather than via pilot.pause(), which waits for the
    message queue to drain and so times out under exactly the load modelled
    here.
    """
    started = time.monotonic()

    async def _poll() -> None:
        while not condition():
            await asyncio.sleep(interval)

    await asyncio.wait_for(_poll(), timeout)
    return time.monotonic() - started


def press_key(app: CrowApp, key: str) -> None:
    """Inject a key press without waiting for the screen to settle.

    The event travels the same focus chain as a real keypress; only the
    settle-wait that `pilot.press` performs is skipped, since under heavy load
    it never settles.
    """
    app.post_message(events.Key(key=key, character=None))


def _count_stream_fragments(conversation: Conversation) -> Callable[[], int]:
    """Count streamed fragments as the UI consumes them."""
    counter = {"n": 0}
    original = conversation.post_agent_response

    async def counted(fragment: str = ""):
        counter["n"] += 1
        return await original(fragment)

    conversation.post_agent_response = counted  # type: ignore[method-assign]
    return lambda: counter["n"]


async def ready_conversation(app: CrowApp, timeout: float = 30.0) -> Conversation:
    """The chat Conversation once it can take a prompt.

    ACP orders the handshake strictly (initialize -> session/new -> session/prompt),
    so submitting before the session id exists is not a state a real user hits.
    """

    def _find() -> Conversation | None:
        try:
            conversation = app.screen.query_one(Conversation)
        except Exception:
            return None
        agent = conversation.agent
        if not conversation.agent_ready or agent is None or not agent.session_id:
            return None
        return conversation

    await wait_until(lambda: _find() is not None, timeout)
    return _find()  # type: ignore[return-value]


def _cancel_reached(log_path: Path) -> bool:
    return log_path.exists() and "cancel RECEIVED" in log_path.read_text()


async def _start_stream(app: CrowApp, conversation: Conversation) -> None:
    conversation.post_message(messages.UserInputSubmitted(body="blast away"))
    await wait_until(lambda: conversation.turn == "agent", timeout=30)


async def test_escape_cancels_immediately_under_600_tps(blast_agent, tmp_path: Path) -> None:
    """One Escape cancels a turn streaming at 600 tokens/sec — immediately."""
    agent_data, log_path = blast_agent
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    app = CrowApp(agent_data=agent_data, project_dir=str(project_dir))

    async with app.run_test(size=(120, 40)):
        conversation = await ready_conversation(app)
        fragments = _count_stream_fragments(conversation)

        await _start_stream(app, conversation)
        await asyncio.sleep(1.5)
        streamed = fragments()
        assert streamed > 0, "mock agent produced no stream; nothing to reproduce"

        pressed = time.monotonic()
        press_key(app, "escape")

        try:
            cancel_latency = await wait_until(
                lambda: _cancel_reached(log_path), timeout=CANCEL_DEADLINE
            )
        except (asyncio.TimeoutError, TimeoutError) as error:
            raise AssertionError(
                f"session/cancel did not reach the agent within {CANCEL_DEADLINE}s "
                f"of Escape while streaming ({streamed} fragments consumed)"
            ) from error

        try:
            unlock_latency = await wait_until(
                lambda: conversation.turn == "client", timeout=CANCEL_DEADLINE
            )
        except (asyncio.TimeoutError, TimeoutError) as error:
            raise AssertionError(
                f"UI was still locked {CANCEL_DEADLINE}s after Escape cancelled a stream"
            ) from error

        print(
            "\n--- cancel under 600 tokens/sec ---\n"
            f"stream fragments consumed: {streamed}\n"
            f"session/cancel reached agent in {cancel_latency * 1000:.0f} ms\n"
            f"UI unlocked {unlock_latency * 1000 + cancel_latency * 1000:.0f} ms after keypress"
        )


async def test_stream_still_renders_at_600_tps(blast_agent, tmp_path: Path) -> None:
    """Cancelling stays responsive without starving the rendering itself."""
    agent_data, _ = blast_agent
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    app = CrowApp(agent_data=agent_data, project_dir=str(project_dir))

    async with app.run_test(size=(120, 40)):
        conversation = await ready_conversation(app)
        fragments = _count_stream_fragments(conversation)

        await _start_stream(app, conversation)
        started = time.monotonic()
        await asyncio.sleep(2.0)
        elapsed = time.monotonic() - started
        rendered = fragments()

        print(
            f"\n--- rendering under 600 tokens/sec ---\n"
            f"{rendered} render updates in {elapsed:.2f}s "
            f"({rendered / elapsed:.1f}/s), stream still running: "
            f"{conversation.turn == 'agent'}"
        )
        # The stream must keep reaching the UI — responsiveness cannot come from
        # simply dropping the transcript.
        assert rendered > 0, "nothing reached the UI while streaming"
        assert conversation.turn == "agent", "turn ended unexpectedly"
