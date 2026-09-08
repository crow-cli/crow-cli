"""Source helpers: `crow-cli init` clones crow; spawn strings for crow's agent.

``crow-cli init`` leaves a checkout of the repo at
``<config_dir>/src/crow-cli`` (plus the site repo and the global skill), so a
``git pull`` there is an upgrade. The checkout is never loaded implicitly: it
is just a directory an ``agent_servers`` entry may point at (see
crow_cli.tui.agent_servers) — one of potentially many agents, nothing special.

:func:`spawn_command` builds the launch string for crow's OWN agent, and it is
always the code that is actually running: a frozen build's ``acp``
subcommand, or this interpreter via ``-m crow_cli.agent.main``. No checkout
preference, no re-exec, no behind-the-scenes redirection.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

from crow_cli.config.config import get_default_config_dir

CROW_REPO = "https://github.com/crow-cli/crow-cli"
SITE_REPO = "https://github.com/crow-cli/crow-cli.github.io"
BRANCH = "main"

#: The map skill, versioned in the repo at ``skills/crow-cli`` and installed
#: globally by init. Global because it is the BIOS: when a spawn is broken,
#: the agent that fixes it cannot fetch the skill from the broken thing it
#: is repairing.
SKILL_NAME = "crow-cli"


class SourceError(Exception):
    """A git/uv step failed. Callers report it; init does not abort on it."""


# ---------------------------------------------------------------------------
# Where things live
# ---------------------------------------------------------------------------


def src_dir(config_dir: Path | str | None = None) -> Path:
    """``<config_dir>/src`` — the home of the cloned repositories."""
    return get_default_config_dir(config_dir) / "src"


def skills_dir(config_dir: Path | str | None = None) -> Path:
    """The user-level skills root: a SIBLING of the config dir under ~/.agents."""
    return get_default_config_dir(config_dir).parent / "skills"


def global_checkout(config_dir: Path | str | None = None) -> Path:
    """``<config_dir>/src/crow-cli`` — the checkout the TUI spawns by default."""
    return src_dir(config_dir) / "crow-cli"


def site_checkout(config_dir: Path | str | None = None) -> Path:
    """``<config_dir>/src/crow-cli.github.io`` — the skills/docs source."""
    return src_dir(config_dir) / "crow-cli.github.io"


def is_checkout(path: Path | str) -> bool:
    """True when ``path`` looks like a runnable crow-cli source tree."""
    path = Path(path)
    return (path / "pyproject.toml").is_file()


def default_agent_server_entry(config_dir: Path | str | None = None) -> dict:
    """The ``agent_servers`` entry init writes for the checkout, as data.

    The explicit route for what used to be implicit: bare `crow-cli` launches
    the TOP entry, so init leaves one named ``crow-cli`` that runs
    ``uv --project <checkout> run crow-cli acp``. An absolute path, because
    the TUI shell-quotes argv and a quoted ``~`` would never expand.
    """
    return {
        "type": "custom",
        "command": "uv",
        "args": [
            "--project",
            str(global_checkout(config_dir)),
            "run",
            "crow-cli",
            "acp",
        ],
    }


# ---------------------------------------------------------------------------
# Crow's own spawn string
# ---------------------------------------------------------------------------


def uv_available() -> bool:
    return shutil.which("uv") is not None


def spawn_command(flags: Iterable[str] = ()) -> tuple[str, str]:
    """Crow's own agent subprocess launch string, given its ``acp`` flags.

    Returns ``(command, kind)`` where ``kind`` is ``"binary"`` (a frozen
    build's own ``acp`` subcommand) or ``"module"`` (this interpreter,
    ``-m crow_cli.agent.main``, which is the agent's argparse entry and takes
    no subcommand). Always the code that is actually running: pointing at a
    source checkout is an ``agent_servers`` entry the user writes, never
    something crow does behind their back.
    """
    flags = [str(a) for a in flags]
    quoted = (" " + " ".join(shlex.quote(a) for a in flags)) if flags else ""

    if getattr(sys, "frozen", False):
        return f"{shlex.quote(sys.executable)} acp{quoted}", "binary"
    return f"{shlex.quote(sys.executable)} -m crow_cli.agent.main{quoted}", "module"


# ---------------------------------------------------------------------------
# init: clone, sync, install the skill
# ---------------------------------------------------------------------------


def _run(argv: list[str], cwd: Path | None = None) -> str:
    """Run a subprocess, raising SourceError with its stderr on failure."""
    proc = subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        raise SourceError(f"{' '.join(argv)}: {detail}")
    return (proc.stdout or "").strip()


def clone_or_update(repo: str, dest: Path) -> str:
    """Clone ``repo`` into ``dest``, or fast-forward it if it is already there.

    Returns a one-word status: ``cloned``, ``updated``, ``offline`` (an existing
    checkout whose fetch failed — still usable) or ``dirty`` (an existing
    checkout with local changes, left alone).
    """
    dest = Path(dest)
    if not (dest / ".git").is_dir():
        if dest.exists() and any(dest.iterdir()):
            raise SourceError(f"{dest} exists and is not a git checkout")
        dest.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "--branch", BRANCH, repo, str(dest)])
        return "cloned"

    if _run(["git", "status", "--porcelain"], cwd=dest):
        return "dirty"
    try:
        _run(["git", "pull", "--ff-only", "origin", BRANCH], cwd=dest)
    except SourceError:
        return "offline"
    return "updated"


def sync_env(checkout: Path) -> None:
    """Pre-create the checkout's venv so the first spawn is not a dep install."""
    _run(["uv", "sync"], cwd=Path(checkout))


def install_skill(checkout: Path | str, skills_root: Path | str) -> Path | None:
    """Copy the repo's ``skills/crow-cli`` into the global skills root.

    The skill is versioned inside the crow-cli repo so it evolves with the
    code; installing it is a copy, and publishing it to crow-ai.dev is
    ``sync-skills.py`` in the site checkout. Returns the installed SKILL.md,
    or None when the checkout does not carry one.
    """
    source = Path(checkout) / "skills" / SKILL_NAME
    if not (source / "SKILL.md").is_file():
        return None
    target = Path(skills_root) / SKILL_NAME
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return target / "SKILL.md"


def bootstrap(
    config_dir: Path | str | None = None,
    *,
    sync: bool = True,
    log: Callable[[str], None] | None = None,
) -> dict[str, object]:
    """The source step of ``crow-cli init``: clone, sync, install the skill.

    Clones crow-cli and crow-cli.github.io into ``<config_dir>/src``, runs
    ``uv sync`` in the crow-cli checkout so the first agent spawn is instant,
    and installs the map skill globally.

    Never raises: a network blip must not throw away the config init just
    wrote. Failures land in the returned ``errors`` list, and ``log`` (if
    given) is called with a line per outcome.
    """
    config_dir = get_default_config_dir(config_dir)
    report: dict[str, object] = {"checkouts": {}, "errors": [], "skill": None, "synced": False}
    errors: list[str] = report["errors"]  # type: ignore[assignment]

    def note(line: str) -> None:
        if log is not None:
            log(line)

    if not shutil.which("git"):
        errors.append("`git` is not on PATH — cannot clone the source checkout.")
        note("[red]✗[/red] git not found; skipping the source checkout")
        return report

    for repo, dest, label in (
        (CROW_REPO, global_checkout(config_dir), "crow-cli"),
        (SITE_REPO, site_checkout(config_dir), "crow-cli.github.io"),
    ):
        try:
            status = clone_or_update(repo, dest)
        except SourceError as error:
            errors.append(f"{label}: {error}")
            note(f"[red]✗[/red] {label}: {error}")
            continue
        report["checkouts"][label] = str(dest)  # type: ignore[index]
        note(f"[green]✓[/green] {label} [dim]{status}[/dim] → [cyan]{dest}[/cyan]")

    checkout = global_checkout(config_dir)
    if is_checkout(checkout):
        if sync:
            if not uv_available():
                errors.append("`uv` is not on PATH — cannot pre-create the source venv.")
                note("[red]✗[/red] uv not found; the first agent spawn will need it")
            else:
                try:
                    sync_env(checkout)
                    report["synced"] = True
                    note("[green]✓[/green] source venv [dim]synced[/dim]")
                except SourceError as error:
                    errors.append(f"uv sync: {error}")
                    note(f"[red]✗[/red] uv sync: {error}")

        try:
            installed = install_skill(checkout, skills_dir(config_dir))
        except OSError as error:
            errors.append(f"skill install: {error}")
            note(f"[red]✗[/red] skill install: {error}")
        else:
            if installed is None:
                note(f"[yellow]![/yellow] {checkout} carries no skills/{SKILL_NAME}")
            else:
                report["skill"] = str(installed)
                note(f"[green]✓[/green] {SKILL_NAME} skill → [cyan]{installed.parent}[/cyan]")

    return report
