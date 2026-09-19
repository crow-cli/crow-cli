"""The `agent_servers` registry — config to argv, env and protocol.

`crow-cli run` and the TUI are both CLIENTS, and both launch whatever the
registry names. These are the registry's own contracts; the TUI's adapter over
it is covered by tests/unit/test_agent_servers_spawn.py, and the dispatch that
consumes it by tests/integration/test_cli_run_dispatch.py.

Real specs, no mocks: every input here is a dict shaped exactly like the YAML
a user writes.
"""

import dataclasses
import logging
import sys

import pytest

from crow_cli.agents import (
    CROW_IDENTITY,
    V1,
    V2,
    AgentServer,
    AgentServerError,
    crow_agent_server,
    default_agent_server,
    parse_agent_server,
    parse_agent_servers,
    resolve_agent_server,
    select_agent_server,
    tool_supply,
)
from crow_cli.cli.source import SourceError

GLOBAL_SUPPLY = {
    "crow-mcp": {"transport": "stdio", "command": "crow-cli", "args": ["mcp"]},
    "remote": {"transport": "http", "url": "https://x.invalid/mcp"},
}


# -- one entry ---------------------------------------------------------------


def test_a_command_is_the_whole_spec():
    server = parse_agent_server("blast", {"command": "/usr/bin/agent"})

    assert server.name == "blast"
    assert server.argv == ["/usr/bin/agent"]
    assert server.args == ()
    assert server.env == {}
    assert server.mcp_servers is None
    assert server.builtin is False


def test_args_and_env_are_honored_exactly_as_written():
    server = parse_agent_server(
        "blast",
        {
            "command": "uv",
            "args": ["--project", "/tmp/a b", "run", "agent"],
            "env": {"TOKEN": "sekrit"},
        },
    )

    assert server.argv == ["uv", "--project", "/tmp/a b", "run", "agent"]
    assert server.env == {"TOKEN": "sekrit"}
    # the string form is decoration for humans; the list is what gets spawned,
    # so a space in an arg survives without a shlex round trip
    assert server.launch == "uv --project /tmp/a b run agent"


def test_args_and_env_are_coerced_to_strings():
    """YAML gives an int for `args: [8080]` and a bool for `env: {DEBUG: true}`.

    `create_subprocess_exec` wants str only, and the failure it produces
    (`TypeError`, deep in asyncio) names neither the entry nor the field.
    """
    server = parse_agent_server(
        "blast", {"command": "agent", "args": [8080], "env": {"DEBUG": True}}
    )

    assert server.args == ("8080",)
    assert server.env == {"DEBUG": "True"}


def test_display_name_is_the_title_and_the_key_is_the_identity():
    server = parse_agent_server(
        "blast", {"command": "agent", "name": "Blast Off"}
    )

    assert server.title == "Blast Off"
    assert server.name == "blast"
    assert parse_agent_server("b", {"command": "a"}).title == "b"


def test_protocol_defaults_to_v1():
    assert parse_agent_server("b", {"command": "a"}).protocol == V1 == "acp"


def test_protocol_accepts_v2():
    server = parse_agent_server("b", {"command": "a", "protocol": "acp2"})
    assert server.protocol == V2 == "acp2"


def test_an_unknown_protocol_is_refused_with_the_valid_ones():
    """Guessing the protocol from the argv is the bug this prevents: the first
    agent whose path happens to contain `acp2` would be mis-driven."""
    with pytest.raises(AgentServerError) as exc:
        parse_agent_server("b", {"command": "a", "protocol": "acp3"})

    assert "unknown protocol 'acp3'" in str(exc.value)
    assert "expected one of acp, acp2" in str(exc.value)


def test_an_mcpServers_override_replaces_the_global_supply():
    server = parse_agent_server(
        "b", {"command": "a", "mcpServers": {"crow-mcp2": {"command": "crow-cli"}}}
    )

    assert list(server.mcp_servers) == ["crow-mcp2"]


def test_a_non_mapping_mcpServers_is_refused():
    with pytest.raises(AgentServerError, match="'mcpServers' must be a mapping"):
        parse_agent_server("b", {"command": "a", "mcpServers": ["crow-mcp"]})


def test_a_non_mapping_entry_is_refused():
    with pytest.raises(AgentServerError, match=r"agent_servers\.'b' must be a mapping"):
        parse_agent_server("b", "uv run agent")


def test_the_old_registry_type_is_refused():
    with pytest.raises(AgentServerError, match="unknown type 'registry'"):
        parse_agent_server("b", {"type": "registry"})


def test_a_missing_command_is_refused():
    with pytest.raises(AgentServerError, match="requires a 'command'"):
        parse_agent_server("b", {"args": ["x"]})


def test_bad_args_and_env_are_refused():
    with pytest.raises(AgentServerError, match="'args' must be a list"):
        parse_agent_server("b", {"command": "a", "args": "x"})
    with pytest.raises(AgentServerError, match="'env' must be a mapping"):
        parse_agent_server("b", {"command": "a", "env": ["x"]})


# -- tool supply -------------------------------------------------------------


def test_tool_supply_falls_through_to_the_global_map():
    server = parse_agent_server("b", {"command": "a"})
    assert tool_supply(server, GLOBAL_SUPPLY) == GLOBAL_SUPPLY


def test_tool_supply_prefers_the_entrys_own_map():
    """How a v2 agent gets crow-mcp2 without changing what v1 sessions get."""
    server = parse_agent_server(
        "b", {"command": "a", "mcpServers": {"crow-mcp2": {"command": "c"}}}
    )

    assert tool_supply(server, GLOBAL_SUPPLY) == {"crow-mcp2": {"command": "c"}}


def test_an_empty_override_means_zero_tools_not_the_global_supply():
    """`mcpServers: {}` is a statement — "this agent gets nothing" — and
    falling back to the global map would silently contradict it."""
    server = parse_agent_server("b", {"command": "a", "mcpServers": {}})

    assert server.mcp_servers == {}
    assert tool_supply(server, GLOBAL_SUPPLY) == {}


def test_no_global_supply_and_no_override_is_zero_tools():
    server = parse_agent_server("b", {"command": "a"})
    assert tool_supply(server, {}) == {}
    assert tool_supply(server, None) == {}


# -- the registry ------------------------------------------------------------


def test_the_registry_keeps_config_order():
    """Order is meaning: the top entry is what a bare client launches."""
    servers = parse_agent_servers(
        {"second": {"command": "b"}, "first": {"command": "a"}}
    )

    assert list(servers) == ["second", "first"]
    assert next(iter(servers.values())).argv == ["b"]


def test_one_broken_entry_does_not_take_down_the_listing(caplog):
    """A client that LISTS agents must survive a bad one; a client that
    LAUNCHES it must not (see test_resolve_refuses_a_broken_entry)."""
    with caplog.at_level(logging.WARNING, logger="crow_cli.agents"):
        servers = parse_agent_servers(
            {"good": {"command": "a"}, "bad": {"args": ["no command"]}}
        )

    assert list(servers) == ["good"]
    assert "agent_servers 'bad'" in caplog.text
    assert "requires a 'command'" in caplog.text


def test_resolve_refuses_a_broken_entry():
    with pytest.raises(AgentServerError, match="requires a 'command'"):
        resolve_agent_server("bad", {"bad": {"args": ["x"]}})


def test_an_unknown_name_lists_what_is_configured_in_config_order():
    with pytest.raises(AgentServerError) as exc:
        resolve_agent_server("nope", {"second": {"command": "b"}, "first": {"command": "a"}})

    assert "No agent_servers entry named 'nope'" in str(exc.value)
    assert "Configured: second, first." in str(exc.value)


def test_an_empty_registry_says_none_configured():
    with pytest.raises(AgentServerError, match="Configured: none configured"):
        resolve_agent_server("nope", {})


def test_a_null_entry_is_an_entry_with_nothing_in_it():
    """`agent_servers: {b:}` parses to None, and the error must be the missing
    command, not an AttributeError."""
    with pytest.raises(AgentServerError, match="requires a 'command'"):
        resolve_agent_server("b", {"b": None})


# -- crow's own agent --------------------------------------------------------


def test_crow_v1_is_this_interpreters_v1_entry():
    server = crow_agent_server(V1)

    assert server.protocol == V1
    assert server.builtin is True
    assert server.name == CROW_IDENTITY
    assert server.title == "Crow"
    assert server.command == sys.executable
    if getattr(sys, "frozen", False):
        assert server.args[0] == "acp"
    else:
        # the module entry is argparse and takes no subcommand
        assert server.args[:2] == ("-m", "crow_cli.agent.main")


def test_crow_v2_is_this_interpreters_v2_entry():
    server = crow_agent_server(V2)

    assert server.protocol == V2
    if getattr(sys, "frozen", False):
        assert server.args[0] == "acp2"
    else:
        assert server.args[:2] == ("-m", "crow_cli.agent2.main")


def test_crow_v1_is_the_default_protocol():
    assert crow_agent_server().protocol == V1


def test_an_unknown_protocol_is_refused_by_the_entry_point_table():
    with pytest.raises(SourceError, match="unknown agent protocol"):
        crow_agent_server("acp3")


def test_config_pointers_ride_crows_own_argv(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    server = crow_agent_server(V2, config_dir="/tmp/crow", config_file="/tmp/my cfg.yaml")

    assert server.args == (
        "-m", "crow_cli.agent2.main",
        "--config-dir", "/tmp/crow",
        "--config-file", "/tmp/my cfg.yaml",
    )


def test_a_frozen_build_spawns_the_binarys_own_subcommand(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    server = crow_agent_server(V2, config_dir="/tmp/crow")

    assert server.argv == [sys.executable, "acp2", "--config-dir", "/tmp/crow"]


def test_crow_never_bakes_the_model_into_argv():
    """-m travels over session/set_config_option, so it reaches an agent
    somebody else wrote. In an argv it would reach only crow's own."""
    for protocol in (V1, V2):
        assert "--model" not in crow_agent_server(protocol).argv


# -- selection ---------------------------------------------------------------


def test_the_top_entry_is_the_default():
    servers = {"second": {"command": "b"}, "first": {"command": "a"}}
    assert default_agent_server(servers).name == "second"


def test_an_empty_registry_falls_back_to_crow_in_the_callers_protocol():
    """There is no entry left to declare a protocol, so the CLIENT picks: a v2
    client asks for acp2, the v1 TUI for acp."""
    assert default_agent_server({}, V2).protocol == V2
    assert default_agent_server({}, V1).protocol == V1
    assert default_agent_server({}).protocol == V1


def test_a_registry_whose_entries_are_all_broken_falls_back_too():
    server = default_agent_server({"bad": {"args": ["x"]}}, V2)
    assert server.builtin is True and server.protocol == V2


def test_select_by_name_wins_over_the_default():
    servers = {"second": {"command": "b"}, "first": {"command": "a"}}
    assert select_agent_server("first", servers).argv == ["a"]


def test_select_with_no_name_is_the_default():
    servers = {"second": {"command": "b"}}
    assert select_agent_server(None, servers).argv == ["b"]


def test_an_unknown_name_never_falls_back():
    """Silently launching a different agent than the one asked for is the kind
    of wrong answer nobody notices."""
    servers = {"second": {"command": "b"}}
    with pytest.raises(AgentServerError, match="No agent_servers entry named 'first'"):
        select_agent_server("first", servers, V2)


def test_the_fallback_protocol_does_not_leak_into_a_named_entry():
    servers = {"first": {"command": "a"}}
    assert select_agent_server("first", servers, V2).protocol == V1


def test_the_dataclass_is_frozen():
    """A resolved entry is passed between a client's layers; one that can be
    edited in place is one whose argv can drift from what was printed."""
    server = AgentServer(name="x", command="a")
    with pytest.raises(dataclasses.FrozenInstanceError):
        server.command = "b"
