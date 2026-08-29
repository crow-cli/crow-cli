import shutil

from textual.app import ComposeResult
from textual import on, work
from textual import containers
from textual import getters
from textual.content import Content
from textual.screen import ModalScreen
from textual import widgets
from textual.widget import Widget

from crow_cli.tui.app import CrowApp
from crow_cli.tui.widgets.command_pane import CommandPane


UV_INSTALL = "curl -LsSf https://astral.sh/uv/install.sh | sh"


class ActionModal(ModalScreen):
    """Executes an action command."""

    command_pane = getters.query_one(CommandPane)
    ok_button = getters.query_one("#ok", widgets.Button)

    app = getters.app(CrowApp)

    BINDINGS = [("escape", "dismiss_modal", "Dismiss")]

    def __init__(
        self,
        action: str,
        agent: str,
        title: str,
        command: str,
        *,
        bootstrap_uv: bool = False,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._action = action
        self._agent = agent
        self._title = title
        self._command = command
        self._bootstrap_uv = bootstrap_uv
        super().__init__(name=name, id=id, classes=classes)

    def get_loading_widget(self) -> Widget:
        return widgets.LoadingIndicator()

    def compose(self) -> ComposeResult:
        with containers.VerticalGroup(id="container"):
            yield CommandPane()
            yield widgets.Button("OK", id="ok", disabled=True)

    def enable_button(self) -> None:
        self.ok_button.loading = False
        self.ok_button.disabled = False
        self.ok_button.focus()

    @on(CommandPane.CommandComplete)
    def on_command_complete(self, event: CommandPane.CommandComplete) -> None:
        self.enable_button()

    def on_mount(self) -> None:
        self.ok_button.loading = True
        self.command_pane.border_title = Content(self._title)
        self.run_command()

    @work()
    async def run_command(self) -> None:
        """Write and execute the command."""
        self.command_pane.anchor()
        if self._bootstrap_uv and shutil.which("uv") is None:
            # Bootstrap UV if required
            await self.command_pane.write(f"$ {UV_INSTALL}\n")
            await self.command_pane.execute(UV_INSTALL, final=False)

        await self.command_pane.write(f"$ {self._command}\n")
        action_task = self.command_pane.execute(self._command)
        await action_task
        self.app.capture_event(
            "agent-action",
            action=self._action,
            agent=self._agent,
            fail=self.command_pane.return_code != 0,
        )

    @on(widgets.Button.Pressed)
    def on_button_pressed(self) -> None:
        self.action_dismiss_modal()

    def action_dismiss_modal(self) -> None:
        self.dismiss(self.command_pane.return_code)
