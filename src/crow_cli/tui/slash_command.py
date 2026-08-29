import rich.repr

from textual.content import Content


@rich.repr.auto
class SlashCommand:
    """A record of a slash command."""

    def __init__(self, command: str, help: str, hint: str | None = None) -> None:
        """

        Args:
            command: The command name.
            help: Description of command.
            hint: Hint text (displayed as suggestion)
        """
        self.command = command
        self.help = help
        self.hint: str | None = hint

    def __rich_repr__(self) -> rich.repr.Result:
        yield self.command
        yield "help", self.help
        yield "hint", self.hint, None

    def __str__(self) -> str:
        return self.command

    @property
    def content(self) -> Content:
        return Content.assemble(
            (self.command, "$text-success"), "\t", (self.help, "dim")
        )
