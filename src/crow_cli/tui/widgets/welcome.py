from textual.app import ComposeResult
from textual import containers

from textual.widgets import Label, Markdown


ASCII_CROW = r"""
   .-.
  /'v'\
 (/   \)
='="="===<
   |_|
"""


WELCOME_MD = """\
## crow-cli v0.1.39

Welcome, **Thomas**!


"""


class Welcome(containers.Vertical):
    def compose(self) -> ComposeResult:
        with containers.Center():
            yield Label(ASCII_CROW, id="logo")
        yield Markdown(WELCOME_MD, id="message", classes="note")
