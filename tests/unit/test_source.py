"""Source helpers: checkout paths, crow's own spawn string, init machinery.

Real code paths — real directory trees on disk. No mocks. The rule that
matters: crow's own agent is ALWAYS the code that is running — a source
checkout is something an ``agent_servers`` entry points at, never something
crow prefers behind the user's back. The clone/sync half lives in
test_init_source.py.
"""

import sys
from pathlib import Path

import pytest

from crow_cli.cli import source
from crow_cli.tui.agent_servers import resolve_agent_server


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


# ---------------------------------------------------------------------------
# Crow's own spawn string
# ---------------------------------------------------------------------------


def test_spawn_command_runs_the_code_that_is_running():
    command, kind = source.spawn_command(["--model", "m"])
    assert kind == ("binary" if getattr(sys, "frozen", False) else "module")
    assert "--model m" in command
    # the module entry is argparse, not typer: it takes no `acp` subcommand
    if kind == "module":
        assert command.endswith("-m crow_cli.agent.main --model m")


def test_spawn_command_quotes_flags_exactly_once():
    command, _ = source.spawn_command(
        ["--config-dir", "/tmp/a b", "--model", "qwen max"]
    )
    assert "'/tmp/a b'" in command
    assert "'qwen max'" in command
    # no double-quoting artifacts
    assert "''" not in command


def test_spawn_command_ignores_a_checkout(config_dir: Path):
    """Even with a checkout present, crow's own agent is the running code."""
    _checkout(source.global_checkout(config_dir))
    command, kind = source.spawn_command(["--model", "m"])
    assert "uv" not in command
    assert str(source.global_checkout(config_dir)) not in command
    assert kind == ("binary" if getattr(sys, "frozen", False) else "module")


def test_default_agent_server_entry_points_at_the_checkout(config_dir: Path):
    """The entry init writes — and it resolves through the TUI's machinery."""
    entry = source.default_agent_server_entry(config_dir)
    assert entry == {
        "type": "custom",
        "command": "uv",
        "args": [
            "--project",
            str(config_dir / "src" / "crow-cli"),
            "run",
            "crow-cli",
            "acp",
        ],
    }

    agent = resolve_agent_server("crow-cli", {"crow-cli": entry})
    assert f"--project {config_dir / 'src' / 'crow-cli'}" in agent["run_command"]["*"]
    assert agent["identity"] == "crow-cli"


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
