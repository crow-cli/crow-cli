"""Headless tests for EditorScreen: editor session tabs hosted by the real CrowApp.

The app boots on the ``store`` screen so no chat session (and therefore no
agent connection) is created — the editor tab flow is independent of ACP.
"""

import asyncio
import os
import stat
from pathlib import Path

import pytest

from textual import on

import crow_cli.tui as tui
from crow_cli.tui.app import CrowApp
from crow_cli.tui.screens.editor import EditorScreen
from crow_cli.tui.widgets.editor_terminal import Command, EditorTerminal
from crow_cli.tui.widgets.session_tabs import SessionLabel, SessionsTabs


async def wait_until(condition, timeout: float = 10.0, interval: float = 0.05) -> None:
    async def _poll() -> None:
        while not condition():
            await asyncio.sleep(interval)

    await asyncio.wait_for(_poll(), timeout)


class EditorTestApp(CrowApp):
    """A CrowApp that records Exited events bubbling up from editor tabs."""

    # Textual resolves CSS_PATH relative to the subclass module — re-pin it.
    CSS_PATH = str(Path(tui.__file__).parent / "tui.tcss")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.exited_events: list[EditorTerminal.Exited] = []

    @on(EditorTerminal.Exited)
    def record_exited(self, event: EditorTerminal.Exited) -> None:
        self.exited_events.append(event)


def make_app(tmp_path: Path) -> CrowApp:
    return EditorTestApp(project_dir=str(tmp_path), mode="store")


async def test_open_file_in_editor_creates_editor_tab(tmp_path: Path) -> None:
    """Opening a file spawns an editor-kind session tab running the command."""
    target = tmp_path / "hello.txt"
    target.write_text("hi\n")
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        app.settings.set("editor.command", "cat")  # stays alive until EOF
        await app.open_file_in_editor(target)

        sessions = list(app.session_tracker)
        assert len(sessions) == 1
        assert sessions[0].kind == "editor"
        assert sessions[0].title == f"cat {target.name}"
        assert isinstance(app.screen, EditorScreen)

        terminal = app.screen.terminal
        await wait_until(lambda: terminal._shell_fd is not None)
        assert terminal.return_code is None
        await wait_until(lambda: terminal.has_focus)

        # EOF exits cat -> the tab closes itself -> back to the store.
        await pilot.press("ctrl+d")
        await wait_until(lambda: app.session_tracker.session_count == 0)
        assert app.current_mode == "store"


def _stay_alive_editor(tmp_path: Path) -> Path:
    """A fake editor that stays open (cat exits at once -> Exited ->
    SessionClose pops the screen under the test's feet)."""
    fake_editor = tmp_path / "fake_editor.sh"
    fake_editor.write_text("#!/bin/sh\nread -r line || true\n")
    fake_editor.chmod(fake_editor.stat().st_mode | stat.S_IEXEC)
    return fake_editor


async def test_editor_tab_is_the_same_page_as_chat(tmp_path: Path) -> None:
    """The tab bar lives INSIDE the column (right of the sidebar), exactly
    like SessionsTabs inside Conversation on the chat page."""
    target = tmp_path / "hello.txt"
    target.write_text("hi\n")
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        app.settings.set("editor.command", str(_stay_alive_editor(tmp_path)))
        await app.open_file_in_editor(target)
        screen = app.screen
        assert isinstance(screen, EditorScreen)

        await pilot.pause()
        body = screen.query_one("#editor-body")
        tabs = body.query_one(SessionsTabs)
        assert tabs.parent is body
        # The terminal shares the column with the tab bar
        terminal = screen.terminal
        assert terminal.parent is body

        # Column chrome mirrors Conversation.-column
        app.settings.set("ui.column", True)
        await pilot.pause()
        assert body.has_class("-column")
        assert body.styles.max_width is not None

        await pilot.press("ctrl+d")
        await wait_until(lambda: app.session_tracker.session_count == 0)


async def test_editor_column_toggle_off(tmp_path: Path) -> None:
    target = tmp_path / "hello.txt"
    target.write_text("hi\n")
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        app.settings.set("editor.command", str(_stay_alive_editor(tmp_path)))
        await app.open_file_in_editor(target)
        await pilot.pause()
        body = app.screen.query_one("#editor-body")
        app.settings.set("ui.column", True)
        await pilot.pause()
        assert body.has_class("-column")
        app.settings.set("ui.column", False)
        await pilot.pause()
        assert not body.has_class("-column")
        assert body.styles.max_width is None
        await pilot.press("ctrl+d")
        await wait_until(lambda: app.session_tracker.session_count == 0)


async def test_editor_tab_closes_when_process_exits(tmp_path: Path) -> None:
    """A fast-exiting editor process closes the tab without any key input."""
    target = tmp_path / "hello.txt"
    target.write_text("hi\n")
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 30)):
        command = Command("printf", [str(target)], dict(os.environ), str(tmp_path))
        screen = EditorScreen(command)
        details = await app.new_session_screen(
            lambda: screen, title="printf", kind="editor"
        )
        assert details.kind == "editor"

        # printf prints the path and exits 0; the tab must close by itself.
        # Wait for the Exited event at the app first — the close cascade
        # (SessionClose on the screen) races the app's own message queue.
        await wait_until(lambda: len(app.exited_events) == 1)
        assert app.exited_events[0].return_code == 0
        await wait_until(lambda: app.session_tracker.session_count == 0)
        assert app.current_mode == "store"


async def test_x_affordance_gracefully_closes_editor_tab(tmp_path: Path) -> None:
    """Clicking the trailing ``x`` on an editor tab sends ``:wq!\\r`` and the
    tab closes only once the editor process actually exits."""
    # A stand-in editor: swallow exactly one ``:wq!``-sized line, record what
    # it got, then quit cleanly — mimics helix writing and exiting on :wq!.
    received = tmp_path / "received.txt"
    fake_editor = tmp_path / "fake_editor.sh"
    fake_editor.write_text(
        "#!/bin/sh\n"
        "read -r line\n"
        f"printf '%s' \"$line\" > {received}\n"
        "exit 0\n"
    )
    fake_editor.chmod(fake_editor.stat().st_mode | stat.S_IEXEC)

    target = tmp_path / "hello.txt"
    target.write_text("hi\n")
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        command = Command(str(fake_editor), [], dict(os.environ), str(tmp_path))
        details = await app.new_session_screen(
            lambda: EditorScreen(command), title="fake", kind="editor"
        )
        mode = details.mode_name
        terminal = app.screen.terminal
        await wait_until(lambda: terminal._shell_fd is not None)
        assert terminal.return_code is None

        # The tab label ends with the close glyph; a click on that last cell
        # posts SessionRequestClose rather than switching tabs.
        label = app.screen.query_one(f"#{mode}", SessionLabel)
        await wait_until(lambda: label.content_region.width > 0)
        await pilot.click(label, offset=(label.content_region.width, 0))

        # Graceful: the app sent :wq! to the editor and waits for it to exit.
        await wait_until(lambda: terminal.return_code == 0)
        await wait_until(lambda: app.session_tracker.session_count == 0)
        assert app.current_mode == "store"
        assert received.read_text() == ":wq!"
