"""The two halves of the v2 ``mcpServers`` seam (hermetic).

``mcp_servers_to_wire`` is what lands on the agent row, so a subagent spawned
in another process can be handed the same servers the client sent;
``mcp_client_for`` is what turns those wire objects into a FastMCP config and a
client. v1's equivalents have ``test_session_mcp_servers_wiring.py``. These are
the v2 ports, and until now the only thing exercising either was the gate's
stdio server — one branch of one of them.

No subprocess and no socket. Constructing a FastMCP ``Client`` is lazy, so a
config naming a port nothing listens on is enough to prove the translation, and
the translation is what is under test. The end-to-end half — a real server on a
real port, its tools listed and called through a real ``session/new`` — is
``test_an_http_mcp_server_supplies_the_tools_a_session_runs`` in the gate.
"""

from __future__ import annotations

import json
import logging

from acp.experimental.v2 import schema as v2
from pydantic import TypeAdapter

from crow_cli.agent2.sessions import mcp_client_for, mcp_servers_to_wire

# The annotation NewSessionRequest.mcp_servers actually carries.
WIRE_LIST = TypeAdapter(
    list[
        v2.HttpMcpServer
        | v2.AcpMcpServer
        | v2.StdioMcpServer
        | v2.OtherMcpServer
    ]
)

STDIO = v2.StdioMcpServer(
    name="crow-mcp2",
    command="crow-cli",
    args=["mcp2"],
    env=[v2.EnvVariable(name="CROW_LOG", value="1")],
)
HTTP = v2.HttpMcpServer(
    name="remote",
    url="https://example.com/mcp",
    headers=[v2.HttpHeader(name="X-Api", value="k")],
)
ACP = v2.AcpMcpServer(name="nested", server_id="agent-1")

LOG = logging.getLogger("test.mcp.wiring")
CWD = "/tmp/wd"


def config_for(*servers) -> dict:
    config, client = mcp_client_for(list(servers), CWD, LOG)
    assert client is not None, "a non-empty server list owes a client"
    return config["mcpServers"]


# ---------------------------------------------------------------------------
# to the store
# ---------------------------------------------------------------------------


def test_the_wire_dicts_parse_back_to_the_same_objects():
    """The round trip a delegated subagent depends on.

    The task tool runs in another process, reads these dicts off the agent row
    and hands them to a child's ``session/new`` unchanged. What is stored has
    to be the same servers the client sent, not a lossy summary of them.
    """
    wire = mcp_servers_to_wire([STDIO, HTTP, ACP])
    assert all(isinstance(entry, dict) for entry in wire)
    assert WIRE_LIST.validate_python(wire) == [STDIO, HTTP, ACP]


def test_what_is_stored_is_json_all_the_way_down():
    """``mode="json"``, and the column it is headed for is the reason.

    An ``HttpMcpServer``'s ``url`` is an ``AnyUrl``. Dumped as a Python object
    it survives ``validate_python`` and then dies in sqlite's JSON column, in
    another process, at the moment a subagent is spawned — so the serializable
    assertion is the one that fails where the bug is.
    """
    wire = mcp_servers_to_wire([HTTP])
    assert json.loads(json.dumps(wire)) == wire
    assert wire[0]["url"] == "https://example.com/mcp"


def test_no_servers_is_an_empty_list_not_a_null():
    """``[]`` means explicitly toolless; NULL would mean never supplied."""
    assert mcp_servers_to_wire(None) == []
    assert mcp_servers_to_wire([]) == []


# ---------------------------------------------------------------------------
# to a client
# ---------------------------------------------------------------------------


def test_a_stdio_server_becomes_the_config_fastmcp_expects():
    assert config_for(STDIO) == {
        "crow-mcp2": {
            "transport": "stdio",
            "command": "crow-cli",
            "args": ["mcp2"],
            "env": {"CROW_LOG": "1"},
            "cwd": CWD,
        }
    }


def test_an_http_server_url_arrives_as_a_plain_string():
    """``AnyUrl`` is not a ``str``, and FastMCP's config model refuses it.

    Hand the raw object to ``MCPConfigTransport`` and it raises a
    ``ValidationError`` that names every variant of the config union it tried —
    which is to say it reports nothing useful about the actual problem. The
    session dies at ``session/new`` blaming the wrong thing.
    """
    served = config_for(HTTP)["remote"]
    assert isinstance(served["url"], str)
    assert served["url"] == "https://example.com/mcp"
    assert served == {
        "transport": "http",
        "url": "https://example.com/mcp",
        "headers": {"X-Api": "k"},
        "cwd": CWD,
    }


def test_a_server_a_config_carried_is_dispatched_too():
    """The discriminator, not the class — because there are two classes.

    ``McpServerStdio`` is what a crow config carries for the same shape a
    client sends as ``StdioMcpServer``, and it has no ``type`` field at all, so
    the fallback infers the transport from what the object does carry.
    """
    from_config = v2.McpServerStdio(name="from-config", command="crow-cli", args=["mcp2"])
    assert config_for(from_config)["from-config"]["transport"] == "stdio"

    http_config = v2.McpServerHttp(name="h", url="https://example.com/mcp")
    assert config_for(http_config)["h"]["transport"] == "http"


def test_both_transports_share_one_client_and_keep_their_own_names():
    config, client = mcp_client_for([STDIO, HTTP], CWD, LOG)
    assert client is not None
    assert list(config["mcpServers"]) == ["crow-mcp2", "remote"]


def test_an_acp_server_is_skipped_loudly_rather_than_advertised(caplog):
    """MCP-over-ACP is not wired. Skipping beats advertising a tool that hangs.

    A warning is the only channel this has: the response to ``session/new``
    carries no per-server status, so a client that asked for three servers and
    got two tools learns why from the agent's log or not at all.
    """
    with caplog.at_level(logging.WARNING, logger="crow_cli.agent2.sessions"):
        config, client = mcp_client_for([ACP], CWD, LOG)
    assert config == {"mcpServers": {}}
    assert client is None
    assert any("not supported yet" in r.getMessage() for r in caplog.records)


def test_an_unknown_transport_is_skipped_rather_than_guessed_at(caplog):
    with caplog.at_level(logging.WARNING, logger="crow_cli.agent2.sessions"):
        config, client = mcp_client_for(
            [v2.OtherMcpServer(type="carrier-pigeon")], CWD, LOG
        )
    assert config == {"mcpServers": {}}
    assert client is None
    assert any("carrier-pigeon" in r.getMessage() for r in caplog.records)


def test_no_servers_means_no_client_and_that_is_not_an_error():
    """Zero tools is a configuration, not a failure worth raising over.

    The client owns tool supply and there is no builtin fallback, so an empty
    list is a session that can only talk. ``None`` rather than a client with no
    transports is what lets the caller skip the connect entirely.
    """
    for empty in ([], None):
        config, client = mcp_client_for(empty, CWD, LOG)
        assert config == {"mcpServers": {}}
        assert client is None
