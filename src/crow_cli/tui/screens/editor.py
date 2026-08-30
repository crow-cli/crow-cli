"""A session tab whose body is a pass-through terminal running an editor.

This is the *editor* flavour of session tab (see PLAN: the tab model is
``AcpClientChat | Terminal | Editor``). It hosts an :class:`EditorTerminal`
running e.g. ``hx <path>`` and closes itself when that process exits.
"""

from textual import on
from textual.binding import Binding
from textual.screen import Screen
from textual import containers
from textual.widgets import Footer
from textual import getters

from crow_cli.tui.app import CrowApp
from crow_cli.tui import messages
from crow_cli.tui.widgets.session_tabs import SessionsTabs
from crow_cli.tui.widgets.editor_terminal import Command, EditorTerminal


class EditorScreen(Screen):
    """A tab that embeds a live editor (helix) in a terminal emulator."""

    CSS_PATH = "editor.tcss"

    SESSION_NAVIGATION_GROUP = Binding.Group(description="Sessions")
    BINDINGS = [
        Binding(
            "ctrl+left_square_bracket",
            "session_previous",
            "Previous session",
            group=SESSION_NAVIGATION_GROUP,
        ),
        Binding(
            "ctrl+right_square_bracket",
            "session_next",
            "Next session",
            group=SESSION_NAVIGATION_GROUP,
        ),
        Binding(
            "ctrl+q",
            "quit_editor",
            "Quit editor",
            tooltip="Save & quit the editor (:wq!)",
        ),
    ]

    app = getters.app(CrowApp)
    terminal = getters.query_one(EditorTerminal)

    def __init__(self, command: Command) -> None:
        super().__init__()
        self._command = command

    def compose(self):
        yield SessionsTabs()
        with containers.Vertical(id="editor-body"):
            yield EditorTerminal(self._command)
        yield Footer()

    async def on_mount(self) -> None:
        terminal = self.terminal
        width = self.size.width or 80
        # Reserve the tab bar (2 rows, when visible) and the footer (1 row).
        height = max(1, (self.size.height or 24) - 3)
        try:
            await terminal.start(width, height)
        except Exception as error:  # pragma: no cover - defensive
            self.notify(f"Unable to start editor: {error}", severity="error")
            self.post_message(messages.SessionClose(self.id or ""))
            return
        terminal.focus()

    def action_session_previous(self) -> None:
        if self.screen.id is not None:
            self.post_message(messages.SessionNavigate(self.screen.id, -1))

    def action_session_next(self) -> None:
        if self.screen.id is not None:
            self.post_message(messages.SessionNavigate(self.screen.id, +1))

    def action_quit_editor(self) -> None:
        """Save & quit the editor (helix ``:wq!``)."""
        self.quit_editor()

    def quit_editor(self) -> None:
        """Send the editor's save-and-quit sequence; exit closes the tab."""
        terminal = self.terminal
        if terminal.return_code is None:
            terminal.send(":wq!\n")

    @on(EditorTerminal.Exited)
    async def on_editor_terminal_exited(
        self, event: EditorTerminal.Exited
    ) -> None:
        # The editor process is gone — close this tab.
        self.post_message(messages.SessionClose(self.id or ""))

    @on(messages.SessionClose)
    async def on_session_close(self, event: messages.SessionClose) -> None:
        await self.app.close_session_mode(self.id)
