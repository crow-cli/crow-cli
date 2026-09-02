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
from textual.widget import Widget
from textual.widgets import Button

from crow_cli.tui import messages
from crow_cli.tui.app import CrowApp
from crow_cli.tui.widgets.conversation import Conversation, Loading
from crow_cli.tui.widgets.prompt import CancelTurn
from crow_cli.tui.widgets.terminal import Terminal

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


async def _one_escape_cancels(
    agent_data: dict, log_path: Path, label: str, tmp_path: Path
) -> None:
    """One Escape, mid-stream, must cancel — and do it now.

    The original failure: key events were never processed while the stream ran,
    so `session/cancel` was never sent and the UI stayed locked.
    """
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
            f"\n--- cancel under {label} ---\n"
            f"stream fragments consumed: {streamed}\n"
            f"session/cancel reached agent in {cancel_latency * 1000:.0f} ms\n"
            f"UI unlocked {(cancel_latency + unlock_latency) * 1000:.0f} ms after keypress"
        )


async def test_escape_cancels_immediately_under_600_tps(
    blast_agent, tmp_path: Path
) -> None:
    """A realistic fast endpoint (600 tokens/sec): one Escape cancels."""
    agent_data, log_path = blast_agent
    await _one_escape_cancels(agent_data, log_path, "600 tokens/sec", tmp_path)


async def test_escape_cancels_immediately_when_unthrottled(
    flood_agent, tmp_path: Path
) -> None:
    """Stress variant: nothing paces the agent, the pump is saturated flat out.

    600 tokens/sec is survivable; an unthrottled stream is what a local model,
    or a pipe nobody rate-limits, actually produces.
    """
    agent_data, log_path = flood_agent
    await _one_escape_cancels(agent_data, log_path, "unthrottled flood", tmp_path)


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


def _cancel_button(conversation: Conversation) -> Button:
    return conversation.prompt.query_one("#cancel-button", Button)


def _on_screen(widget: Widget) -> bool:
    """Is the widget actually painted, with real geometry?

    This Textual has no `Widget.displayed`; a hidden widget drops out of the
    compositor, so an empty region is the honest answer for "not on screen".
    """
    return widget.styles.display != "none" and widget.region.area > 0


async def test_cancel_button_appears_only_while_streaming(
    blast_agent, tmp_path: Path
) -> None:
    """The mouse path exists while the agent works and costs nothing when idle.

    It is the only control a saturated keyboard leaves the user, so it has to be
    on screen during a stream — and one line tall, or it reshapes the prompt.
    """
    agent_data, _ = blast_agent
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    app = CrowApp(agent_data=agent_data, project_dir=str(project_dir))

    async with app.run_test(size=(120, 40)):
        conversation = await ready_conversation(app)
        button = _cancel_button(conversation)
        container = conversation.prompt.query_one("#prompt-container")

        assert not _on_screen(button), "Cancel is offered while nothing is running"
        idle_height = container.region.height

        await _start_stream(app, conversation)
        await wait_until(lambda: _on_screen(button), timeout=5)
        streaming_height = container.region.height

        assert button.region.height == 1, (
            f"Cancel button is {button.region.height} lines tall; the prompt "
            "row must not grow when a turn starts"
        )
        assert streaming_height == idle_height, (
            "prompt row changed height when the Cancel button appeared"
        )

        # And it goes away with the turn.
        press_key(app, "escape")
        await wait_until(lambda: conversation.turn == "client", timeout=CANCEL_DEADLINE)
        await wait_until(lambda: not _on_screen(button), timeout=5)


async def test_clicking_cancel_stops_a_600_tps_stream(
    blast_agent, tmp_path: Path
) -> None:
    """Clicking Cancel is as immediate as Escape under the same load."""
    agent_data, log_path = blast_agent
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    app = CrowApp(agent_data=agent_data, project_dir=str(project_dir))

    async with app.run_test(size=(120, 40)):
        conversation = await ready_conversation(app)
        fragments = _count_stream_fragments(conversation)
        button = _cancel_button(conversation)

        await _start_stream(app, conversation)
        await asyncio.sleep(1.5)
        assert fragments() > 0, "mock agent produced no stream; nothing to reproduce"
        assert _on_screen(button), "Cancel was not clickable during the stream"

        # The sanctioned way to drive a button; it refuses to post if the button
        # is hidden, so this is a real click on a real (visible) control.
        button.press()

        try:
            cancel_latency = await wait_until(
                lambda: _cancel_reached(log_path), timeout=CANCEL_DEADLINE
            )
            unlock_latency = await wait_until(
                lambda: conversation.turn == "client", timeout=CANCEL_DEADLINE
            )
        except (asyncio.TimeoutError, TimeoutError) as error:
            raise AssertionError(
                f"clicking Cancel did not stop a 600 tokens/sec stream within "
                f"{CANCEL_DEADLINE}s ({fragments()} fragments consumed)"
            ) from error

        print(
            "\n--- cancel by click under 600 tokens/sec ---\n"
            f"session/cancel reached agent in {cancel_latency * 1000:.0f} ms\n"
            f"UI unlocked {(cancel_latency + unlock_latency) * 1000:.0f} ms after click"
        )


async def test_cancelling_an_idle_agent_cannot_poison_the_next_turn(
    blast_agent, tmp_path: Path
) -> None:
    """A stray Cancel click must not leave the client in a dropping state.

    `session/update` traffic is discarded while `_cancelling` is raised. If that
    flag could be raised with no turn in flight — a double click, a click after
    the answer landed — the *next* prompt would stream into the void.
    """
    agent_data, _ = blast_agent
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    app = CrowApp(agent_data=agent_data, project_dir=str(project_dir))

    async with app.run_test(size=(120, 40)):
        conversation = await ready_conversation(app)
        agent = conversation.agent
        assert agent is not None

        assert conversation.prompt.turn is None
        conversation.post_message(CancelTurn())
        await asyncio.sleep(0.2)

        assert agent.begin_cancel() is False, "idle agent accepted a cancel"
        assert agent._cancelling is False, "cancel poisoned an idle client"
        assert conversation.turn != "agent"


async def test_reprompting_immediately_after_cancel_is_clean(
    blast_agent, tmp_path: Path
) -> None:
    """Cancel, then fire the next prompt without waiting — what cancel is for.

    Two turns are briefly in flight at once (the cancelled one has yet to answer
    `session/prompt`). Neither the client's render flags nor the previous turn's
    deferred widget cleanup may touch the turn that replaced it.
    """
    agent_data, log_path = blast_agent
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    app = CrowApp(agent_data=agent_data, project_dir=str(project_dir))

    async with app.run_test(size=(120, 40)):
        conversation = await ready_conversation(app)
        agent = conversation.agent
        fragments = _count_stream_fragments(conversation)

        await _start_stream(app, conversation)
        await asyncio.sleep(0.5)

        press_key(app, "escape")
        # Deliberately no pause: the new prompt races the deferred cleanup of
        # the cancelled turn.
        conversation.post_message(messages.UserInputSubmitted(body="and again"))
        await wait_until(lambda: conversation.turn == "agent", timeout=10)

        assert agent is not None and agent._turn_open, "second turn never opened"
        assert agent._cancelling is False, (
            "the cancelled turn left the client dropping updates"
        )
        loading = conversation._loading
        assert loading is not None and loading.is_mounted, (
            "the new turn's loading indicator was swept away by cleanup of the "
            "cancelled turn"
        )

        before = fragments()
        await asyncio.sleep(1.0)
        assert fragments() > before, "second turn streamed nothing to the UI"

        press_key(app, "escape")
        await wait_until(lambda: conversation.turn == "client", timeout=CANCEL_DEADLINE)
        # Nothing from either cancelled turn is left spinning on screen.
        await wait_until(lambda: not list(conversation.query(Loading)), timeout=5)


async def test_cancel_does_not_wait_for_an_uncooperative_agent(
    wedged_agent, tmp_path: Path
) -> None:
    """An agent that ignores `session/cancel` must not hold the UI hostage.

    Cancellation is a client-side decision: unlock on our clock and stop
    rendering the corpse, whatever the agent decides to do about it.
    """
    agent_data, log_path = wedged_agent
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    app = CrowApp(agent_data=agent_data, project_dir=str(project_dir))

    async with app.run_test(size=(120, 40)):
        conversation = await ready_conversation(app)
        agent = conversation.agent
        fragments = _count_stream_fragments(conversation)

        await _start_stream(app, conversation)
        await asyncio.sleep(1.0)
        assert fragments() > 0, "wedged agent produced no stream"

        press_key(app, "escape")
        unlock_latency = await wait_until(
            lambda: conversation.turn == "client", timeout=CANCEL_DEADLINE
        )
        assert _cancel_reached(log_path), "session/cancel never reached the agent"
        assert agent is not None and agent._cancelling, "not dropping the dead turn"

        # The agent keeps streaming; none of it may reach the transcript.
        frozen = fragments()
        await asyncio.sleep(1.0)
        assert fragments() == frozen, (
            "a cancelled turn kept rendering after the agent ignored the cancel"
        )
        print(
            "\n--- cancel against a wedged agent ---\n"
            f"UI unlocked {unlock_latency * 1000:.0f} ms after keypress, "
            f"agent still streaming, transcript frozen at {frozen} fragments"
        )


async def test_escape_belongs_to_a_focused_terminal_during_a_stream(
    blast_agent, tmp_path: Path
) -> None:
    """A priority binding must not eat the terminal's own Escape.

    Tapping escape twice is how you leave an embedded terminal. The cancel
    binding has priority precisely so it survives a saturated pump, so focus has
    to decide who gets the key — and the mouse keeps a way out either way.
    """
    agent_data, log_path = blast_agent
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    app = CrowApp(agent_data=agent_data, project_dir=str(project_dir))

    async with app.run_test(size=(120, 40)):
        conversation = await ready_conversation(app)

        await _start_stream(app, conversation)
        await asyncio.sleep(0.5)
        assert conversation.turn == "agent"

        # The user focuses a terminal while the agent is mid-stream.
        terminal = Terminal("escape-owning")
        await conversation.contents.mount(terminal)
        terminal.focus()
        await wait_until(lambda: terminal.has_focus, timeout=5)

        press_key(app, "escape")
        await asyncio.sleep(0.1)
        # Tap again inside the terminal's escape window (400ms): two taps leave
        # the terminal, which only happens if it owns the key.
        press_key(app, "escape")
        await wait_until(lambda: not terminal.has_focus, timeout=2)

        assert conversation.turn == "agent", (
            "cancel stole Escape from the focused terminal"
        )
        assert not _cancel_reached(log_path), (
            "session/cancel went out while a terminal had focus"
        )

        # The mouse path is unaffected by who owns the keyboard.
        _cancel_button(conversation).press()
        await wait_until(lambda: conversation.turn == "client", timeout=CANCEL_DEADLINE)
