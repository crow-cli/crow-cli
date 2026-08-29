from typing import Literal
from textual.content import Content

from textual.widget import Widget


from crow_cli.tui.danger import DangerLevel


class DangerWarning(Widget):
    DEFAULT_CSS = """
    DangerWarning {
        height: auto;
        padding: 0 1;
        margin: 1 0;
        &.-dangerous {            
            color: $text-warning;
            border: round $warning;
        }

        &.-destructive {            
            color: $text-error;
            border: round $error;
        }
    }

    """

    def __init__(
        self,
        level: Literal[DangerLevel.DANGEROUS, DangerLevel.DESTRUCTIVE],
        *,
        id: str | None = None,
        classes: str | None = None,
    ):
        self.level = level
        super().__init__(id=id, classes=classes)

    def on_mount(self) -> None:
        if self.level == DangerLevel.DANGEROUS:
            self.add_class("-dangerous")
        elif self.level == DangerLevel.DESTRUCTIVE:
            self.add_class("-destructive")

    def render(self) -> Content:
        if self.level == DangerLevel.DANGEROUS:
            return Content.from_markup(
                "🐸 Potentially dangeous operation — [dim]please review carefully!"
            )
        else:
            return Content.from_markup(
                "🐸 [b]Destructive operation[/b] (may alter files outside of project directory) — [dim]please review carefully!"
            )


if __name__ == "__main__":
    from textual.app import App, ComposeResult

    class DangerApp(App):
        def compose(self) -> ComposeResult:
            yield DangerWarning(DangerLevel.DANGEROUS)
            yield DangerWarning(DangerLevel.DESTRUCTIVE)

    app = DangerApp()
    app.run()
