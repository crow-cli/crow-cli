"""`crow-cli install crow` — build and install crowdium, crow's IDE.

crow's IDE is VS Code, built by `packages/crow-gui` (a vendored VSCodium
pipeline) into two artifacts: the Electron desktop app and the `reh-web`
browser server. This command installs both under `~/.local/share/crow` and puts
a single `crow` binary on PATH:

    crow [args]      the desktop IDE (args go to it: `crow .`, `crow --diff a b`)
    crow web         the same IDE in a browser, served locally
    crow agent       the crow agent REPL (`crow-cli run -i`)
    crow tunnel …    the built-in tunnel/remote CLI

`crow agent` is handled in two places that agree: the shim below (fast path, no
Electron/node hop) and the IDE's own Rust CLI, where
`vscodium/patches/user/01-cli-crow-agent.patch` moves upstream's agent-host
manager to `agent-host` and gives `agent` to crow. So `bin/crow agent` works
too, for anything that bypasses the shim.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import typer
from rich.console import Console

from crow_cli.cli import install_web

console = Console()

# Everything crow installs lives under ~/.local/share/crow, beside the
# crow-web tier's own state; the build tree in packages/crow-gui/vscodium is
# scratch and can be deleted after installing.
SHARE_DIR = ".local/share/crow"
IDE_SUBDIR = "ide"
WEB_SUBDIR = "web"
DEFAULT_WEB_PORT = 8769


def short(path: Path) -> str:
    """~-relative: rich wraps long absolute paths into unreadable output."""
    text = str(path)
    home = str(Path.home())
    return "~" + text[len(home):] if text.startswith(home + "/") else text


def pipeline_dir(repo: Path) -> Path:
    pipeline = repo / "packages" / "crow-gui"
    if not (pipeline / "build.sh").is_file():
        console.print(f"[red]no crow-gui pipeline at {pipeline}[/red]")
        raise typer.Exit(1)
    return pipeline


def launcher_text(web_port: int) -> str:
    """The `crow` shim: one binary, three front doors. Kept POSIX sh so it runs
    before anything else on a machine is set up."""
    return f"""#!/usr/bin/env sh
# crow — crow's IDE. Built by packages/crow-gui, installed by `crow-cli install crow`.
#
#   crow [args]        the desktop IDE; args go straight to it
#   crow web [args]    the same IDE in a browser (extra args go to the server)
#   crow agent [args]  the crow agent REPL
#   crow tunnel [args] the built-in tunnel/remote CLI
#
# Env: CROW_IDE_DIR, CROW_WEB_DIR, CROW_WEB_HOST, CROW_WEB_PORT, CROW_CLI
set -e

IDE_DIR="${{CROW_IDE_DIR:-$HOME/{SHARE_DIR}/{IDE_SUBDIR}}}"
WEB_DIR="${{CROW_WEB_DIR:-$HOME/{SHARE_DIR}/{WEB_SUBDIR}}}"
WEB_HOST="${{CROW_WEB_HOST:-127.0.0.1}}"
WEB_PORT="${{CROW_WEB_PORT:-{web_port}}}"
CROW_CLI="${{CROW_CLI:-crow-cli}}"

sub=""
if [ $# -gt 0 ]; then
  sub="$1"
  shift
fi

case "$sub" in
  agent)
    exec "$CROW_CLI" run -i "$@"
    ;;
  web|serve-web)
    if [ ! -x "$WEB_DIR/bin/crow-server" ]; then
      echo "crow: no web server at $WEB_DIR — run `crow-cli install crow`" >&2
      exit 1
    fi
    echo "crow: serving on http://$WEB_HOST:$WEB_PORT (the server prints the tokenised URL)" >&2
    exec "$WEB_DIR/bin/crow-server" --host "$WEB_HOST" --port "$WEB_PORT" "$@"
    ;;
  tunnel)
    exec "$IDE_DIR/bin/crow-tunnel" "$@"
    ;;
  "")
    exec "$IDE_DIR/bin/crow"
    ;;
  *)
    exec "$IDE_DIR/bin/crow" "$sub" "$@"
    ;;
esac
"""


def desktop_text(launcher: Path, icon: Path | None) -> str:
    icon_line = f"Icon={icon}\n" if icon else ""
    return f"""[Desktop Entry]
Type=Application
Name=Crow
GenericName=Code Editor
Comment=crow's IDE — VS Code, built by crow
Exec={launcher} %F
{icon_line}Terminal=false
Categories=Development;IDE;
MimeType=text/plain;inode/directory;
StartupWMClass=Crow
"""


def copy_tree(src: Path, dst: Path) -> None:
    """`cp -a` rather than shutil: these trees are ~1GB and tens of thousands
    of files, and permissions/symlinks must survive."""
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    # relative src keeps the echoed command inside one terminal line
    install_web.run(["cp", "-a", src.name, str(dst)], src.parent)


def install_crow(
    arch: str = typer.Option("x64", "--arch", help="VS Code arch the pipeline built (x64, arm64)"),
    prefix: Path = typer.Option(None, "--prefix", help="Install prefix (default: ~/.local)"),
    web_port: int = typer.Option(DEFAULT_WEB_PORT, "--web-port", help="Default port for `crow web`"),
    no_web: bool = typer.Option(False, "--no-web", help="Install the desktop IDE only"),
    no_build: bool = typer.Option(False, "--no-build", help="Fail instead of building when artifacts are missing"),
    rebuild: bool = typer.Option(False, "--rebuild", help="Run the pipeline even if artifacts already exist"),
    no_desktop: bool = typer.Option(False, "--no-desktop", help="Write the launcher but no .desktop entry"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the install plan without writing anything"),
) -> None:
    """Build crow's IDE (desktop + web) and install the `crow` binary."""
    repo = install_web.repo_root()
    pipeline = pipeline_dir(repo)
    home = Path.home()
    root = prefix or home / ".local"
    share = root / "share" / "crow"
    launcher = root / "bin" / "crow"
    desktop = root / "share" / "applications" / "crow.desktop"
    wanted = [
        ("ide", pipeline / "vscodium" / f"VSCode-linux-{arch}", share / IDE_SUBDIR),
    ]
    if not no_web:
        wanted.append(("web", pipeline / "vscodium" / f"vscode-reh-web-linux-{arch}", share / WEB_SUBDIR))

    console.print("[bold magenta]🪶 crow IDE installer[/bold magenta]")
    console.print(f"pipeline: [cyan]{short(pipeline)}[/cyan]")
    for label, built, dest in wanted:
        state = "[green]built[/green]" if built.is_dir() else "[yellow]missing[/yellow]"
        console.print(f"{label:>4}: [cyan]{built.relative_to(pipeline)}[/cyan] {state} → [cyan]{short(dest)}[/cyan]")
    console.print(f"launcher: [cyan]{short(launcher)}[/cyan]")

    missing = [built for _, built, _ in wanted if not built.is_dir()]
    need_build = rebuild or bool(missing)

    if dry_run:
        console.print("\n[yellow]Dry run — writing nothing, building nothing[/yellow]")
        if need_build:
            flags = ["./build.sh", "--arch", arch] + (["--no-web"] if no_web else [])
            console.print(f"would run [cyan]{' '.join(flags)}[/cyan] in {short(pipeline)}")
        else:
            console.print("would skip the build (artifacts present, no --rebuild)")
        for label, built, dest in wanted:
            console.print(f"would cp -a {built.relative_to(pipeline)} → [cyan]{short(dest)}[/cyan]")
        console.print(f"would write launcher  → [cyan]{short(launcher)}[/cyan]")
        if not no_desktop:
            console.print(f"would write .desktop  → [cyan]{short(desktop)}[/cyan]")
        return

    if missing and no_build:
        for built in missing:
            console.print(f"[red]--no-build but there is no {built}[/red]")
        raise typer.Exit(1)

    if need_build:
        if no_build:
            console.print("[red]--rebuild with --no-build makes no sense[/red]")
            raise typer.Exit(1)
        flags = ["./build.sh", "--arch", arch]
        if no_web:
            flags.append("--no-web")
        console.print(f"\n[bold]building[/bold] [dim](this is the long part: gulp minify + package + cargo CLI)[/dim]")
        started = time.monotonic()
        install_web.run(flags, pipeline)
        console.print(f"[green]✓[/green] built in {(time.monotonic() - started) / 60:.1f} min")
        for label, built, _ in wanted:
            if not built.is_dir():
                console.print(f"[red]the build produced no {label} at {built}[/red]")
                raise typer.Exit(1)

    for label, built, dest in wanted:
        copy_tree(built, dest)
        console.print(f"[green]✓[/green] {label} at [cyan]{short(dest)}[/cyan]")

    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text(launcher_text(web_port))
    launcher.chmod(0o755)
    console.print(f"[green]✓[/green] launcher at [cyan]{short(launcher)}[/cyan]")

    if not no_desktop:
        icon = share / IDE_SUBDIR / "resources" / "app" / "resources" / "linux" / "code.png"
        desktop.parent.mkdir(parents=True, exist_ok=True)
        desktop.write_text(desktop_text(launcher, icon if icon.is_file() else None))
        console.print(f"[green]✓[/green] desktop entry at [cyan]{short(desktop)}[/cyan]")

    console.print("\n[bold green]crow is installed[/bold green]")
    console.print("  [cyan]crow[/cyan]           the desktop IDE")
    if not no_web:
        console.print(f"  [cyan]crow web[/cyan]       the IDE in a browser on port {web_port}")
    console.print("  [cyan]crow agent[/cyan]     the crow agent REPL")
    if shutil.which("crow") != str(launcher):
        console.print(f"[yellow]note:[/yellow] {launcher.parent} is not first on PATH — `crow` may resolve elsewhere")
