"""Install command: `crow-cli install crow` — one install, three front doors.

crow's desktop IDE, its browser server and the agent TUI are one product, and
they live in their own repo — `crow-cli/crow`, whose `packages/crow-gui` builds
the IDE and whose `crates/crow-client` builds the TUI. So they are one install:
`install crow` builds whatever is missing from that checkout and
writes the `crow` launcher that fronts all three — `crow` (IDE),
`crow serve-web` (browser), `crow agent` (TUI). The old `install web`
(crow-web systemd tier) and `install gui` (Electron shell around crow-web)
are gone: the IDE serves the web tier itself and is the GUI.
"""

import typer

from crow_cli.cli import install_crow

app = typer.Typer(help="Install crow: the desktop IDE, its web server, and the agent TUI")

app.command(name="crow")(install_crow.install_crow)
