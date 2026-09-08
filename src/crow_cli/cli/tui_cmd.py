"""The TUI entry point — bare `crow-cli` launches the interactive client.

The TUI is derived from Toad (see src/crow_cli/tui/NOTICE) and drives an ACP
agent over stdio exactly like any other ACP client: it spawns the agent
subprocess and speaks ACP. Which agent to spawn comes from the
`agent_servers` config block (see crow_cli.tui.agent_servers):

  * ``-a NAME`` launches exactly that entry — its command, honored as written.
  * no ``-a`` launches the TOP entry, the same way the top model in config.yaml
    is the default model when no ``-m`` is passed.
  * nothing configured launches crow's own agent (:func:`crow_agent`).
"""

from pathlib import Path

import typer

from crow_cli.tui.agent_servers import AgentServerError, crow_agent, resolve_agent_server


def launch_tui(
    directory: str = ".",
    session: str | None = None,
    model: str | None = None,
    config_dir: Path | None = None,
    config_file: Path | None = None,
    agent_server: str | None = None,
) -> None:
    """Launch the TUI against the given project directory."""
    try:
        from crow_cli.tui.app import CrowApp
    except ImportError:
        typer.echo(
            "TUI dependencies are missing — your crow-cli install looks broken.\n"
            "Reinstall it (e.g. `uv tool install --from ./crow-cli crow-cli --python 3.14`).",
            err=True,
        )
        raise typer.Exit(1)

    path = Path(directory).expanduser().resolve()
    if not path.is_dir():
        typer.echo(f"Not a directory: {directory}", err=True)
        raise typer.Exit(1)

    from crow_cli.config import Config

    config = Config.load(config_dir=config_dir)
    if agent_server is None:
        # No -a: the top entry wins — same rule as models, where the top model
        # in config.yaml is what you get when no -m is passed.
        agent_server = next(iter(config.agent_servers), None)

    if agent_server is None:
        agent_data = crow_agent(model, config_dir, config_file)
    else:
        try:
            agent_data = resolve_agent_server(agent_server, config.agent_servers)
        except AgentServerError as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(1) from error

    app = CrowApp(
        agent_data=agent_data,
        project_dir=str(path),
        mode=None,
        session_id=session,
    )
    app.run()
