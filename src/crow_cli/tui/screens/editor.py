"""A session tab whose body is a pass-through terminal running an editor.

This is the *editor* flavour of session tab (see PLAN: the tab model is
``AcpClientChat | Terminal | Editor``). It hosts an :class:`EditorTerminal`
running e.g. ``hx <path>`` and closes itself when that process exits.

The screen mirrors MainScreen's chrome: the same sidebar (so the project
explorer stays available) and the same optional column constraint, so the
editor occupies the same horizontal band as the chat instead of the full
window width.
"""

from textual import containers, getters, on
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DirectoryTree, Footer, Tree

from crow_cli.tui.app import CrowApp
from crow_cli.tui import messages
from crow_cli.tui.widgets.editor_terminal import Command, EditorTerminal
from crow_cli.tui.widgets.plan import Plan
from crow_cli.tui.widgets.project_directory_tree import ProjectDirectoryTree
from crow_cli.tui.widgets.session_tabs import SessionsTabs
from crow_cli.tui.widgets.side_bar import SideBar


class EditorScreen(Screen):
    """A tab that embeds a live editor (helix) in a terminal emulator."""

    CSS_PATH = "editor.tcss"

    # The sidebar is first in DOM order; without this the screen's
    # auto-focus would land on a collapsible title instead of the editor.
    AUTO_FOCUS = "EditorTerminal"

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
        # Same page as the chat: sidebar left, and the tab bar INSIDE the
        # column (as Conversation hosts SessionsTabs on MainScreen).
        with containers.Center():
            yield SideBar(
                SideBar.Panel("Plan", Plan([])),
                SideBar.Panel(
                    "Project",
                    ProjectDirectoryTree(
                        self.app.project_dir,
                        id="project_directory_tree",
                    ),
                    flex=True,
                ),
            )
            with containers.Vertical(id="editor-body"):
                yield SessionsTabs()
                yield EditorTerminal(self._command)
        yield Footer()

    async def on_mount(self) -> None:
        self._watch_column()
        terminal = self.terminal
        # The terminal's own content region (chrome already excluded) —
        # starting the PTY at any other size forces a SIGWINCH repaint.
        width, height = terminal.scrollable_content_region.size
        try:
            await terminal.start(width or 80, max(1, height or 24))
        except Exception as error:  # pragma: no cover - defensive
            self.notify(f"Unable to start editor: {error}", severity="error")
            self.post_message(messages.SessionClose(self.id or ""))
            return
        terminal.focus()

    def _watch_column(self) -> None:
        # data_bind() is not an option here: it resolves the source from the
        # *active message pump*, which is MainScreen when a file click opens
        # the tab. Watching the app's reactives directly is context-free.
        self.watch(self.app, "column", self._apply_column_width, init=True)
        self.watch(self.app, "column_width", self._apply_column_width, init=True)

    def _apply_column_width(self) -> None:
        body = self.query_one("#editor-body")
        body.styles.max_width = (
            max(10, self.app.column_width) if self.app.column else None
        )
        body.set_class(self.app.column, "-column")

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
            terminal.send(":wq!\r")

    @on(SideBar.Dismiss)
    def on_side_bar_dismiss(self, message: SideBar.Dismiss) -> None:
        message.stop()
        self.terminal.focus()

    @on(DirectoryTree.FileSelected, "ProjectDirectoryTree")
    async def on_project_directory_tree_selected(
        self, event: Tree.NodeSelected
    ) -> None:
        if (data := event.node.data) is not None:
            await self.app.open_file_in_editor(data.path)

    @on(EditorTerminal.Exited)
    async def on_editor_terminal_exited(
        self, event: EditorTerminal.Exited
    ) -> None:
        # The editor process is gone — close this tab.
        self.post_message(messages.SessionClose(self.id or ""))

    @on(messages.SessionClose)
    async def on_session_close(self, event: messages.SessionClose) -> None:
        await self.app.close_session_mode(self.id)
