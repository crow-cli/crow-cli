"""Source-first distribution: crow-cli clones itself, then runs from the clone.

There is no non-source distribution. ``uv tool install crow-cli && crow-cli
init`` leaves a checkout of the repo at ``<config_dir>/src/crow-cli``, and from
then on the TUI spawns ``uv --project <checkout> run crow-cli acp``. A
``git pull`` in the checkout IS the upgrade and pure-Python changes are live
with no reinstall: the installed tool is the bootloader, the checkout is the
program.

Three scopes, resolved project-first the way :func:`crow_cli.agent.prompt.
skill_roots` resolves skills — nearest project scope wins, the user scope is
the fallback:

    <cwd>/.agents/crow/agent.py       a project's own agent (repl-agent pattern)
    <cwd>/.agents/crow/src/crow-cli   a project's own checkout -> re-exec into it
    <config_dir>/src/crow-cli         the global checkout -> the TUI's default

``crow-cli acp`` re-execs into the project scope when there is one, so the
agent that answers is the one the repo ships. :data:`REEXEC_ENV` is the
sentinel that stops the re-exec'd child from re-exec'ing again; ``--system``
opts out of the whole thing and runs the code you actually invoked.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

from crow_cli.agent.prompt import ancestors
from crow_cli.config.config import get_default_config_dir

CROW_REPO = "https://github.com/crow-cli/crow-cli"
SITE_REPO = "https://github.com/crow-cli/crow-cli.github.io"
BRANCH = "main"

#: Set on the child before exec'ing into a project scope. Its presence means
#: "this process IS the re-exec", so it must not look for another one.
REEXEC_ENV = "CROW_ACP_REEXEC"

#: The map skill, versioned in the repo at ``skills/crow-cli`` and installed
#: globally by init. Global because it is the BIOS: when a project-level spawn
#: is broken, the agent that fixes it cannot fetch the skill from the broken
#: thing it is repairing.
SKILL_NAME = "crow-cli"

PROJECT_SCOPE = Path(".agents") / "crow"


class SourceError(Exception):
    """A git/uv step failed. Callers report it; init does not abort on it."""


def _warn(message: str) -> None:
    """A fallback is about to happen. Say so — never degrade silently."""
    print(f"crow-cli: {message}", file=sys.stderr)


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


def project_scope(cwd: Path | str) -> Path | None:
    """The nearest ``.agents/crow`` from ``cwd`` up to the git root, if any.

    Same walk as :func:`crow_cli.agent.prompt.skill_roots`: a project scope
    travels with the repo, and running crow from a subdirectory of that repo
    still finds it.
    """
    for directory in ancestors(Path(cwd)):
        scope = directory / PROJECT_SCOPE
        if scope.is_dir():
            return scope
    return None


def project_agent_script(cwd: Path | str) -> Path | None:
    """``<cwd>/.agents/crow/agent.py`` — a project's own agent, if it has one.

    The repl-agent pattern: a script that imports ``crow_cli``, mutates
    ``Config``, wires its own hooks and calls ``run_agent``. Different
    compaction is a different creature, and this is how a repo gets one.
    """
    scope = project_scope(cwd)
    if scope is None:
        return None
    script = scope / "agent.py"
    return script if script.is_file() else None


def project_checkout(cwd: Path | str) -> Path | None:
    """``<cwd>/.agents/crow/src/crow-cli`` when it is a usable source tree."""
    scope = project_scope(cwd)
    if scope is None:
        return None
    checkout = scope / "src" / "crow-cli"
    return checkout if is_checkout(checkout) else None


# ---------------------------------------------------------------------------
# Spawning from a checkout
# ---------------------------------------------------------------------------


def uv_available() -> bool:
    return shutil.which("uv") is not None


def uv_argv(checkout: Path | str, args: Iterable[str] = ()) -> list[str]:
    """``uv --project <checkout> run crow-cli <args>`` as an argv list."""
    return ["uv", "--project", str(checkout), "run", "crow-cli", *args]


def spawn_command(
    flags: Iterable[str] = (),
    *,
    config_dir: Path | str | None = None,
    system: bool = False,
) -> tuple[str, str]:
    """How the TUI should launch crow's agent, given its ``acp`` flags.

    Returns ``(command, kind)`` where ``kind`` is ``"source"`` (spawned from
    the global checkout via uv), ``"binary"`` (a frozen build's own ``acp``
    subcommand) or ``"module"`` (this interpreter, ``-m crow_cli.agent.main``,
    which is the agent's argparse entry and takes no subcommand).

    The checkout wins by default — that is the whole point of a source-first
    distribution. ``system=True``, a missing checkout, or no ``uv`` on PATH
    falls back to the code that is actually running, and every fallback is
    reported on stderr rather than silent.
    """
    flags = [str(a) for a in flags]
    quoted = (" " + " ".join(shlex.quote(a) for a in flags)) if flags else ""

    if not system:
        checkout = global_checkout(config_dir)
        if is_checkout(checkout):
            if uv_available():
                return (
                    " ".join(shlex.quote(a) for a in uv_argv(checkout, ["acp", *flags])),
                    "source",
                )
            _warn(
                f"{checkout} is a source checkout but `uv` is not on PATH — "
                "falling back to the installed crow-cli. Install uv, or pass "
                "--system to make this the intended behaviour."
            )
        else:
            _warn(
                f"No source checkout at {checkout} — running the installed "
                "crow-cli. `crow-cli init` clones it; --system silences this."
            )

    if getattr(sys, "frozen", False):
        return f"{shlex.quote(sys.executable)} acp{quoted}", "binary"
    return f"{shlex.quote(sys.executable)} -m crow_cli.agent.main{quoted}", "module"


def reexec_into_project(cwd: Path | str, argv: list[str]) -> bool:
    """Re-exec ``crow-cli acp`` into the project's own agent, if it has one.

    ``argv`` is ``sys.argv[1:]`` — it starts with ``acp``. Returns False when
    there is nothing to re-exec into, when this process is already a re-exec,
    or when the attempt failed (loudly, on stderr) so the caller carries on
    in-process. A successful exec replaces this process and never returns.
    """
    if os.environ.get(REEXEC_ENV):
        return False

    script = project_agent_script(cwd)
    checkout = project_checkout(cwd)
    if script is None and checkout is None:
        return False

    if script is not None and checkout is not None:
        # The project's agent, running inside the project's own environment.
        target = ["uv", "--project", str(checkout), "run", "python", str(script), *argv[1:]]
    elif checkout is not None:
        target = uv_argv(checkout, argv)
    else:
        # A bare agent.py with no checkout: run it with this interpreter, which
        # can already import crow_cli because it is running it.
        target = [sys.executable, str(script), *argv[1:]]

    if target[0] == "uv" and not uv_available():
        _warn(
            f"Project agent at {script or checkout} needs `uv`, which is not on "
            "PATH — running the installed crow-cli instead. Pass --system to "
            "make that the intended behaviour."
        )
        return False

    os.environ[REEXEC_ENV] = "1"
    try:
        os.execvp(target[0], target)
    except OSError as error:
        # We did not exec, so we are not a re-exec: do not leave the sentinel
        # behind to stop the caller from trying anything else.
        del os.environ[REEXEC_ENV]
        _warn(
            f"Could not re-exec into the project agent ({' '.join(target)}): "
            f"{error}. Running the installed crow-cli instead."
        )
        return False
    raise AssertionError("execvp returned")  # unreachable


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
