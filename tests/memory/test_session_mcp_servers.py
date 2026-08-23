"""mcpServers round trip through sqlite — task system critical path.

MCP servers are CLIENT-DEFINED and ride the agents table (no table of their
own): they are stored on the agent row provisioned with them, by the same
session/new, session/load or fork call. The task MCP tool runs in a SEPARATE
process (all tool calling is MCP JSON-RPC), so it cannot see the agent's
in-memory state. The coupling between the two processes is the shared sqlite
state: the agent persists the client's mcpServers JSON on the agent row; the
MCP server process reads it back by WIRE session id to pass through to the
subagent's session/new.

These tests simulate the two processes with two engines on one db file.
"""

from crow_cli.memory.db import create_database, get_engine
from crow_cli.memory.ids import build_agent_id
from crow_cli.memory.reads import get_session_mcp_servers
from crow_cli.memory.writes import create_agent, set_agent_mcp_servers

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


def _trunk(engine, session_id, agent_idx=1, servers=None):
    """Provision a trunk agent row (fork_idx=1) the way session/new does:
    create the row, then store the client's mcpServers on it."""
    agent_id = build_agent_id(session_id, agent_idx, 1)
    create_agent(
        engine, agent_id=agent_id, session_id=session_id,
        agent_idx=agent_idx, fork_idx=1,
    )
    if servers is not None:
        set_agent_mcp_servers(engine, agent_id, servers)
    return agent_id


def test_round_trip_across_engines(tmp_path):
    """Writer = agent process, reader = MCP server process. The reader only
    knows the WIRE id (trunk = bare session_id)."""
    uri = _uri(tmp_path)
    writer = get_engine(uri)
    reader = get_engine(uri)

    servers = [STDIO_SERVER, HTTP_SERVER, SSE_SERVER]
    _trunk(writer, "quick-zephyr-otter-of-glass", servers=servers)

    assert get_session_mcp_servers(reader, "quick-zephyr-otter-of-glass") == servers


def test_set_overwrites_previous_list_on_same_row(tmp_path):
    """session/load with a new client list replaces what new_session stored
    (same agent row, second write wins)."""
    uri = _uri(tmp_path)
    engine = get_engine(uri)

    aid = _trunk(engine, "s1", servers=[STDIO_SERVER])
    set_agent_mcp_servers(engine, aid, [SSE_SERVER, HTTP_SERVER])

    assert get_session_mcp_servers(engine, "s1") == [SSE_SERVER, HTTP_SERVER]


def test_newest_agent_in_chain_wins(tmp_path):
    """The read scans the wire session's agent chain newest-first and returns
    the most recent provisioning — a later agent_idx overrides an earlier one."""
    uri = _uri(tmp_path)
    engine = get_engine(uri)

    _trunk(engine, "s1", agent_idx=1, servers=[STDIO_SERVER])
    _trunk(engine, "s1", agent_idx=2, servers=[HTTP_SERVER])

    assert get_session_mcp_servers(engine, "s1") == [HTTP_SERVER]


def test_compaction_row_null_is_skipped(tmp_path):
    """A newer agent row that never carried mcpServers (NULL — e.g. a
    compaction row) is skipped; the read falls back to the older provisioning."""
    uri = _uri(tmp_path)
    engine = get_engine(uri)

    _trunk(engine, "s1", agent_idx=1, servers=[STDIO_SERVER])
    _trunk(engine, "s1", agent_idx=2)  # servers=None → NULL

    assert get_session_mcp_servers(engine, "s1") == [STDIO_SERVER]


def test_explicit_empty_list_means_toolless(tmp_path):
    """Client passing mcpServers=[] is EXPLICITLY toolless (the fork-delegate
    use case) — the empty list round-trips as empty, not as 'unknown'/NULL."""
    uri = _uri(tmp_path)
    engine = get_engine(uri)

    aid = _trunk(engine, "s1", servers=[STDIO_SERVER])
    set_agent_mcp_servers(engine, aid, [])

    assert get_session_mcp_servers(engine, "s1") == []


def test_fork_wire_id_reads_fork_row(tmp_path):
    """A fork (fork_idx>1) is addressed by its FULL agent_id on the wire, and
    its mcpServers are read off the fork row — independent of the trunk."""
    uri = _uri(tmp_path)
    engine = get_engine(uri)

    _trunk(engine, "s1", agent_idx=1, servers=[STDIO_SERVER])
    fork_id = build_agent_id("s1", 1, 2)
    create_agent(engine, agent_id=fork_id, session_id="s1", agent_idx=1, fork_idx=2)
    set_agent_mcp_servers(engine, fork_id, [HTTP_SERVER])

    # fork addressed by full agent_id; trunk still returns its own list
    assert get_session_mcp_servers(engine, fork_id) == [HTTP_SERVER]
    assert get_session_mcp_servers(engine, "s1") == [STDIO_SERVER]


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
    _trunk(engine, "s1", servers=[weird])
    assert get_session_mcp_servers(engine, "s1") == [weird]
