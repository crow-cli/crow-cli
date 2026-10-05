"""Install commands: the crow-web tier, and the Electron GUI that wraps it."""

import shutil
from pathlib import Path

import typer
from rich.console import Console

from crow_cli.cli import install_web

app = typer.Typer(help="Install the crow-web tier and the crow desktop GUI")
console = Console()

app.command(name="web")(install_web.install_web)

# The Electron app lives under ~/.local/share/crow/gui, out of the way of both
# the crow-web systemd unit (~/.local/bin) and the bun workspace. The launcher
# shim and .desktop entry point at it, and the env overrides let a user point
# the same install at a different workspace or agent without reinstalling.
GUI_DIR = ".local/share/crow/gui"


def app_dir(home: Path | None = None) -> Path:
    return (home or Path.home()) / Path(GUI_DIR)


def launcher_text() -> str:
    """The `crow-gui` shim. `CROW_WEB_BIN` is exported because the electron
    main process reads it (via launcher.cjs) to find the bundled binary; the
    other overrides (CROW_ROOT, CROW_ACP_URL) pass straight through the
    environment."""
    return """#!/usr/bin/env sh
# crow-gui — run the Electron shell that wraps crow-web.
# Env overrides: CROW_GUI_DIR (app dir), CROW_WEB_BIN (crow-web binary),
# CROW_ROOT (directory crow-web serves), CROW_ACP_URL (agent endpoint).
set -e
APP_DIR="${CROW_GUI_DIR:-$HOME/.local/share/crow/gui}"
export CROW_WEB_BIN="${CROW_WEB_BIN:-$APP_DIR/crow-web}"
exec "$APP_DIR/node_modules/.bin/electron" "$APP_DIR"
"""


def desktop_text(launcher: Path) -> str:
    return f"""[Desktop Entry]
Type=Application
Name=Crow
Comment=Crow desktop GUI
Exec={launcher}
Terminal=false
Categories=Development;IDE;
"""


@app.command()
def gui(
    root: Path = typer.Option(
        None, "--root", help="Directory the editor and explorer serve (default: cwd)"
    ),
    acp_url: str = typer.Option(
        "ws://127.0.0.1:2769/acp",
        "--acp-url",
        help="The agent's http endpoint, proxied at /acp",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print the install plan without writing anything"
    ),
    no_build: bool = typer.Option(
        False, "--no-build", help="Reuse target/release/crow-web instead of building"
    ),
    no_desktop: bool = typer.Option(
        False, "--no-desktop", help="Write the launcher but no .desktop entry"
    ),
) -> None:
    """Build crow-web and install the Electron GUI shell and its launcher."""
    repo = install_web.repo_root()
    root = (root or Path.cwd()).resolve()
    home = Path.home()
    app = app_dir(home)
    launcher = home / ".local" / "bin" / "crow-gui"
    desktop = home / ".local" / "share" / "applications" / "crow.desktop"
    electron_src = repo / "packages" / "electron"

    console.print("[bold magenta]🪶 crow GUI installer[/bold magenta]")
    console.print(f"repo:   [cyan]{repo}[/cyan]")
    console.print(f"root:   [cyan]{root}[/cyan]")
    console.print(f"app:    [cyan]{app}[/cyan]")

    if dry_run:
        console.print("\n[yellow]Dry run — writing nothing, downloading nothing[/yellow]")
        console.print(
            "would build SPA + crow-web"
            + (" (skipped: --no-build)" if no_build else "")
        )
        console.print(f"would copy crow-web            → [cyan]{app / 'crow-web'}[/cyan]")
        for name in ("main.cjs", "launcher.cjs", "package.json"):
            console.print(f"would copy electron/{name:<12} → [cyan]{app / name}[/cyan]")
        console.print(f"would run `bun install` in [cyan]{app}[/cyan] to fetch electron")
        console.print(f"would write launcher           → [cyan]{launcher}[/cyan]")
        if not no_desktop:
            console.print(f"would write .desktop           → [cyan]{desktop}[/cyan]")
        return

    built = repo / "target" / "release" / "crow-web"
    if no_build:
        if not built.is_file():
            console.print(f"[red]--no-build but there is no {built}[/red]")
            raise typer.Exit(1)
    else:
        built = install_web.build(repo)

    if not electron_src.is_dir():
        console.print(f"[red]electron shell missing at {electron_src}[/red]")
        raise typer.Exit(1)

    app.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built, app / "crow-web")
    (app / "crow-web").chmod(0o755)
    for name in ("main.cjs", "launcher.cjs", "package.json"):
        shutil.copy2(electron_src / name, app / name)
    console.print(f"[green]✓[/green] app files at [cyan]{app}[/cyan]")

    # Electron is a devDependency of the app's own package.json; this is the
    # one network fetch in the command, and the step --dry-run skips.
    install_web.run(["bun", "install"], app)

    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text(launcher_text())
    launcher.chmod(0o755)
    console.print(f"[green]✓[/green] launcher at [cyan]{launcher}[/cyan]")

    if not no_desktop:
        desktop.parent.mkdir(parents=True, exist_ok=True)
        desktop.write_text(desktop_text(launcher))
        console.print(f"[green]✓[/green] desktop entry at [cyan]{desktop}[/cyan]")

    console.print("\n[bold green]crow GUI is installed — run `crow-gui`[/bold green]")
