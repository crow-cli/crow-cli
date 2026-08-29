from textual.app import ComposeResult
from textual import containers

from textual.widgets import Label, Markdown

from crow_cli.tui import get_version


ASCII_CROW = r"""
   .-.
  /'v'\
 (/   \)
='="="===<
   |_|
"""


WELCOME_MD = f"""\
## crow-cli v{get_version()}

Welcome, **Thomas**!


"""


class Welcome(containers.Vertical):
    def compose(self) -> ComposeResult:
        with containers.Center():
            yield Label(ASCII_CROW, id="logo")
        yield Markdown(WELCOME_MD, id="message", classes="note")
