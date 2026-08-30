"""A pass-through interactive terminal for running a fullscreen TUI (e.g. helix).

Unlike :class:`TerminalTool` (an ACP tool-call result framed with a border and
success/error styling), an ``EditorTerminal`` is a bare terminal emulator that
fills its tab and forwards every key — including ``escape`` — straight to the
underlying process. It is the body of an *editor* session tab.
"""

from __future__ import annotations

from contextlib import suppress

from textual import events
from textual.message import Message

from crow_cli.tui.widgets.terminal_tool import TerminalTool, Command


class EditorTerminal(TerminalTool):
    """A fullscreen, pass-through terminal running a single program.

    Args:
        command: The command to run (e.g. ``hx <path>``).
    """

    DEFAULT_CSS = """
    EditorTerminal {
        width: 100%;
        height: 1fr;
        border: none;
        overflow: hidden;
        background: $background;
    }
    """

    class Exited(Message):
        """Posted when the wrapped process exits."""

        def __init__(self, terminal: "EditorTerminal", return_code: int | None) -> None:
            self.terminal = terminal
            self.return_code = return_code
            super().__init__()

        @property
        def control(self) -> "EditorTerminal":
            return self.terminal

    async def on_key(self, event: events.Key) -> None:
        """Forward every key verbatim (no double-tap-escape, no interception)."""
        event.prevent_default()
        event.stop()
        if (stdin := self.state.key_event_to_stdin(event)) is not None:
            await self.write_process_stdin(stdin)

    def update_size(self, width: int, height: int) -> None:
        old_width, old_height = self._width, self._height
        super().update_size(width, height)
        # Keep the PTY in sync so the program (helix) redraws on resize.
        if self._shell_fd is not None and (
            self._width != old_width or self._height != old_height
        ):
            with suppress(OSError):
                self.resize_pty(self._shell_fd, self._width, self._height)

    async def run(self) -> None:
        await super().run()
        # Drop the tool-call framing classes; an editor tab is neutral.
        self.remove_class("-success", "-error")
        # This runs in a task spawned from the screen's on_mount, so the
        # message constructor picks up the WRONG active message pump as
        # sender — which makes Textual stop the bubble one hop early.
        self.post_message(self.Exited(self, self.return_code).set_sender(self))

    def send(self, text: str) -> None:
        """Send raw text to the process stdin (e.g. ``:wq!\\n``)."""
        if self._shell_fd is not None:
            self.call_later(self.write_stdin, text)

    def on_unmount(self) -> None:
        # Tab closed or app exiting: never leak the editor process. A graceful
        # ``:wq!`` has usually already let it exit (then kill() is a no-op);
        # this is the force-kill fallback. Unmount does NOT fire on tab switch
        # (the screen stays mounted), so this never kills a backgrounded tab.
        self.kill()


__all__ = ["EditorTerminal", "Command"]
