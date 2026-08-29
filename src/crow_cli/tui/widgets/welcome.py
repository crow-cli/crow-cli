from textual.app import ComposeResult
from textual import containers

from textual.widgets import Label, Markdown


ASCII_TOAD = r"""
         _   _
        (.)_(.)
     _ (   _   ) _
    / \/`-----'\/ \
  __\ ( (     ) ) /__
  )   /\ \._./ /\   (
   )_/ /|\   /|\ \_(
"""


WELCOME_MD = """\
## Toad v1.0

Welcome, **Will**!


"""


class Welcome(containers.Vertical):
    def compose(self) -> ComposeResult:
        with containers.Center():
            yield Label(ASCII_TOAD, id="logo")
        yield Markdown(WELCOME_MD, id="message", classes="note")
