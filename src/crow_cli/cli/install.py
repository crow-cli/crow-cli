"""Install commands for Crow Desktop IDE."""

import io
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

app = typer.Typer(help="Install Crow Desktop IDE")
console = Console()

GITHUB_REPO = "odellus/sidex"
API_BASE = f"https://api.github.com/repos/{GITHUB_REPO}"
DOWNLOAD_BASE = f"https://github.com/{GITHUB_REPO}/releases/download"


def get_system_info() -> tuple[str, str]:
    """Detect OS and architecture, return (os, arch) tuple."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    # Map architecture names
    arch_map = {
        "x86_64": "amd64",
        "amd64": "amd64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    arch = arch_map.get(machine, machine)

    # Validate OS
    if system not in ("linux", "darwin", "windows"):
        console.print(f"[red]Unsupported OS: {system}[/red]")
        console.print("[yellow]Currently only Linux is supported[/yellow]")
        raise typer.Exit(1)

    if system != "linux":
        console.print(f"[red]{system.title()} builds are not yet available[/red]")
        console.print("[dim]Linux (amd64/arm64) is currently supported[/dim]")
        raise typer.Exit(1)

    return system, arch


def get_latest_release() -> dict:
    """Fetch latest release info from GitHub API."""
    url = f"{API_BASE}/releases/latest"
    try:
        response = httpx.get(url, timeout=10, follow_redirects=True)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to fetch latest release: {e}[/red]")
        raise typer.Exit(1)


def find_asset(assets: list[dict], arch: str) -> Optional[dict]:
    """Find the appropriate .deb asset for the architecture."""
    for asset in assets:
        name = asset["name"]
        if name.endswith(f"_{arch}.deb"):
            return asset
    return None


def download_asset(url: str, dest: Path) -> None:
    """Download a file with progress bar."""
    with httpx.stream("GET", url, follow_redirects=True, timeout=300) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length", 0))

        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Downloading", total=total)

            with open(dest, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=8192):
                    f.write(chunk)
                    progress.update(task, advance=len(chunk))


def deb_data_tar(deb_path: Path) -> bytes:
    """Return the data.tar.* payload of a .deb.

    A .deb is an ar archive (debian-binary, control.tar.*, data.tar.*); parsing
    it here avoids needing dpkg, ar or bsdtar on non-Debian systems.
    """
    with deb_path.open("rb") as f:
        if f.read(8) != b"!<arch>\n":
            raise ValueError(f"{deb_path.name} is not a .deb archive")
        while header := f.read(60):
            name = header[:16].decode().strip().rstrip("/")
            size = int(header[48:58])
            if name.startswith("data.tar"):
                return f.read(size)
            f.seek(size + size % 2, os.SEEK_CUR)  # members are 2-byte aligned
    raise ValueError(f"{deb_path.name} has no data.tar member")


def missing_libraries(binary: Path) -> list[str]:
    """Shared libraries the dynamic linker can't resolve for `binary`."""
    result = subprocess.run(
        ["ldd", str(binary)], capture_output=True, text=True, check=True
    )
    return [line.split()[0] for line in result.stdout.splitlines() if "not found" in line]


def install_local(deb_path: Path, prefix: Path) -> bool:
    """Install the .deb's usr/ tree for the current user, without root or dpkg.

    Layout as Zed's Linux installer: prefix/crow.app/{bin,lib,share}, a
    prefix/bin/Crow symlink and a desktop entry. Tauri finds its resources at
    <real exe dir>/../lib/Crow, so the tree stays intact.
    """
    console.print(f"\n[cyan]Installing {deb_path.name}...[/cyan]")
    app_dir = prefix / "crow.app"
    exe = app_dir / "bin" / "Crow"
    prefix.mkdir(parents=True, exist_ok=True)
    for stale in prefix.glob(".crow.app-*"):  # staging left by a killed run
        shutil.rmtree(stale)

    # Stage beside app_dir so the swap is a rename; leaving the block deletes
    # staging along with the replaced install.
    with tempfile.TemporaryDirectory(dir=prefix, prefix=".crow.app-") as tmp:
        staging = Path(tmp)
        with tarfile.open(fileobj=io.BytesIO(deb_data_tar(deb_path))) as tar:
            tar.extractall(staging, filter="data")
        # Checked before the current install is touched: the app can't start without them.
        if missing := missing_libraries(staging / "usr" / "bin" / "Crow"):
            console.print(
                f"[red]Missing system libraries: {', '.join(missing)}[/red]\n"
                "Install WebKitGTK 4.1 (Arch: webkit2gtk-4.1) and re-run."
            )
            return False
        if app_dir.exists():
            app_dir.rename(staging / "replaced")
        (staging / "usr").rename(app_dir)

    link = prefix / "bin" / "Crow"
    link.parent.mkdir(exist_ok=True)
    link.unlink(missing_ok=True)
    link.symlink_to(exe)

    # Absolute paths: the session PATH may lack ~/.local/bin, and the icon
    # isn't in an icon theme dir.
    entry = (app_dir / "share/applications/Crow.desktop").read_text()
    icon = app_dir / "share/icons/hicolor/256x256@2/apps/Crow.png"
    desktop = prefix / "share/applications/Crow.desktop"
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(
        entry.replace("Exec=Crow", f'Exec="{exe}"').replace("Icon=Crow", f"Icon={icon}")
    )
    console.print(f"[green]✓ Crow Desktop installed to {app_dir}[/green]")
    return True


def install_deb(deb_path: Path) -> bool:
    """Install a .deb package using dpkg."""
    console.print(f"\n[cyan]Installing {deb_path.name}...[/cyan]")

    # Check if we have sudo
    has_sudo = subprocess.run(
        ["which", "sudo"], capture_output=True
    ).returncode == 0

    cmd = ["sudo", "dpkg", "-i", str(deb_path)] if has_sudo else ["dpkg", "-i", str(deb_path)]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            console.print(f"[red]Installation failed:[/red]")
            console.print(result.stderr)

            # Try to fix dependencies if needed
            if "dependency problems" in result.stderr.lower():
                console.print("\n[yellow]Attempting to fix dependencies...[/yellow]")
                fix_cmd = (
                    ["sudo", "apt-get", "install", "-f", "-y"]
                    if has_sudo
                    else ["apt-get", "install", "-f", "-y"]
                )
                subprocess.run(fix_cmd, check=True)
                console.print("[green]Dependencies fixed![/green]")
                return True
            return False

        console.print("[green]✓ Crow Desktop installed successfully![/green]")
        return True

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Installation failed: {e}[/red]")
        return False
    except FileNotFoundError:
        console.print("[red]dpkg not found. Are you on a Debian-based system?[/red]")
        return False


@app.command()
def desktop(
    version: Optional[str] = typer.Option(
        None, "--version", "-v", help="Specific version to install (e.g., v0.1.6)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be installed without installing"
    ),
):
    """
    Install Crow Desktop IDE.

    Detects your system architecture and downloads the appropriate package
    from the latest GitHub release.
    """
    console.print("\n[bold magenta]🪶 Crow Desktop Installer[/bold magenta]\n")

    # Detect system
    os_name, arch = get_system_info()
    console.print(f"System: [cyan]{os_name}[/cyan] / [cyan]{arch}[/cyan]")

    # Get release info
    if version:
        tag = version if version.startswith("v") else f"v{version}"
        console.print(f"Installing specific version: [cyan]{tag}[/cyan]")
        release_url = f"{API_BASE}/releases/tags/{tag}"
        try:
            response = httpx.get(release_url, timeout=10, follow_redirects=True)
            response.raise_for_status()
            release = response.json()
        except httpx.HTTPError:
            console.print(f"[red]Version {tag} not found[/red]")
            raise typer.Exit(1)
    else:
        console.print("Fetching latest release...")
        release = get_latest_release()
        tag = release["tag_name"]

    console.print(f"Release: [green]{tag}[/green]")

    # Find appropriate asset
    assets = release.get("assets", [])
    asset = find_asset(assets, arch)

    if not asset:
        console.print(f"[red]No {arch} package found in release {tag}[/red]")
        console.print("[dim]Available assets:[/dim]")
        for a in assets[:10]:
            console.print(f"  - {a['name']}")
        raise typer.Exit(1)

    console.print(f"Package: [cyan]{asset['name']}[/cyan]")
    console.print(f"Size: [cyan]{asset['size'] / 1024 / 1024:.1f} MB[/cyan]")

    if dry_run:
        console.print("\n[yellow]Dry run - not downloading[/yellow]")
        console.print(f"URL: {asset['browser_download_url']}")
        return

    # Download
    with tempfile.TemporaryDirectory() as tmpdir:
        dest = Path(tmpdir) / asset["name"]

        try:
            download_asset(asset["browser_download_url"], dest)
        except httpx.HTTPError as e:
            console.print(f"\n[red]Download failed: {e}[/red]")
            raise typer.Exit(1)

        console.print(f"\n[green]✓ Downloaded to {dest}[/green]")

        # Install: dpkg/apt on Debian and derivatives; elsewhere (Arch, Fedora, ...)
        # unpack the same .deb into ~/.local. Keyed on apt-get, not dpkg,
        # because Arch can have dpkg installed.
        if shutil.which("apt-get"):
            installed = install_deb(dest)
        else:
            installed = install_local(dest, Path.home() / ".local")
        if not installed:
            console.print("\n[red]Installation failed[/red]")
            raise typer.Exit(1)

    console.print(
        "\n[bold green]🎉 Crow Desktop is ready![/bold green]\n"
        "Run [cyan]Crow[/cyan] or find it in your applications menu."
    )


@app.command()
def check():
    """Check for available Crow Desktop releases."""
    console.print("\n[bold magenta]🪶 Crow Release Info[/bold magenta]\n")

    release = get_latest_release()

    console.print(f"[bold]Latest Release:[/bold] {release['tag_name']}")
    console.print(f"[bold]Published:[/bold] {release['published_at']}")
    console.print(f"[bold]URL:[/bold] {release['html_url']}")

    if release.get("body"):
        console.print(f"\n[bold]Release Notes:[/bold]")
        console.print(release["body"][:500] + "..." if len(release["body"]) > 500 else release["body"])

    console.print(f"\n[bold]Available Packages:[/bold]")
    for asset in release.get("assets", []):
        size_mb = asset["size"] / 1024 / 1024
        console.print(f"  • {asset['name']} ({size_mb:.1f} MB)")
