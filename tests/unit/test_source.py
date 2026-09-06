"""Source-first distribution: checkout resolution, spawn command, project re-exec.

Real code paths — real directory trees on disk and a real ``os.execvp`` in a
real subprocess. No mocks: the resolution rules ARE the feature, so the tests
build the tree and ask. The clone/sync half lives in test_init_source.py.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from crow_cli.cli import source


def _checkout(path: Path) -> Path:
    """A directory that passes is_checkout — a pyproject and nothing else."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text('[project]\nname = "crow-cli"\n')
    return path


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    d = tmp_path / "crow"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Where things live
# ---------------------------------------------------------------------------


def test_everything_hangs_off_the_config_dir(config_dir: Path):
    assert source.src_dir(config_dir) == config_dir / "src"
    assert source.global_checkout(config_dir) == config_dir / "src" / "crow-cli"
    assert source.site_checkout(config_dir) == config_dir / "src" / "crow-cli.github.io"
    # skills are a SIBLING of the config dir under ~/.agents, never inside it
    assert source.skills_dir(config_dir) == config_dir.parent / "skills"


def test_is_checkout_needs_a_pyproject(tmp_path: Path):
    assert not source.is_checkout(tmp_path / "nope")
    (tmp_path / "empty").mkdir()
    assert not source.is_checkout(tmp_path / "empty")
    assert source.is_checkout(_checkout(tmp_path / "real"))


def test_project_scope_walks_up_to_the_git_root(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    scope = repo / ".agents" / "crow"
    scope.mkdir(parents=True)
    nested = repo / "crates" / "tui" / "src"
    nested.mkdir(parents=True)

    assert source.project_scope(nested) == scope
    assert source.project_scope(repo) == scope


def test_project_scope_stops_at_the_git_root(tmp_path: Path):
    # A scope ABOVE the repository is somebody else's workspace, not ours.
    (tmp_path / ".agents" / "crow").mkdir(parents=True)
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    assert source.project_scope(repo) is None


def test_project_scope_outside_a_repo_is_just_cwd(tmp_path: Path):
    loose = tmp_path / "loose"
    loose.mkdir()
    (tmp_path / ".agents" / "crow").mkdir(parents=True)
    assert source.project_scope(loose) is None


def test_nearest_project_scope_wins(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    outer = repo / ".agents" / "crow"
    outer.mkdir(parents=True)
    inner = repo / "sub" / ".agents" / "crow"
    inner.mkdir(parents=True)
    assert source.project_scope(repo / "sub") == inner


def test_project_agent_script_and_checkout(tmp_path: Path):
    assert source.project_agent_script(tmp_path) is None
    assert source.project_checkout(tmp_path) is None

    scope = tmp_path / ".agents" / "crow"
    scope.mkdir(parents=True)
    assert source.project_agent_script(tmp_path) is None

    (scope / "agent.py").write_text("# the repl-agent pattern\n")
    assert source.project_agent_script(tmp_path) == scope / "agent.py"

    # a src/crow-cli directory is not a checkout until it has a pyproject
    (scope / "src" / "crow-cli").mkdir(parents=True)
    assert source.project_checkout(tmp_path) is None
    _checkout(scope / "src" / "crow-cli")
    assert source.project_checkout(tmp_path) == scope / "src" / "crow-cli"


# ---------------------------------------------------------------------------
# Spawning from a checkout
# ---------------------------------------------------------------------------


def test_uv_argv(config_dir: Path):
    assert source.uv_argv(config_dir / "src" / "crow-cli", ["acp", "--model", "m"]) == [
        "uv",
        "--project",
        str(config_dir / "src" / "crow-cli"),
        "run",
        "crow-cli",
        "acp",
        "--model",
        "m",
    ]


def test_spawn_command_prefers_the_source_checkout(config_dir: Path):
    checkout = _checkout(source.global_checkout(config_dir))
    command, kind = source.spawn_command(["--model", "m"], config_dir=config_dir)
    assert kind == "source"
    assert command == f"uv --project {checkout} run crow-cli acp --model m"


def test_spawn_command_quotes_flags_exactly_once(config_dir: Path):
    _checkout(source.global_checkout(config_dir))
    command, kind = source.spawn_command(
        ["--config-dir", "/tmp/a b", "--model", "qwen max"], config_dir=config_dir
    )
    assert kind == "source"
    assert "'/tmp/a b'" in command
    assert "'qwen max'" in command
    # no double-quoting artifacts
    assert "''" not in command


def test_spawn_command_system_runs_the_code_that_is_running(config_dir: Path):
    _checkout(source.global_checkout(config_dir))
    command, kind = source.spawn_command(["--model", "m"], config_dir=config_dir, system=True)
    assert kind == ("binary" if getattr(sys, "frozen", False) else "module")
    assert "uv" not in command
    assert "--model m" in command
    # the module entry is argparse, not typer: it takes no `acp` subcommand
    if kind == "module":
        assert command.endswith("-m crow_cli.agent.main --model m")


def test_spawn_command_falls_back_loudly_without_a_checkout(config_dir: Path, capsys):
    command, kind = source.spawn_command(config_dir=config_dir)
    assert kind == ("binary" if getattr(sys, "frozen", False) else "module")
    err = capsys.readouterr().err
    assert "No source checkout at" in err
    assert str(source.global_checkout(config_dir)) in err
    assert "--system" in err


def test_spawn_command_falls_back_loudly_without_uv(config_dir: Path, monkeypatch, capsys):
    checkout = _checkout(source.global_checkout(config_dir))
    monkeypatch.setattr(source, "uv_available", lambda: False)
    command, kind = source.spawn_command(config_dir=config_dir)
    assert kind == ("binary" if getattr(sys, "frozen", False) else "module")
    assert str(checkout) not in command
    err = capsys.readouterr().err
    assert "`uv` is not on PATH" in err


# ---------------------------------------------------------------------------
# The project re-exec
# ---------------------------------------------------------------------------


def test_reexec_is_a_noop_without_a_project_scope(tmp_path: Path):
    assert source.reexec_into_project(tmp_path, ["acp"]) is False


def test_reexec_honours_the_sentinel(tmp_path: Path, monkeypatch):
    scope = tmp_path / ".agents" / "crow"
    scope.mkdir(parents=True)
    (scope / "agent.py").write_text("")
    monkeypatch.setenv(source.REEXEC_ENV, "1")

    def boom(*_a, **_k):  # pragma: no cover - must not be reached
        raise AssertionError("a re-exec looked for another re-exec")

    monkeypatch.setattr(os, "execvp", boom)
    assert source.reexec_into_project(tmp_path, ["acp"]) is False


def test_reexec_falls_back_loudly_when_uv_is_missing(tmp_path: Path, monkeypatch, capsys):
    scope = tmp_path / ".agents" / "crow"
    _checkout(scope / "src" / "crow-cli")
    monkeypatch.setattr(source, "uv_available", lambda: False)

    def boom(*_a, **_k):  # pragma: no cover - must not be reached
        raise AssertionError("exec'd without uv")

    monkeypatch.setattr(os, "execvp", boom)
    assert source.reexec_into_project(tmp_path, ["acp"]) is False
    assert "needs `uv`" in capsys.readouterr().err


def test_reexec_reports_a_failed_exec_and_lets_the_caller_carry_on(
    tmp_path: Path, monkeypatch, capsys
):
    scope = tmp_path / ".agents" / "crow"
    scope.mkdir(parents=True)
    script = scope / "agent.py"
    script.write_text("")
    # No checkout, so the target is [sys.executable, script] — make the exec
    # fail the way a missing interpreter does.
    monkeypatch.setattr(source.sys, "executable", "/nonexistent/python")
    assert source.reexec_into_project(tmp_path, ["acp"]) is False
    assert "Could not re-exec into the project agent" in capsys.readouterr().err


def test_reexec_really_replaces_the_process(tmp_path: Path):
    """The real thing: a project agent.py, an actual execvp, in a subprocess.

    The driver calls reexec_into_project and then prints a line that must
    NEVER appear — if exec worked, the process is the project's agent.
    """
    scope = tmp_path / "project" / ".agents" / "crow"
    scope.mkdir(parents=True)
    (scope / "agent.py").write_text(
        textwrap.dedent(
            """
            import os, sys
            print("PROJECT-AGENT", " ".join(sys.argv[1:]))
            print("SENTINEL=" + os.environ.get("CROW_ACP_REEXEC", "unset"))
            """
        )
    )
    driver = tmp_path / "driver.py"
    driver.write_text(
        textwrap.dedent(
            f"""
            import sys
            from pathlib import Path
            from crow_cli.cli.source import reexec_into_project
            reexec_into_project(Path({str(tmp_path / "project")!r}), sys.argv[1:])
            print("FELL-THROUGH")
            """
        )
    )

    proc = subprocess.run(
        [sys.executable, str(driver), "acp", "--model", "m"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert proc.returncode == 0, proc.stderr
    assert "FELL-THROUGH" not in proc.stdout
    assert "PROJECT-AGENT --model m" in proc.stdout
    # the sentinel rides into the child so it does not re-exec again
    assert "SENTINEL=1" in proc.stdout


# ---------------------------------------------------------------------------
# The skill install
# ---------------------------------------------------------------------------


def test_install_skill_copies_the_repo_skill(tmp_path: Path):
    checkout = _checkout(tmp_path / "checkout")
    skill = checkout / "skills" / "crow-cli"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: crow-cli\n---\n\nbody\n")
    (skill / "notes" / "deep").mkdir(parents=True)
    (skill / "notes" / "deep" / "extra.md").write_text("extra")

    installed = source.install_skill(checkout, tmp_path / "skills")

    assert installed == tmp_path / "skills" / "crow-cli" / "SKILL.md"
    assert installed.read_text().startswith("---\nname: crow-cli")
    assert (tmp_path / "skills" / "crow-cli" / "notes" / "deep" / "extra.md").read_text() == "extra"


def test_install_skill_replaces_a_stale_install(tmp_path: Path):
    checkout = _checkout(tmp_path / "checkout")
    skill = checkout / "skills" / "crow-cli"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("v2")

    root = tmp_path / "skills"
    (root / "crow-cli").mkdir(parents=True)
    (root / "crow-cli" / "SKILL.md").write_text("v1")
    (root / "crow-cli" / "OBSOLETE.md").write_text("gone in v2")

    source.install_skill(checkout, root)

    assert (root / "crow-cli" / "SKILL.md").read_text() == "v2"
    assert not (root / "crow-cli" / "OBSOLETE.md").exists()


def test_install_skill_returns_none_when_the_checkout_carries_no_skill(tmp_path: Path):
    checkout = _checkout(tmp_path / "checkout")
    assert source.install_skill(checkout, tmp_path / "skills") is None
    assert not (tmp_path / "skills").exists()
