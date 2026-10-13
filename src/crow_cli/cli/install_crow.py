"""`crow-cli install crow` — build and install crowdium, crow's IDE.

crow's IDE is VS Code, built by `packages/crow-gui` (a vendored VSCodium
pipeline) into two artifacts: the Electron desktop app and the `reh-web`
browser server. This command INSTALLS them, and on Linux the install is the
`.deb`: `./build.sh --deb` plus `sudo dpkg -i`, which is the only route that
gets a root-owned 4755 `chrome-sandbox` (Chromium refuses to launch without it
on kernels that restrict unprivileged user namespaces — Ubuntu 24.04+) and the
one that puts `crow.desktop`, `/usr/bin/crow` and `/usr/share/crow/web` where
the rest of the system expects them. `--no-deb` keeps the old rootless copy
under `~/.local/share/crow`, which is a build you can run, not an install.

Either way a single `crow` binary lands on PATH:

    crow [args]      the desktop IDE (args go to it: `crow .`, `crow --diff a b`)
    crow serve-web   the same IDE in a browser, through the IDE's own CLI
                     (it starts the bundled server and prints a tokenised URL)
    crow agent       the crow agent TUI (crates/crow-client's `crow-agent`)
    crow tunnel …    the built-in tunnel/remote CLI

The TUI is a Rust binary built from this repo's `crates/crow-client`, and this
command builds it (`cargo build --release --bin crow-agent`) and installs it
beside the launcher — `crow agent` is only as good as the binary it execs. Two
front doors agree on that binary: the shim below (fast path, no Electron/node
hop) and the IDE's own Rust CLI, where
`vscodium/patches/user/01-cli-crow-agent.patch` moves upstream's agent-host
manager to `agent-host` and gives `agent` to crow. So `bin/crow agent` works
too, for anything that bypasses the shim.

The web server is the same shape: it is installed beside the IDE, and
`vscodium/patches/user/06-serveweb-local-server.patch` makes the IDE's
`serve-web` start that one instead of asking an update service for a release to
download (crow publishes none). The deb ships it at `/usr/share/crow/web`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import typer
from rich.console import Console

console = Console()


def repo_root() -> Path:
    """The checkout that owns the rust crates and the crow-gui pipeline."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "Cargo.toml").is_file() and (parent / "packages" / "crow-gui").is_dir():
            return parent
    console.print("[red]not inside a crow-cli checkout (no Cargo.toml + packages/crow-gui)[/red]")
    raise typer.Exit(1)


def run(argv: list[str], cwd: Path) -> None:
    console.print(f"[dim]$ {' '.join(argv)}[/dim]")
    subprocess.run(argv, cwd=cwd, check=True)

# Everything crow installs lives under ~/.local/share/crow, beside the
# crow-web tier's own state; the build tree in packages/crow-gui/vscodium is
# scratch and can be deleted after installing.
SHARE_DIR = ".local/share/crow"
IDE_SUBDIR = "ide"
WEB_SUBDIR = "web"


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


def launcher_text() -> str:
    """The `crow` shim: one binary, three front doors. Kept POSIX sh so it runs
    before anything else on a machine is set up."""
    return f"""#!/usr/bin/env sh
# crow — crow's IDE. Built by packages/crow-gui, installed by `crow-cli install crow`.
#
#   crow [args]        the desktop IDE; args go straight to it
#   crow serve-web     the same IDE in a browser, via the IDE's CLI: it finds the
#                      server bundled beside it and prints a tokenised URL
#   crow agent [args]  the crow agent TUI
#   crow tunnel [args] the built-in tunnel/remote CLI
#
# Env: CROW_IDE_DIR, CROW_AGENT_BIN. serve-web resolves the web server itself
# ($CROW_WEB_DIR, then the `web` dir beside the IDE, then /usr/bin/crow-web).
set -e

IDE_DIR="${{CROW_IDE_DIR:-$HOME/{SHARE_DIR}/{IDE_SUBDIR}}}"
# A package install wins over the user-prefix copy: Chromium only accepts a
# root-owned 4755 chrome-sandbox, and without it the IDE dies silently on
# kernels that restrict unprivileged user namespaces (Ubuntu 24.04+).
if [ -z "${{CROW_IDE_DIR:-}}" ] && [ -x /usr/share/crow/bin/crow ]; then
  IDE_DIR=/usr/share/crow
fi
CROW_AGENT_BIN="${{CROW_AGENT_BIN:-crow-agent}}"

sub=""
if [ $# -gt 0 ]; then
  sub="$1"
  shift
fi

case "$sub" in
  agent)
    exec "$CROW_AGENT_BIN" "$@"
    ;;
  serve-web)
    # The IDE's own CLI: it finds the web server installed beside it (the deb
    # puts it at /usr/share/crow/web, this installer at ~/.local/share/crow/web)
    # and serves it — crow publishes no release tarballs for it to download.
    exec "$IDE_DIR/bin/crow" serve-web "$@"
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
StartupWMClass=crow
"""


def copy_tree(src: Path, dst: Path) -> None:
    """`cp -a` rather than shutil: these trees are ~1GB and tens of thousands
    of files, and permissions/symlinks must survive."""
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    # relative src keeps the echoed command inside one terminal line
    run(["cp", "-a", src.name, str(dst)], src.parent)


# ---------------------------------------------------------------------------
# The .deb route — the one that is actually an install
# ---------------------------------------------------------------------------

#: What building a .deb needs on top of the pipeline's own prerequisites
#: (dpkg-dev provides dpkg-deb; fakeroot gives the archive root:root ownership).
DEB_TOOLS = ("dpkg-deb", "fakeroot")


def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def deb_preflight() -> list[str]:
    """The tools the .deb route is missing, empty when it can run.

    Checked before a 40-minute build, not after: there is nothing worse than a
    pipeline that succeeds and then cannot be installed.
    """
    missing = [tool for tool in DEB_TOOLS if shutil.which(tool) is None]
    if not is_root() and shutil.which("sudo") is None:
        missing.append("sudo")
    return missing


def built_deb(pipeline: Path) -> Path | None:
    """The newest `crow_*.deb` under `vscodium/assets/`, if the pipeline made one."""
    debs = sorted(
        (pipeline / "vscodium" / "assets").glob("crow_*.deb"),
        key=lambda p: p.stat().st_mtime,
    )
    return debs[-1] if debs else None


def dpkg_install(deb: Path) -> None:
    """`dpkg -i` — the step that turns a build into an install."""
    argv = ["dpkg", "-i", str(deb)] if is_root() else ["sudo", "dpkg", "-i", str(deb)]
    console.print(f"[dim]$ {' '.join(argv)}[/dim]")
    if subprocess.run(argv, cwd=str(deb.parent)).returncode != 0:
        console.print("[red]dpkg -i failed — unsatisfied dependencies are the usual cause:[/red]")
        console.print("[cyan]  sudo apt-get install -f[/cyan]")
        raise typer.Exit(1)


def install_crow(
    arch: str = typer.Option("x64", "--arch", help="VS Code arch the pipeline built (x64, arm64)"),
    prefix: Path = typer.Option(None, "--prefix", help="Install prefix (default: ~/.local)"),
    no_web: bool = typer.Option(False, "--no-web", help="Install the desktop IDE only"),
    deb: bool = typer.Option(
        True,
        "--deb/--no-deb",
        help="Linux: build the .deb and install it with dpkg -i (system-wide, root-owned "
        "chrome-sandbox). --no-deb copies the built trees under the prefix instead — no root, no sandbox.",
    ),
    no_build: bool = typer.Option(False, "--no-build", help="Fail instead of building when artifacts are missing"),
    rebuild: bool = typer.Option(False, "--rebuild", help="Run the pipeline even if artifacts already exist"),
    no_desktop: bool = typer.Option(False, "--no-desktop", help="Rootless route only: write the launcher but no .desktop entry (the deb ships its own)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the install plan without writing anything"),
) -> None:
    """Build crow's IDE and the crow agent TUI, and install both.

    On Linux the IDE install is the `.deb` (`--deb`, the default): the pipeline
    builds it and `dpkg -i` installs it system-wide. `--no-deb` copies the built
    trees under the prefix instead — no root, and no setuid chrome-sandbox.
    """
    repo = repo_root()
    pipeline = pipeline_dir(repo)
    home = Path.home()
    root = prefix or home / ".local"
    share = root / "share" / "crow"
    launcher = root / "bin" / "crow"
    desktop = root / "share" / "applications" / "crow.desktop"

    # The .deb IS the install on Linux. The prefix copy is a build you can run:
    # no root, so no setuid chrome-sandbox, and a user-level .desktop entry that
    # shadows the package's.
    use_deb = deb and sys.platform == "linux"
    if deb and not use_deb:
        console.print("[yellow]the .deb route is Linux-only — copying the built trees under the prefix instead[/yellow]")
    if use_deb and no_web:
        console.print("[yellow]--no-web: the .deb will carry no web server, so `crow serve-web` will not work[/yellow]")

    wanted = [
        ("ide", pipeline / "vscodium" / f"VSCode-linux-{arch}", share / IDE_SUBDIR),
    ]
    if not no_web:
        wanted.append(("web", pipeline / "vscodium" / f"vscode-reh-web-linux-{arch}", share / WEB_SUBDIR))

    console.print("[bold magenta]🪶 crow IDE installer[/bold magenta]")
    console.print(f"pipeline: [cyan]{short(pipeline)}[/cyan]")
    have_deb = built_deb(pipeline) if use_deb else None
    if use_deb:
        state = "[green]built[/green]" if have_deb else "[yellow]missing[/yellow]"
        name = have_deb.name if have_deb else "crow_*.deb"
        console.print(f" deb: [cyan]vscodium/assets/{name}[/cyan] {state} → [cyan]dpkg -i[/cyan] (system-wide)")
        missing_tools = deb_preflight()
        if missing_tools:
            console.print(f"[red]the .deb route needs: {', '.join(missing_tools)}[/red]")
            console.print("[dim]  debian/ubuntu: sudo apt-get install dpkg-dev fakeroot — or pass --no-deb[/dim]")
            raise typer.Exit(1)
    else:
        for label, built, dest in wanted:
            state = "[green]built[/green]" if built.is_dir() else "[yellow]missing[/yellow]"
            console.print(f"{label:>4}: [cyan]{built.relative_to(pipeline)}[/cyan] {state} → [cyan]{short(dest)}[/cyan]")
    console.print(f"tui: [cyan]crates/crow-client[/cyan] → [cyan]{short(root / 'bin' / 'crow-agent')}[/cyan]")
    console.print(f"launcher: [cyan]{short(launcher)}[/cyan]")

    missing = [built for _, built, _ in wanted if not built.is_dir()]
    need_build = rebuild or (have_deb is None if use_deb else bool(missing))
    flags = ["./build.sh", "--arch", arch]
    if no_web:
        flags.append("--no-web")
    if use_deb:
        flags.append("--deb")

    if dry_run:
        console.print("\n[yellow]Dry run — writing nothing, building nothing[/yellow]")
        if need_build:
            console.print(f"would run [cyan]{' '.join(flags)}[/cyan] in {short(pipeline)}")
        else:
            console.print("would skip the build (artifacts present, no --rebuild)")
        if use_deb:
            target = short(have_deb) if have_deb else "vscodium/assets/crow_*.deb"
            console.print(f"would {'sudo ' if not is_root() else ''}dpkg -i [cyan]{target}[/cyan]")
            if desktop.exists():
                console.print(f"would remove the user-level entry shadowing the package's → [cyan]{short(desktop)}[/cyan]")
        else:
            for label, built, dest in wanted:
                console.print(f"would cp -a {built.relative_to(pipeline)} → [cyan]{short(dest)}[/cyan]")
        console.print("would cargo build --release --bin crow-agent")
        console.print(f"would copy TUI        → [cyan]{short(root / 'bin' / 'crow-agent')}[/cyan]")
        console.print(f"would write launcher  → [cyan]{short(launcher)}[/cyan]")
        if not no_desktop and not use_deb:
            console.print(f"would write .desktop  → [cyan]{short(desktop)}[/cyan]")
        return

    if no_build and rebuild:
        console.print("[red]--rebuild with --no-build makes no sense[/red]")
        raise typer.Exit(1)

    if no_build and need_build:
        what = "no .deb under vscodium/assets" if use_deb else ", ".join(f"no {b}" for b in missing)
        console.print(f"[red]--no-build but there is {what}[/red]")
        raise typer.Exit(1)

    if need_build:
        console.print(f"\n[bold]building[/bold] [dim](this is the long part: gulp minify + package + cargo CLI)[/dim]")
        started = time.monotonic()
        run(flags, pipeline)
        console.print(f"[green]✓[/green] built in {(time.monotonic() - started) / 60:.1f} min")
        if use_deb:
            have_deb = built_deb(pipeline)
            if have_deb is None:
                console.print("[red]the build produced no .deb under vscodium/assets/[/red]")
                raise typer.Exit(1)
        else:
            for label, built, _ in wanted:
                if not built.is_dir():
                    console.print(f"[red]the build produced no {label} at {built}[/red]")
                    raise typer.Exit(1)

    if use_deb:
        how = "as root" if is_root() else "via sudo"
        console.print(f"\n[bold]installing the .deb[/bold] [dim](dpkg -i {how})[/dim]")
        dpkg_install(have_deb)
        console.print(f"[green]✓[/green] {have_deb.name} installed — /usr/share/crow, /usr/bin/crow, /usr/bin/crow-web")
    else:
        for label, built, dest in wanted:
            copy_tree(built, dest)
            console.print(f"[green]✓[/green] {label} at [cyan]{short(dest)}[/cyan]")

    if shutil.which("cargo") is None:
        console.print("[red]cargo is not on PATH — the crow agent TUI is a Rust binary (crates/crow-client)[/red]")
        raise typer.Exit(1)
    tui = root / "bin" / "crow-agent"
    console.print(f"\n[bold]building the crow agent TUI[/bold] [dim](cargo release; incremental after the first run)[/dim]")
    started = time.monotonic()
    run(["cargo", "build", "--release", "--bin", "crow-agent"], repo)
    console.print(f"[green]✓[/green] built in {(time.monotonic() - started) / 60:.1f} min")
    built_tui = repo / "target" / "release" / "crow-agent"
    if not built_tui.is_file():
        console.print(f"[red]cargo produced no {built_tui}[/red]")
        raise typer.Exit(1)
    tui.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built_tui, tui)
    tui.chmod(0o755)
    console.print(f"[green]✓[/green] TUI at [cyan]{short(tui)}[/cyan]")

    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text(launcher_text())
    launcher.chmod(0o755)
    console.print(f"[green]✓[/green] launcher at [cyan]{short(launcher)}[/cyan]")

    if use_deb:
        # The package ships /usr/share/applications/crow.desktop. A user-level
        # entry of the same name WINS in the menu and points at the prefix copy,
        # so the right move here is to delete the stale one, not write a new one.
        if desktop.exists():
            desktop.unlink()
            console.print(f"[green]✓[/green] removed the user-level entry that shadowed the package's: [cyan]{short(desktop)}[/cyan]")
    elif not no_desktop:
        icon = share / IDE_SUBDIR / "resources" / "app" / "resources" / "linux" / "code.png"
        desktop.parent.mkdir(parents=True, exist_ok=True)
        desktop.write_text(desktop_text(launcher, icon if icon.is_file() else None))
        console.print(f"[green]✓[/green] desktop entry at [cyan]{short(desktop)}[/cyan]")

    console.print("\n[bold green]crow is installed[/bold green]")
    if use_deb:
        console.print("  [dim]system-wide: /usr/share/crow (+ web), /usr/bin/crow, /usr/bin/crow-web[/dim]")
    console.print("  [cyan]crow[/cyan]           the desktop IDE")
    if not no_web:
        console.print("  [cyan]crow serve-web[/cyan] the IDE in a browser, via the IDE's own CLI")
    console.print("  [cyan]crow agent[/cyan]     the crow agent TUI")
    if shutil.which("crow") != str(launcher):
        console.print(f"[yellow]note:[/yellow] {launcher.parent} is not first on PATH — `crow` may resolve elsewhere")
