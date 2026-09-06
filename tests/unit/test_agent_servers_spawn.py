"""The TUI's launch string: which crow does `crow-cli` spawn?

Source-first means the checkout at <config_dir>/src/crow-cli wins by default
and `--system` is the opt-out. Real trees on disk, no mocks.
"""

import shlex
import sys
from pathlib import Path

import pytest

from crow_cli.tui.agent_servers import AgentServerError, crow_agent, resolve_agent_server


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    d = tmp_path / "crow"
    d.mkdir()
    return d


@pytest.fixture
def checkout(config_dir: Path) -> Path:
    tree = config_dir / "src" / "crow-cli"
    tree.mkdir(parents=True)
    (tree / "pyproject.toml").write_text('[project]\nname = "crow-cli"\n')
    return tree


def _installed_kind() -> str:
    return "binary" if getattr(sys, "frozen", False) else "module"


def test_crow_agent_spawns_the_source_checkout_by_default(checkout: Path, config_dir: Path):
    agent = crow_agent(config_dir=str(config_dir))

    command = agent["run_command"]["*"]
    assert command == f"uv --project {checkout} run crow-cli acp --config-dir {config_dir}"
    assert "the source checkout" in agent["help"]


def test_crow_agent_system_runs_the_installed_agent(checkout: Path, config_dir: Path):
    agent = crow_agent(config_dir=str(config_dir), system=True)

    command = agent["run_command"]["*"]
    assert "uv" not in command
    assert str(checkout) not in command
    assert command.startswith(shlex.quote(sys.executable))
    if _installed_kind() == "module":
        # the module entry is argparse and takes no `acp` subcommand
        assert "-m crow_cli.agent.main --config-dir" in command
    else:
        assert " acp --config-dir" in command
    assert "the installed crow-cli" in agent["help"]


def test_crow_agent_without_a_checkout_falls_back(checkout: Path, tmp_path: Path, capsys):
    bare = tmp_path / "bare"
    bare.mkdir()

    agent = crow_agent(config_dir=str(bare))

    assert "uv" not in agent["run_command"]["*"]
    assert "No source checkout at" in capsys.readouterr().err


def test_crow_agent_carries_model_and_config_file(checkout: Path, config_dir: Path):
    agent = crow_agent(
        model="alibaba:qwen3.8-max-preview",
        config_dir=str(config_dir),
        config_file="/tmp/my config.yaml",
    )

    command = agent["run_command"]["*"]
    assert command.endswith(
        f"acp --config-dir {config_dir} --config-file '/tmp/my config.yaml' "
        "--model alibaba:qwen3.8-max-preview"
    )
    # quoted exactly once, so the shell hands the agent one path with a space in it
    assert "'/tmp/my config.yaml'" in command
    assert shlex.split(command)[-3] == "/tmp/my config.yaml"


def test_resolve_agent_server_registry_threads_system(checkout: Path, config_dir: Path):
    servers = {"crow-cli": {"type": "registry", "default_config_options": {"model": "m"}}}

    from_source = resolve_agent_server("crow-cli", servers, config_dir=str(config_dir))
    from_system = resolve_agent_server(
        "crow-cli", servers, config_dir=str(config_dir), system=True
    )

    assert from_source["run_command"]["*"].startswith("uv --project")
    assert "uv" not in from_system["run_command"]["*"]
    assert from_system["run_command"]["*"].startswith(shlex.quote(sys.executable))
    # the entry's default model survived both ways
    assert "--model m" in from_source["run_command"]["*"]
    assert "--model m" in from_system["run_command"]["*"]


def test_resolve_agent_server_custom_entry_owns_its_argv(checkout: Path, config_dir: Path):
    servers = {
        "blast": {"type": "custom", "command": "/usr/bin/python3", "args": ["mock.py"]}
    }

    agent = resolve_agent_server(
        "blast", servers, config_dir=str(config_dir), system=True, model="m"
    )

    assert agent["run_command"]["*"] == "/usr/bin/python3 mock.py"


def test_resolve_agent_server_rejects_an_unknown_name(checkout: Path, config_dir: Path):
    with pytest.raises(AgentServerError, match="No agent_servers entry named"):
        resolve_agent_server("nope", {}, config_dir=str(config_dir))
