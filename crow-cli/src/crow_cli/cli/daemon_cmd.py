"""`crow-cli-dev daemon` — manage crow's infrastructure services.

Services: crow-memory (rust HTTP memory service), crow-mcp (MCP over HTTP),
ollama-mv (multivector embedding server), searxng (docker). See
crow_cli/cli/daemon.py for the registry and lifecycle conventions.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from crow_cli.agent.configure import get_default_config_dir
from crow_cli.cli import embeddings
from crow_cli.cli.daemon import default_registry, restart, start, status, stop

app = typer.Typer(help="Manage crow infrastructure daemons (memory, mcp, ollama-mv, searxng).")
console = Console()

ALL = "all"


def _specs(config_dir: Path | None, name: str):
    cdir = get_default_config_dir(config_dir)
    registry = default_registry(cdir)
    if name == ALL:
        return cdir, list(registry.values())
    if name not in registry:
        console.print(f"[red]unknown daemon:[/red] {name} (known: {', '.join(registry)})")
        raise typer.Exit(1)
    return cdir, [registry[name]]


@app.command("start")
def start_cmd(
    name: str = typer.Argument(ALL, help="Daemon name, or 'all'."),
    config_dir: Path | None = typer.Option(None, "--config-dir"),
):
    """Start a daemon (no-op if already running)."""
    cdir, specs = _specs(config_dir, name)
    for spec in specs:
        console.print(start(cdir, spec))


@app.command("stop")
def stop_cmd(
    name: str = typer.Argument(ALL, help="Daemon name, or 'all'."),
    config_dir: Path | None = typer.Option(None, "--config-dir"),
):
    """Stop a daemon. Never kills processes we didn't start."""
    cdir, specs = _specs(config_dir, name)
    for spec in specs:
        console.print(stop(cdir, spec))


@app.command("restart")
def restart_cmd(
    name: str = typer.Argument(ALL, help="Daemon name, or 'all'."),
    config_dir: Path | None = typer.Option(None, "--config-dir"),
):
    """Stop then start."""
    cdir, specs = _specs(config_dir, name)
    for spec in specs:
        console.print(restart(cdir, spec))


@app.command("status")
def status_cmd(
    name: str = typer.Argument(ALL, help="Daemon name, or 'all'."),
    config_dir: Path | None = typer.Option(None, "--config-dir"),
    json_out: bool = typer.Option(False, "--json"),
):
    """Show pid / running / health for one or all daemons."""
    cdir, specs = _specs(config_dir, name)
    rows = [status(cdir, spec) for spec in specs]
    if json_out:
        console.print(json.dumps(rows, indent=2))
        return
    table = Table(title="crow daemons")
    table.add_column("name")
    table.add_column("kind")
    table.add_column("pid")
    table.add_column("running")
    table.add_column("healthy")
    table.add_column("detail")
    for r in rows:
        running = "[green]yes[/green]" if r["running"] else "[red]no[/red]"
        healthy_s = "[green]yes[/green]" if r["healthy"] else "[red]no[/red]"
        table.add_row(
            r["name"],
            r["kind"],
            str(r["pid"] or ""),
            running,
            healthy_s,
            r.get("detail", ""),
        )
    console.print(table)


@app.command("list")
def list_cmd(config_dir: Path | None = typer.Option(None, "--config-dir")):
    """Alias for `status all`."""
    status_cmd(ALL, config_dir, False)


@app.command("install")
def install_cmd(
    name: str = typer.Argument(..., help=f"Daemon to provision ('{embeddings.SERVICE_NAME}')."),
    config_dir: Path | None = typer.Option(None, "--config-dir"),
    no_verify: bool = typer.Option(
        False, "--no-verify", help="Skip the post-install embed check."
    ),
):
    """Provision a daemon: build what's missing, point config at it, start it,
    verify. Idempotent — a finished install is a no-op."""
    cdir = get_default_config_dir(config_dir)
    if name != embeddings.SERVICE_NAME:
        console.print(f"[red]no installer for:[/red] {name} (only {embeddings.SERVICE_NAME})")
        raise typer.Exit(1)
    try:
        binary = embeddings.provision(cdir)
    except embeddings.ProvisionError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(f"{embeddings.SERVICE_NAME} binary: [cyan]{binary}[/cyan]")
    # Re-read the registry: config.yaml may have just been repointed.
    console.print(start(cdir, default_registry(cdir)[embeddings.SERVICE_NAME]))
    if not no_verify:
        if not embeddings.verify_embeddings():
            console.print(
                "[red]embeddings: FAILED after 24 attempts — check the ollama-mv log[/red]"
            )
            raise typer.Exit(1)
