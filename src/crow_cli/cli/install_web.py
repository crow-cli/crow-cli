"""`crow-cli install web` — build and deploy the crow-web tier.

One command turns a checkout into a running service: the bun workspace
builds the SPA, cargo builds the binary that embeds it, the binary lands in
`~/.local/bin`, and a systemd *user* unit keeps it alive across logins. The
unit is the whole deployment — there is no nginx in front of crow-web and no
static directory beside it, because the SPA is inside the executable.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import typer
from rich.console import Console

console = Console()

UNIT_NAME = "crow-web.service"


def repo_root() -> Path:
    """The checkout that owns both the rust crates and the bun workspace."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "Cargo.toml").is_file() and (parent / "packages" / "chat").is_dir():
            return parent
    console.print("[red]not inside a crow-cli checkout (no Cargo.toml + packages/chat)[/red]")
    raise typer.Exit(1)


def unit_text(binary: Path, port: int, root: Path, acp_url: str) -> str:
    """The systemd user unit. Restart on-failure because a pty pump that
    panics must not take the editor down with it for good."""
    return f"""[Unit]
Description=crow-web: the crow web client (embedded SPA, fs buffers, ptys, acp proxy)
After=network.target

[Service]
ExecStart={binary} --port {port} --root {root} --acp-url {acp_url}
Restart=on-failure
RestartSec=2
# The shells crow-web spawns are interactive; give them a real terminal type.
Environment=TERM=xterm-256color

[Install]
WantedBy=default.target
"""


def unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / UNIT_NAME


def run(argv: list[str], cwd: Path) -> None:
    console.print(f"[dim]$ {' '.join(argv)}[/dim]")
    subprocess.run(argv, cwd=cwd, check=True)


def build(repo: Path) -> Path:
    """Frontend first, always: rust-embed reads packages/chat/dist at compile
    time, so a stale dist is a stale UI baked into the binary."""
    if shutil.which("bun") is None:
        console.print("[red]bun is not on PATH; install it (npm i -g bun)[/red]")
        raise typer.Exit(1)
    run(["bun", "install"], repo)
    run(["bun", "run", "web:build"], repo)
    run(["cargo", "build", "--release", "-p", "crow-web"], repo)
    built = repo / "target" / "release" / "crow-web"
    if not built.is_file():
        console.print(f"[red]cargo produced no binary at {built}[/red]")
        raise typer.Exit(1)
    return built


def install_web(
    port: int = typer.Option(2770, "--port", help="Port the web tier listens on"),
    root: Path = typer.Option(None, "--root", help="Directory the editor and explorer serve (default: cwd)"),
    acp_url: str = typer.Option(
        "ws://127.0.0.1:2769/acp", "--acp-url", help="The agent's http endpoint, proxied at /acp"
    ),
    bin_dir: Path = typer.Option(None, "--bin-dir", help="Where the binary lands (default: ~/.local/bin)"),
    no_service: bool = typer.Option(False, "--no-service", help="Install the binary but write no systemd unit"),
    no_build: bool = typer.Option(False, "--no-build", help="Reuse target/release/crow-web instead of building"),
) -> None:
    """Build crow-web and run it as a systemd user service."""
    repo = repo_root()
    root = (root or Path.cwd()).resolve()
    bin_dir = (bin_dir or Path.home() / ".local" / "bin").expanduser()

    console.print("[bold magenta]🪶 crow-web installer[/bold magenta]")
    console.print(f"repo:   [cyan]{repo}[/cyan]")
    console.print(f"root:   [cyan]{root}[/cyan]")
    console.print(f"port:   [cyan]{port}[/cyan]")

    built = repo / "target" / "release" / "crow-web"
    if no_build:
        if not built.is_file():
            console.print(f"[red]--no-build but there is no {built}[/red]")
            raise typer.Exit(1)
    else:
        built = build(repo)

    bin_dir.mkdir(parents=True, exist_ok=True)
    target = bin_dir / "crow-web"
    shutil.copy2(built, target)
    target.chmod(0o755)
    console.print(f"[green]✓[/green] binary at [cyan]{target}[/cyan]")

    if no_service:
        console.print("[yellow]--no-service: start it yourself:[/yellow]")
        console.print(f"  {target} --port {port} --root {root} --acp-url {acp_url}")
        return

    unit = unit_path()
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(unit_text(target, port, root, acp_url))
    console.print(f"[green]✓[/green] unit at [cyan]{unit}[/cyan]")

    systemctl = ["systemctl", "--user"]
    run(systemctl + ["daemon-reload"], Path.home())
    run(systemctl + ["enable", "--now", UNIT_NAME], Path.home())
    run(systemctl + ["status", "--no-pager", UNIT_NAME], Path.home())
    console.print(f"\n[bold green]crow-web is live on http://127.0.0.1:{port}[/bold green]")
