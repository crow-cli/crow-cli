"""Toy: a real terminal (helix) embedded in a column of a Textual TUI.

The point is to learn whether in-TUI terminal embedding is worth keeping
in crow-cli (vs. the rio-new-tab fallback) — so this is deliberately the
thinnest faithful version: pyte screen + PTY, grid render, key forwarding,
real resize semantics (screen.resize + TIOCSWINSZ, no folding, no wipes).

Run:  cd sandbox/textual-term-toy && uv --project . run toy.py [file]
"""

from __future__ import annotations

import asyncio
import fcntl
import os
import signal
import struct
import sys
import termios
from pathlib import Path

import pyte
from rich.segment import Segment
from rich.style import Style
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Static

NAMED_COLORS = {
    "black": "black",
    "red": "red",
    "green": "green",
    "brown": "yellow",
    "yellow": "yellow",
    "blue": "blue",
    "magenta": "magenta",
    "cyan": "cyan",
    "white": "white",
    "brightblack": "bright_black",
    "brightred": "bright_red",
    "brightgreen": "bright_green",
    "brightbrown": "bright_yellow",
    "brightyellow": "bright_yellow",
    "brightblue": "bright_blue",
    "brightmagenta": "bright_magenta",
    "brightcyan": "bright_cyan",
    "brightwhite": "bright_white",
}

KEY_SEQUENCES = {
    "up": b"\x1b[A",
    "down": b"\x1b[B",
    "right": b"\x1b[C",
    "left": b"\x1b[D",
    "home": b"\x1b[H",
    "end": b"\x1b[F",
    "pageup": b"\x1b[5~",
    "pagedown": b"\x1b[6~",
    "delete": b"\x1b[3~",
    "insert": b"\x1b[2~",
    "enter": b"\r",
    "tab": b"\t",
    "escape": b"\x1b",
    "backspace": b"\x7f",
    "f1": b"\x1bOP",
    "f2": b"\x1bOQ",
    "f3": b"\x1bOR",
    "f4": b"\x1bOS",
}


def _rich_color(pyte_color: str) -> str | None:
    # pyte color values are "default", ANSI names, or 6-char hex strings
    # (both 256-color via FG_BG_256 and 24-bit truecolor).
    if pyte_color == "default" or not pyte_color:
        return None
    if pyte_color in NAMED_COLORS:
        return NAMED_COLORS[pyte_color]
    if len(pyte_color) == 6:
        return f"#{pyte_color}"
    return None


def _style_for(char: pyte.screens.Char) -> Style:
    fg = _rich_color(char.fg)
    bg = _rich_color(char.bg)
    if char.reverse:
        fg, bg = bg, fg
    return Style(
        color=fg,
        bgcolor=bg,
        bold=char.bold or None,
        italic=char.italics or None,
        underline=char.underscore or None,
        strike=char.strikethrough or None,
    )


class PyteTerminal(Widget, can_focus=True):
    """A pyte-backed terminal widget: PTY in, grid out."""

    DEFAULT_CSS = """
    PyteTerminal {
        width: 1fr;
        height: 1fr;
    }
    """

    def __init__(self, command: list[str], cwd: str) -> None:
        super().__init__()
        self._command = command
        self._cwd = cwd
        self._master_fd: int | None = None
        self._pid: int | None = None
        self.pyte_screen = pyte.Screen(80, 24)
        self.pyte_stream = pyte.ByteStream(self.pyte_screen)

    # ---- PTY lifecycle -------------------------------------------------

    def _resize_pty_fd(self, fd: int, cols: int, rows: int) -> None:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def _resize_pty(self, cols: int, rows: int) -> None:
        if self._master_fd is not None:
            self._resize_pty_fd(self._master_fd, cols, rows)

    def on_mount(self) -> None:
        cols = max(2, self.size.width)
        rows = max(2, self.size.height)
        self.pyte_screen.resize(rows, cols)

        master_fd, slave_fd = os.openpty()
        self._resize_pty_fd(slave_fd, cols, rows)

        pid = os.fork()
        if pid == 0:  # child: become the terminal's program
            os.close(master_fd)
            os.setsid()
            fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)
            os.chdir(self._cwd)
            os.execvp(self._command[0], self._command)

        os.close(slave_fd)
        self._pid = pid
        self._master_fd = master_fd
        os.set_blocking(master_fd, False)
        asyncio.get_running_loop().add_reader(master_fd, self._on_pty_readable)

    def _on_pty_readable(self) -> None:
        assert self._master_fd is not None
        try:
            while True:
                try:
                    chunk = os.read(self._master_fd, 65536)
                except BlockingIOError:
                    break
                if not chunk:
                    break
                self.pyte_stream.feed(chunk)
                self.refresh()
        except OSError:
            self._teardown_reader()

    def _teardown_reader(self) -> None:
        if self._master_fd is not None:
            try:
                asyncio.get_running_loop().remove_reader(self._master_fd)
            except Exception:
                pass
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None

    def on_unmount(self) -> None:
        self._teardown_reader()
        if self._pid is not None:
            try:
                os.killpg(os.getpgid(self._pid), signal.SIGHUP)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            self._pid = None

    # ---- resize ---------------------------------------------------------

    def on_resize(self, event: events.Resize) -> None:
        cols = max(2, event.size.width)
        rows = max(2, event.size.height)
        if cols == self.pyte_screen.columns and rows == self.pyte_screen.lines:
            return
        self.pyte_screen.resize(rows, cols)
        self._resize_pty(cols, rows)
        self.refresh()

    # ---- input ----------------------------------------------------------

    def on_key(self, event: events.Key) -> None:
        if self._master_fd is None:
            return
        data: bytes | None = None
        key = event.key
        if key in KEY_SEQUENCES:
            data = KEY_SEQUENCES[key]
        elif key.startswith("ctrl+") and len(key) == 6:
            letter = key[5]
            if "a" <= letter <= "z":
                data = bytes([ord(letter) - 96])
        elif event.character:
            data = event.character.encode("utf-8")
        if data:
            os.write(self._master_fd, data)
            event.stop()
            event.prevent_default()

    # ---- render ---------------------------------------------------------

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        if y >= self.pyte_screen.lines:
            return Strip.blank(width)
        row = self.pyte_screen.buffer[y]
        segments: list[Segment] = []
        text_parts: list[str] = []
        current_style: Style | None = None
        for x in range(min(self.pyte_screen.columns, width)):
            char = row[x]
            style = _style_for(char)
            if style != current_style and text_parts:
                segments.append(Segment("".join(text_parts), current_style))
                text_parts = []
            current_style = style
            text_parts.append(char.data if char.data else " ")
        if text_parts:
            segments.append(Segment("".join(text_parts), current_style))
        return Strip(segments).crop_extend(0, width, None)


SAMPLE = Path(__file__).parent / "sample.md"


class ToyApp(App):
    """Sidebar + column with a live terminal — the crow-cli editor-tab shape."""

    CSS = """
    #frame {
        width: 1fr;
        height: 1fr;
    }
    #sidebar {
        width: 34;
        border-right: thick $accent;
        padding: 1 2;
    }
    #sidebar .title {
        text-style: bold;
        color: $accent;
    }
    #column {
        width: 1fr;
        max-width: 100;
        background: black 7%;
        padding-left: 1;
    }
    #tabbar {
        height: 1;
        background: $boost;
        color: $text;
        padding: 0 1;
    }
    """

    BINDINGS = [("ctrl+q", "quit", "Quit")]

    def __init__(self, target: Path) -> None:
        super().__init__()
        self.target = target

    def compose(self) -> ComposeResult:
        with Horizontal(id="frame"):
            with Vertical(id="sidebar"):
                yield Static("[b]TOY[/b] — terminal in a column", classes="title")
                yield Static("")
                yield Static("pyte screen + real PTY")
                yield Static("resize = screen.resize + TIOCSWINSZ")
                yield Static("no folding, no wipes")
                yield Static("")
                yield Static(f"file: {self.target.name}")
                yield Static("[dim]ctrl+q quits[/dim]")
            with Vertical(id="column"):
                yield Static(f"hx {self.target.name}", id="tabbar")
                yield PyteTerminal(["hx", str(self.target)], cwd=str(Path.cwd()))

    def on_mount(self) -> None:
        self.query_one(PyteTerminal).focus()


def main() -> None:
    if not SAMPLE.exists():
        SAMPLE.write_text(
            "# sample\n\n"
            + "\n".join(
                f"line {i:03d} lorem ipsum dolor sit amet" for i in range(1, 201)
            )
            + "\n"
        )
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else SAMPLE
    ToyApp(target.resolve()).run()


if __name__ == "__main__":
    main()
