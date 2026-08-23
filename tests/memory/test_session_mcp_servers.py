"""mcpServers round trip through sqlite — task system critical path.

MCP servers are CLIENT-DEFINED, per session: they arrive on session/new,
session/load and fork. The task MCP tool runs in a SEPARATE process (all
tool calling is MCP JSON-RPC), so it cannot see the agent's in-memory
``_session_mcp_servers`` map. The coupling between the two processes is
the shared sqlite state: the agent persists the client's mcpServers JSON
keyed by session id; the MCP server process reads it back to pass through
to the delegated agent's session/new.

These tests simulate the two processes with two engines on one db file.
"""

from crow_cli.memory.db import create_database, get_engine
from crow_cli.memory.reads import get_session_mcp_servers
from crow_cli.memory.writes import set_session_mcp_servers

# Real ACP wire shapes (name required; env/headers are lists of
# {name, value} pairs) — what a client actually sends in mcpServers.
STDIO_SERVER = {
    "name": "crow-mcp",
    "command": "uvx",
    "args": ["--from", "crow-cli", "crow-mcp"],
    "env": [{"name": "CROW_LOG", "value": "1"}],
}
HTTP_SERVER = {
    "name": "example-http",
    "type": "http",
    "url": "https://example.com/mcp",
    "headers": [{"name": "Authorization", "value": "Bearer token"}],
}
SSE_SERVER = {"name": "example-sse", "type": "sse", "url": "https://example.com/sse"}


def _uri(tmp_path):
    uri = f"sqlite:///{tmp_path / 'roundtrip.db'}"
    create_database(uri)
    return uri


def test_round_trip_across_engines(tmp_path):
    """Writer = agent process, reader = MCP server process."""
    uri = _uri(tmp_path)
    writer = get_engine(uri)
    reader = get_engine(uri)

    servers = [STDIO_SERVER, HTTP_SERVER, SSE_SERVER]
    set_session_mcp_servers(writer, "quick-zephyr-otter-of-glass", servers)

    assert get_session_mcp_servers(reader, "quick-zephyr-otter-of-glass") == servers


def test_upsert_overwrites_previous_list(tmp_path):
    """session/load with a new client list replaces what new_session stored."""
    uri = _uri(tmp_path)
    engine = get_engine(uri)

    set_session_mcp_servers(engine, "s1", [STDIO_SERVER])
    set_session_mcp_servers(engine, "s2", [HTTP_SERVER])
    set_session_mcp_servers(engine, "s1", [SSE_SERVER, HTTP_SERVER])

    assert get_session_mcp_servers(engine, "s1") == [SSE_SERVER, HTTP_SERVER]
    assert get_session_mcp_servers(engine, "s2") == [HTTP_SERVER]


def test_explicit_empty_list_means_toolless(tmp_path):
    """Client passing mcpServers=[] is EXPLICITLY toolless (the fork-delegate
    use case) — the empty list round-trips as empty, not as 'unknown'."""
    uri = _uri(tmp_path)
    engine = get_engine(uri)

    set_session_mcp_servers(engine, "s1", [STDIO_SERVER])
    set_session_mcp_servers(engine, "s1", [])

    assert get_session_mcp_servers(engine, "s1") == []


def test_unknown_session_is_empty(tmp_path):
    uri = _uri(tmp_path)
    engine = get_engine(uri)
    assert get_session_mcp_servers(engine, "never-seen") == []


def test_nested_json_survives_byte_for_byte(tmp_path):
    """Whatever wire shape the client sent is what the delegate gets: the
    stored JSON must deep-equal the input, nesting and order included."""
    uri = _uri(tmp_path)
    engine = get_engine(uri)

    weird = {
        "command": "node",
        "args": ["server.js", "--port", "0"],
        "env": {
            "NESTED": '{"a": [1, 2, {"b": null}]}',
            "EMPTY": "",
        },
    }
    set_session_mcp_servers(engine, "s1", [weird])
    assert get_session_mcp_servers(engine, "s1") == [weird]
