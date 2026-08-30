"""Headless tests for the pass-through EditorTerminal widget."""

import asyncio
import os
from pathlib import Path

from textual.app import App, ComposeResult

from crow_cli.tui.widgets.editor_terminal import Command, EditorTerminal


class EditorApp(App):
    def __init__(self, command: Command) -> None:
        super().__init__()
        self._command = command
        self.exited: asyncio.Event = asyncio.Event()
        self.exit_code: int | None = None

    def compose(self) -> ComposeResult:
        yield EditorTerminal(self._command)

    async def on_mount(self) -> None:
        terminal = self.query_one(EditorTerminal)
        await terminal.start(80, 24)
        terminal.focus()

    def on_editor_terminal_exited(self, event: EditorTerminal.Exited) -> None:
        self.exit_code = event.return_code
        self.exited.set()


async def wait_flag(flag: asyncio.Event, timeout: float = 10.0) -> None:
    await asyncio.wait_for(flag.wait(), timeout)


async def test_output_lands_in_buffer(tmp_path: Path) -> None:
    """Program output is rendered into the terminal buffer."""
    command = Command("printf", ["hello-from-pty\n"], dict(os.environ), str(tmp_path))
    app = EditorApp(command)
    async with app.run_test(size=(80, 24)) as pilot:
        await wait_flag(app.exited)
        terminal = app.query_one(EditorTerminal)
        text = "\n".join(
            line.content.plain for line in terminal.state.scrollback_buffer.lines
        )
        assert "hello-from-pty" in text
        assert app.exit_code == 0


async def test_keys_and_escape_reach_stdin(tmp_path: Path) -> None:
    """Typed keys — including escape — are forwarded verbatim to the process."""
    out_file = tmp_path / "stdin.txt"
    command = Command("sh", ["-c", f"cat > {out_file}"], dict(os.environ), str(tmp_path))
    app = EditorApp(command)
    async with app.run_test(size=(80, 24)) as pilot:
        terminal = app.query_one(EditorTerminal)
        for _ in range(100):
            if terminal._shell_fd is not None:
                break
            await pilot.pause(0.05)
        assert terminal._shell_fd is not None

        await pilot.press("h", "i", "escape")
        await pilot.pause(0.3)
        # Canonical PTY: newline completes the line, then ctrl+d at line
        # start signals EOF -> cat exits.
        await pilot.press("enter")
        await pilot.press("ctrl+d")
        await wait_flag(app.exited)

    assert out_file.read_bytes() == b"hi\x1b\n"


async def test_update_size_resizes_pty(tmp_path: Path) -> None:
    """Resizing the widget resizes the PTY (helix redraw dependency)."""
    import fcntl
    import struct
    import termios

    command = Command("cat", [], dict(os.environ), str(tmp_path))
    app = EditorApp(command)
    async with app.run_test(size=(80, 24)) as pilot:
        terminal = app.query_one(EditorTerminal)
        for _ in range(100):
            if terminal._shell_fd is not None:
                break
            await pilot.pause(0.05)
        terminal.update_size(101, 31)
        packed = fcntl.ioctl(terminal._shell_fd, termios.TIOCGWINSZ, b"\x00" * 8)
        rows, cols = struct.unpack("HHHH", packed)[:2]
        assert (cols, rows) == (101, 31)
        # EOF at start of line -> cat exits naturally (kill() only signals the
        # `sh -c` wrapper, not its child; process-group kill is tracked separately).
        await pilot.press("ctrl+d")
        await wait_flag(app.exited)
