"""The TUI entry point — bare `crow-cli` launches the interactive client.

The TUI is derived from Toad (see src/crow_cli/tui/NOTICE) and drives
`crow-cli acp` exactly like any other ACP agent: it spawns the agent
subprocess and speaks ACP over stdio. The agent command mirrors
client/subagent.py — frozen builds call the binary's `acp` subcommand,
dev runs call the module.
"""

import shlex
import sys
from pathlib import Path

import typer

from crow_cli.tui.agent_schema import Agent


def build_crow_agent(
    model: str | None = None,
    config_dir: Path | None = None,
    config_file: Path | None = None,
) -> Agent:
    """The crow-cli agent definition, flags embedded in the launch command."""
    args: list[str] = []
    if config_dir is not None:
        args += ["--config-dir", shlex.quote(str(config_dir))]
    if config_file is not None:
        args += ["--config-file", shlex.quote(str(config_file))]
    if model is not None:
        args += ["--model", shlex.quote(model)]
    flag_str = (" " + " ".join(args)) if args else ""

    is_frozen = getattr(sys, "frozen", False)
    if is_frozen:
        command = f"{shlex.quote(sys.executable)} acp{flag_str}"
    else:
        command = f"{shlex.quote(sys.executable)} -m crow_cli.agent.main{flag_str}"

    return {
        "identity": "crow-ai.dev",
        "name": "Crow",
        "short_name": "crow",
        "url": "https://crow-ai.dev",
        "protocol": "acp",
        "type": "coding",
        "author_name": "Crow AI",
        "author_url": "https://crow-ai.dev",
        "publisher_name": "Crow AI",
        "publisher_url": "https://crow-ai.dev",
        "description": "The Crow agent — transparent, observable, self-orchestrating.",
        "tags": [],
        "help": "crow-cli's own ACP agent.",
        "run_command": {"*": command},
        "actions": {},
    }


def launch_tui(
    directory: str = ".",
    session: str | None = None,
    model: str | None = None,
    config_dir: Path | None = None,
    config_file: Path | None = None,
) -> None:
    """Launch the TUI against the given project directory."""
    try:
        from crow_cli.tui.app import CrowApp
    except ImportError:
        typer.echo(
            "The TUI needs extra dependencies: install with `crow-cli[tui]`\n"
            "  uv tool install 'crow-cli[tui]'   (or pip install 'crow-cli[tui]')",
            err=True,
        )
        raise typer.Exit(1)

    path = Path(directory).expanduser().resolve()
    if not path.is_dir():
        typer.echo(f"Not a directory: {directory}", err=True)
        raise typer.Exit(1)

    app = CrowApp(
        agent_data=build_crow_agent(model, config_dir, config_file),
        project_dir=str(path),
        mode=None,
        session_id=session,
    )
    app.run()
