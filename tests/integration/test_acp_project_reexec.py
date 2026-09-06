"""`crow-cli acp` re-execs into a project-level agent — the real CLI, spawned.

The unit tests build the trees and check the resolution rules. This drives the
actual command line: a real subprocess running ``-m crow_cli.cli.main acp``
with a real ``.agents/crow`` in its cwd. If the re-exec wiring in
``run_agentmain`` is missing, misplaced, or runs after something that blocks,
the project's agent never gets the stdio it owns and this fails.

No LLM, no network: the project agent is a three-line script that prints and
exits, which is exactly what the repl-agent pattern is allowed to be.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from crow_cli.cli import source

CLI = [sys.executable, "-m", "crow_cli.cli.main"]
MARKER = "PROJECT-AGENT-OWNS-STDIO"
TIMEOUT = 120


def _project(tmp_path: Path, agent_body: str) -> Path:
    """A project directory carrying its own agent at .agents/crow/agent.py."""
    project = tmp_path / "project"
    scope = project / ".agents" / "crow"
    scope.mkdir(parents=True)
    (scope / "agent.py").write_text(textwrap.dedent(agent_body))
    project.mkdir(exist_ok=True)
    return project


def _run_acp(project: Path, config_dir: Path, *extra: str) -> subprocess.CompletedProcess:
    """Run the real `crow-cli acp` in `project` with stdin closed.

    Stdin closed is the discriminator: a re-exec'd project agent prints its
    marker and exits 0, while the real agent has nothing to read and never
    prints the marker.
    """
    return subprocess.run(
        [*CLI, "acp", "--config-dir", str(config_dir), *extra],
        cwd=str(project),
        input="",
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never inherit a sentinel from the process running the tests."""
    monkeypatch.delenv(source.REEXEC_ENV, raising=False)


def test_acp_reexecs_into_the_project_agent(tmp_path: Path, clean_env: None):
    project = _project(
        tmp_path,
        f"""
            import os, sys
            print("{MARKER}", " ".join(sys.argv[1:]))
            print("SENTINEL=" + os.environ.get("{source.REEXEC_ENV}", "unset"))
            sys.exit(0)
        """,
    )

    proc = _run_acp(project, tmp_path / "crow", "--model", "m")

    assert MARKER in proc.stdout, f"the project agent never ran:\n{proc.stderr}"
    # the acp subcommand is consumed by the re-exec; the rest is forwarded
    assert "--model m" in proc.stdout
    # the sentinel rides along so the child does not go looking for another
    assert "SENTINEL=1" in proc.stdout
    assert proc.returncode == 0


def test_acp_system_skips_the_project_agent(tmp_path: Path, clean_env: None):
    project = _project(
        tmp_path,
        f"""
            print("{MARKER}")
            raise SystemExit(0)
        """,
    )

    proc = _run_acp(project, tmp_path / "crow", "--system")

    assert MARKER not in proc.stdout
    assert MARKER not in proc.stderr


def test_acp_without_a_project_scope_boots_normally(tmp_path: Path, clean_env: None):
    project = tmp_path / "project"
    project.mkdir()

    proc = _run_acp(project, tmp_path / "crow")

    # nothing to re-exec into, so this is the installed agent: it comes up on
    # stdio and, finding it closed, goes away — but it never printed the marker
    assert MARKER not in proc.stdout


def test_acp_sentinel_in_the_environment_stops_the_walk(tmp_path: Path, monkeypatch):
    project = _project(
        tmp_path,
        f"""
            print("{MARKER}")
            raise SystemExit(0)
        """,
    )
    monkeypatch.setenv(source.REEXEC_ENV, "1")

    proc = _run_acp(project, tmp_path / "crow")

    assert MARKER not in proc.stdout
