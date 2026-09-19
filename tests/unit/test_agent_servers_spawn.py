"""The TUI's launch strings: what `-a NAME` and the no-config fallback build.

Every configured entry is a command, honored exactly as written — crow never
substitutes its own agent for one. Real specs, no mocks.
"""

import logging
import shlex
import sys

import pytest

from crow_cli.tui.agent_servers import (
    AgentServerError,
    crow_agent,
    resolve_agent_server,
    resolved_agent_servers,
)


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


def test_crow_agent_carries_config_file():
    agent = crow_agent(config_dir="/tmp/crow", config_file="/tmp/my config.yaml")

    command = agent["run_command"]["*"]
    flags = "--config-dir /tmp/crow --config-file '/tmp/my config.yaml'"
    if getattr(sys, "frozen", False):
        assert command.endswith(f"acp {flags}")
    else:
        assert command.endswith(flags)
    # quoted exactly once, so the shell hands the agent one path with a space in it
    assert "'/tmp/my config.yaml'" in command
    assert shlex.split(command)[-1] == "/tmp/my config.yaml"


def test_crow_agent_never_bakes_the_model_into_argv():
    """-m is client-driven (session/set_config_option), not a launch flag.

    Putting --model here would make it work for crow's own agent and silently
    vanish for every custom agent_servers entry — the bug this guards.
    """
    tokens = shlex.split(crow_agent(config_dir="/tmp/crow")["run_command"]["*"])

    # `python -m crow_cli.agent.main` is a module flag, not a model one — the
    # invariant is that no model flag reaches the agent's argv at all.
    assert "--model" not in tokens
    assert "--model" not in " ".join(tokens)


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


# -- the protocol this client speaks -----------------------------------------


def test_the_tui_refuses_a_v2_entry_and_names_the_client_that_speaks_it():
    """A v1 client handed a v2 agent does not fail loudly — it hangs in a
    handshake that can never complete. Refusing, and saying what to run
    instead, is the only honest answer."""
    servers = {"crow-v2": {"protocol": "acp2", "command": "uv", "args": ["run", "agent"]}}

    with pytest.raises(AgentServerError) as exc:
        resolve_agent_server("crow-v2", servers)

    message = str(exc.value)
    assert "speaks acp2" in message
    assert "crow-cli run -a crow-v2" in message


def test_the_tui_still_launches_a_v1_entry():
    servers = {"old": {"protocol": "acp", "command": "/usr/bin/python3", "args": ["m.py"]}}
    assert resolve_agent_server("old", servers)["run_command"]["*"] == (
        "/usr/bin/python3 m.py"
    )


def test_the_store_listing_skips_a_v2_entry_with_a_warning(tmp_path, caplog):
    """One unlaunchable entry must not take down the home screen — but it must
    not vanish either, or the user is left wondering where their agent went."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "agent_servers:\n"
        "  crow-v2:\n"
        "    protocol: acp2\n"
        "    command: uv\n"
        "    args: [run, agent]\n"
        "  old:\n"
        "    command: /usr/bin/python3\n"
        "    args: [m.py]\n"
    )

    with caplog.at_level(logging.WARNING, logger="crow_cli.tui.agent_servers"):
        agents = resolved_agent_servers(str(config_dir))

    assert "old" in agents
    assert "crow-v2" not in agents
    assert "crow-ai.dev" in agents, "crow's own v1 agent is always launchable"
    assert "speaks acp2" in caplog.text


def test_crow_agent_is_v1_because_the_tui_is():
    """The empty-registry fallback follows the client's protocol: v1 here,
    acp2 for `crow-cli run`."""
    command = crow_agent()["run_command"]["*"]
    if getattr(sys, "frozen", False):
        assert " acp " in f" {command} " or command.endswith(" acp")
    else:
        assert "crow_cli.agent.main" in command
        assert "crow_cli.agent2.main" not in command
