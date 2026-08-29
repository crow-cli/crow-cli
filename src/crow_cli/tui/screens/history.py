"""Agent history screen — sessions discovered via ACP `session/list`.

Visually modeled on the tabs screen (sessions.py), but the entries are the
agent server's own sessions for the current working directory. The session
id is the star; everything else is supporting cast.
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual import containers
from textual import getters
from textual import widgets
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual import on, work

from crow_cli.tui.acp import protocol
from crow_cli.tui.app import CrowApp
from crow_cli.tui.screens.session_resume_modal import SessionResumeModal
from crow_cli.tui.session_list import list_sessions, SessionListError
from crow_cli.tui.widgets.grid_select import GridSelect


class HistoryCard(containers.VerticalGroup):
    """A single session from the agent's history."""

    session_info: reactive[protocol.SessionInfo | None] = reactive(
        None, always_update=True, recompose=True
    )

    def __init__(
        self,
        session_info: protocol.SessionInfo,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self.set_reactive(HistoryCard.session_info, session_info)

    def compose(self) -> ComposeResult:
        if (session_info := self.session_info) is not None:
            with containers.HorizontalGroup():
                yield widgets.Label("❯", classes="icon")
                with containers.VerticalGroup():
                    yield widgets.Label(
                        session_info["sessionId"],
                        classes="title",
                        markup=False,
                    )
                    subtitle = ""
                    if updated_at := session_info.get("updatedAt"):
                        subtitle = SessionResumeModal.friendly_time_ago(updated_at)
                    if title := session_info.get("title"):
                        subtitle = f"{subtitle}  {title}" if subtitle else title
                    yield widgets.Label(subtitle, classes="subtitle", markup=False)


class LoadMoreCard(widgets.Static):
    """Sentinel at the bottom of the grid; select it to fetch the next page."""

    def __init__(self) -> None:
        super().__init__("Load more…", id="load-more", classes="load-more")


class HistoryGridSelect(GridSelect):
    app: getters.app[CrowApp] = getters.app(CrowApp)

    def __init__(self) -> None:
        super().__init__(id="history-grid", min_column_width=40)

    def allow_focus(self) -> bool:
        return True


class HistoryScreen(ModalScreen[str]):
    """Pick a session from the agent's history (session/list for this cwd)."""

    CSS_PATH = "history.tcss"

    BINDINGS = [Binding("escape", "dismiss", "Dismiss")]

    app: getters.app[CrowApp] = getters.app(CrowApp)
    grid = getters.query_one(HistoryGridSelect)

    def __init__(self) -> None:
        super().__init__()
        self._dismissed = False
        self._next_cursor: str | None = None
        self._fetching = False

    def compose(self) -> ComposeResult:
        with containers.Center(id="title-container"):
            yield widgets.Label("History")
        yield widgets.Static(
            "Sessions for this directory, from the agent. Select one to resume.",
            classes="instructions",
        )
        yield widgets.Static("Contacting agent…", id="loading")
        yield HistoryGridSelect()
        yield widgets.Footer()

    @property
    def focus_chain(self) -> list:
        return [self.grid]

    def on_mount(self) -> None:
        self.fetch_sessions()

    @work(exclusive=True)
    async def fetch_sessions(self, cursor: str | None = None) -> None:
        if self._fetching:
            return
        self._fetching = True
        try:
            agent_data = self.app.agent_data
            if agent_data is None:
                self.notify("No agent configured", title="History", severity="error")
                self.dismiss()
                return
            try:
                sessions, next_cursor = await list_sessions(
                    agent_data, self.app.project_dir, cursor=cursor
                )
            except SessionListError as error:
                self.notify(str(error), title="History", severity="error")
                if cursor is None:
                    self.dismiss()
                return
            self._next_cursor = next_cursor

            loading = self.query_one_optional("#loading")
            if loading is not None:
                loading.display = False

            grid = self.grid
            sentinel = self.query_one_optional("#load-more")
            if sentinel is not None:
                await sentinel.remove()

            for session_info in sessions:
                await grid.mount(
                    HistoryCard(session_info, id=session_info["sessionId"])
                )
            if next_cursor is not None:
                await grid.mount(LoadMoreCard())

            if not grid.children:
                self.query_one(".instructions", widgets.Static).update(
                    "No sessions for this directory yet."
                )
            # Focus may have landed before the cards existed, in which case
            # on_focus saw no children and left the highlight unset.
            if grid.highlighted is None and grid.children:
                grid.highlight_first()
            grid.focus(scroll_visible=False)
        finally:
            self._fetching = False

    @on(GridSelect.Selected)
    def on_selected(self, event: GridSelect.Selected) -> None:
        event.stop()
        # Guard against a double delivery (e.g. key repeat): dismissing a
        # second time raises ScreenStackError once the screen is popped.
        if self._dismissed:
            return
        if isinstance(event.widget, LoadMoreCard):
            if self._next_cursor is not None:
                self.fetch_sessions(self._next_cursor)
        elif isinstance(event.widget, HistoryCard):
            session_info = event.widget.session_info
            if session_info is not None:
                self._dismissed = True
                self.dismiss(session_info["sessionId"])
