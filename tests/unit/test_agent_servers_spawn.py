"""The TUI's launch strings: what `-a NAME` and the no-config fallback build.

Every configured entry is a command, honored exactly as written — crow never
substitutes its own agent for one. Real specs, no mocks.
"""

import shlex
import sys

import pytest

from crow_cli.tui.agent_servers import AgentServerError, crow_agent, resolve_agent_server


def test_crow_agent_runs_the_code_that_is_running():
    agent = crow_agent()

    command = agent["run_command"]["*"]
    assert "uv" not in command
    assert command.startswith(shlex.quote(sys.executable))
    if getattr(sys, "frozen", False):
        assert " acp" in command
    else:
        # the module entry is argparse and takes no `acp` subcommand
        assert "-m crow_cli.agent.main" in command


def test_crow_agent_carries_model_and_config_file():
    agent = crow_agent(
        model="alibaba:qwen3.8-max-preview",
        config_dir="/tmp/crow",
        config_file="/tmp/my config.yaml",
    )

    command = agent["run_command"]["*"]
    flags = (
        "--config-dir /tmp/crow --config-file '/tmp/my config.yaml' "
        "--model alibaba:qwen3.8-max-preview"
    )
    if getattr(sys, "frozen", False):
        assert command.endswith(f"acp {flags}")
    else:
        assert command.endswith(flags)
    # quoted exactly once, so the shell hands the agent one path with a space in it
    assert "'/tmp/my config.yaml'" in command
    assert shlex.split(command)[-3] == "/tmp/my config.yaml"


def test_resolve_agent_server_custom_entry_owns_its_argv():
    servers = {
        "blast": {"type": "custom", "command": "/usr/bin/python3", "args": ["mock.py"]}
    }

    agent = resolve_agent_server("blast", servers)

    assert agent["run_command"]["*"] == "/usr/bin/python3 mock.py"


def test_resolve_agent_server_typeless_entry_is_custom():
    """A command IS the spec; `type` is optional and only ever means custom."""
    servers = {"blast": {"command": "/usr/bin/python3", "args": ["mock.py"]}}
    agent = resolve_agent_server("blast", servers)
    assert agent["run_command"]["*"] == "/usr/bin/python3 mock.py"


def test_resolve_agent_server_env_and_display_name():
    servers = {
        "blast": {
            "command": "/usr/bin/python3",
            "args": ["mock.py"],
            "env": {"CROW_MOCK_CHUNKS": "50000"},
            "name": "Blast Off",
        }
    }
    agent = resolve_agent_server("blast", servers)
    assert agent["run_command"]["*"] == "/usr/bin/python3 mock.py"
    assert agent["env"] == {"CROW_MOCK_CHUNKS": "50000"}
    assert agent["name"] == "Blast Off"
    # the identity stays the config key — that is what LaunchAgent carries
    assert agent["identity"] == "blast"


def test_resolve_agent_server_rejects_an_unknown_name():
    with pytest.raises(AgentServerError, match="No agent_servers entry named"):
        resolve_agent_server("nope", {})


def test_resolve_agent_server_rejects_the_old_registry_type():
    """The registry is gone: an entry that says otherwise fails loudly."""
    servers = {"crow-cli": {"type": "registry"}}
    with pytest.raises(AgentServerError, match="unknown type 'registry'"):
        resolve_agent_server("crow-cli", servers)


def test_resolve_agent_server_requires_a_command():
    with pytest.raises(AgentServerError, match="requires a 'command'"):
        resolve_agent_server("empty", {"empty": {}})
