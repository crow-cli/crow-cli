from __future__ import annotations
from typing import Iterable

from textual.app import ComposeResult
from textual import containers
from textual.highlight import highlight
from textual.widgets import Static


from crow_cli.tui.menus import MenuItem
from crow_cli.tui.widgets.non_selectable_label import NonSelectableLabel


class ShellResult(containers.HorizontalGroup):
    def __init__(
        self,
        command: str,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        self._command = command
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)

    def compose(self) -> ComposeResult:
        yield NonSelectableLabel("$", id="prompt", markup=False)
        yield Static(highlight(self._command, language="sh"))

    def get_block_menu(self) -> Iterable[MenuItem]:
        yield from ()

    def get_block_content(self, destination: str) -> str | None:
        return self._command
