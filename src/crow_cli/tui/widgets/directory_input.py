from textual.widgets import Input

from crow_cli.tui.directory_suggester import DirectorySuggester


class DirectoryInput(Input):
    def on_mount(self) -> None:
        self.suggester = DirectorySuggester()
