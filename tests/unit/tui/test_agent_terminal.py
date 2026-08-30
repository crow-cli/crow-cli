"""Tests for the headless agent terminal (the ACP terminal tool path).

This path is deliberately separate from the human-facing terminal
emulator: PTY + raw byte capture only. These tests pin the tool
contract: spawn, capture, exit status, kill, release, byte limit.
"""

import asyncio
import os
from pathlib import Path

import pytest

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen

import crow_cli.tui as tui
from crow_cli.tui.acp.messages import CreateTerminal
from crow_cli.tui.agent_terminal import AgentTerminal
from crow_cli.tui.app import CrowApp
from crow_cli.tui.widgets.conversation import Conversation
from crow_cli.tui.widgets.terminal_tool import Command


def make_command(command: str, args: list[str], cwd: str = "/tmp") -> Command:
    return Command(command, args, dict(os.environ), cwd)


async def test_captures_output_and_exit_code() -> None:
    terminal = AgentTerminal(
        make_command("bash", ["-c", "echo hello-agent; date"])
    )
    await terminal.start()
    return_code, signal = await terminal.wait_for_exit()
    assert return_code == 0
    assert signal is None
    state = terminal.tool_state
    assert "hello-agent" in state.output
    assert state.return_code == 0
    assert not state.truncated


async def test_output_listeners_receive_decoded_chunks() -> None:
    terminal = AgentTerminal(make_command("bash", ["-c", "echo mirror-me"]))
    received: list[str] = []

    async def listener(text: str) -> None:
        received.append(text)

    terminal.add_output_listener(listener)
    await terminal.start()
    await terminal.wait_for_exit()
    await asyncio.sleep(0.1)  # listener tasks are fire-and-forget
    assert "mirror-me" in "".join(received)


async def test_exit_listener_sees_return_code() -> None:
    terminal = AgentTerminal(make_command("bash", ["-c", "exit 3"]))
    exits: list[int | None] = []

    async def listener(return_code: int | None) -> None:
        exits.append(return_code)

    terminal.add_exit_listener(listener)
    await terminal.start()
    await terminal.wait_for_exit()
    assert exits == [3]
    assert terminal.tool_state.return_code == 3


async def test_kill_stops_a_long_running_process() -> None:
    terminal = AgentTerminal(make_command("sleep", ["30"]))
    await terminal.start()
    assert terminal.kill()
    return_code, _ = await terminal.wait_for_exit()
    assert return_code != 0
    # Killing again is a no-op once exited
    assert not terminal.kill()


async def test_output_byte_limit_truncates() -> None:
    terminal = AgentTerminal(
        make_command("bash", ["-c", "yes x | head -c 10000"]),
        output_byte_limit=1000,
    )
    await terminal.start()
    await terminal.wait_for_exit()
    state = terminal.tool_state
    assert state.truncated
    assert len(state.output) <= 1000


async def test_release_marks_terminal_unusable() -> None:
    terminal = AgentTerminal(make_command("true", []))
    await terminal.start()
    await terminal.wait_for_exit()
    assert not terminal.released
    terminal.release()
    assert terminal.released


async def test_spawn_failure_raises() -> None:
    terminal = AgentTerminal(
        make_command("true", [], cwd="/nonexistent-directory-xyz")
    )
    with pytest.raises(Exception):
        await terminal.start()
    # wait_for_exit still resolves (the guarded run completed)
    await terminal.wait_for_exit()


class SuspendedConversationApp(CrowApp):
    """CrowApp hosting a Conversation that is hidden (window size 0) —
    the situation when the user is on another screen (e.g. the editor)."""

    # Textual resolves CSS_PATH relative to the subclass module — re-pin it.
    CSS_PATH = str(Path(tui.__file__).parent / "tui.tcss")

    def __init__(self, project_path: Path) -> None:
        super().__init__(project_dir=str(project_path), mode="store")
        self.conversation = Conversation(project_path)


class _HostScreen(Screen):
    def __init__(self, conversation: Conversation) -> None:
        super().__init__()
        self._conversation = conversation

    def compose(self) -> ComposeResult:
        with Vertical(id="body"):
            yield self._conversation


async def test_terminal_created_while_conversation_suspended(
    tmp_path: Path,
) -> None:
    """Regression: terminal/create while the conversation window is
    suspended (user on another screen, window size 0). The old widget
    path sized the PTY from that 0 window -> negative width -> struct.pack
    raised in spawn -> the run loop died and the agent saw empty output.
    The headless path sizes from an explicit clamped width instead.
    """
    app = SuspendedConversationApp(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await app.push_screen(_HostScreen(app.conversation))
        await pilot.pause()
        conversation = app.conversation
        conversation.display = False  # suspended: user is elsewhere
        await pilot.pause()
        assert conversation.window.size.width == 0

        future: asyncio.Future[bool] = asyncio.Future()
        conversation.post_message(
            CreateTerminal(
                "terminal-1",
                command="bash",
                result_future=future,
                args=["-c", "echo hello-agent"],
                cwd=str(tmp_path),
            )
        )
        await asyncio.wait_for(future, 10)
        assert future.result() is True

        terminal = conversation.get_terminal("terminal-1")
        assert terminal is not None
        return_code, _ = await asyncio.wait_for(terminal.wait_for_exit(), 10)
        assert return_code == 0
        assert "hello-agent" in terminal.tool_state.output
