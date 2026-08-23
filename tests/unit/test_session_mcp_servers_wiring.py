"""Wiring: new/load/fork persist the client's mcpServers to sqlite.

The round trip's agent side: whatever mcpServers the client hands over on
session/new, session/load or fork must land in the session_mcp_servers
table (wire JSON dicts, keyed by wire id) so the separate-process task
tool can read them and pass them through to a delegated agent.

Transport isolation: the non-empty cases monkeypatch ONLY the MCP client
factory (no real server subprocesses in unit tests); the empty-list cases
run the full real path (empty list = no client = nothing to spawn).
"""

import pytest
from acp.schema import HttpMcpServer, McpServerStdio, SseMcpServer
from pydantic import TypeAdapter

from crow_cli.agent.main import AcpAgent, _mcp_servers_to_wire
from crow_cli.agent.session import AgentSession, lookup_or_create_prompt

# The same annotation main.py receives from the ACP SDK.
WIRE_LIST = TypeAdapter(list[HttpMcpServer | SseMcpServer | McpServerStdio])

STDIO = McpServerStdio(
    name="crow-mcp",
    command="uvx",
    args=["--from", "crow-cli", "crow-mcp"],
    env=[{"name": "CROW_LOG", "value": "1"}],
)
HTTP = HttpMcpServer(
    name="example-http", type="http", url="https://example.com/mcp", headers=[]
)
SSE = SseMcpServer(
    name="example-sse", type="sse", url="https://example.com/sse", headers=[]
)


@pytest.fixture
def no_transport(monkeypatch):
    """Isolate the persistence wiring from real MCP server subprocesses."""
    import crow_cli.agent.main as main_mod

    monkeypatch.setattr(
        main_mod, "create_mcp_client_from_acp", lambda **kw: (None, None)
    )


@pytest.fixture
def agent(test_config):
    """AcpAgent outside a live connection: _conn is set by the SDK at serve
    time, so unit construction shims it to None (no session_update sends)."""
    a = AcpAgent(config=test_config)
    a._conn = None
    return a


class TestSerializer:
    def test_wire_dicts_parse_back_to_the_same_objects(self):
        wire = _mcp_servers_to_wire([STDIO, HTTP, SSE])
        assert all(isinstance(w, dict) for w in wire)
        assert WIRE_LIST.validate_python(wire) == [STDIO, HTTP, SSE]

    def test_none_is_empty(self):
        assert _mcp_servers_to_wire(None) == []


class TestNewSessionPersists:
    async def test_non_empty_list_lands_in_sqlite_shape(
        self, agent, memory_service, no_transport
    ):
        resp = await agent.new_session(cwd="/tmp", mcp_servers=[STDIO, HTTP])

        stored = memory_service._session_mcp_servers[resp.session_id]
        assert stored == _mcp_servers_to_wire([STDIO, HTTP])
        # and what's stored parses back to exactly what the client sent
        assert WIRE_LIST.validate_python(stored) == [STDIO, HTTP]

    async def test_empty_list_is_explicitly_toolless(self, agent, memory_service):
        resp = await agent.new_session(cwd="/tmp", mcp_servers=[])
        assert memory_service._session_mcp_servers[resp.session_id] == []

    async def test_absent_list_persists_as_empty(self, agent, memory_service):
        resp = await agent.new_session(cwd="/tmp")
        assert memory_service._session_mcp_servers[resp.session_id] == []


class TestLoadSessionPersists:
    @pytest.fixture
    async def saved_session(self, memory_service):
        prompt_id = await lookup_or_create_prompt("You are a test.", name="t")
        return await AgentSession.create(
            prompt_id=prompt_id,
            prompt_args={"workspace": "/tmp", "display_tree": "test/"},
            tool_definitions=[],
            request_params={},
            model_identifier="test-model-id",
            cwd="/tmp",
            agent_idx=1,
            session_id="saved-session",
        )

    async def test_load_overwrites_with_the_new_client_list(
        self, agent, memory_service, saved_session, no_transport
    ):
        memory_service._session_mcp_servers[saved_session.session_id] = [
            {"command": "old"}
        ]

        resp = await agent.load_session(
            cwd="/tmp", session_id=saved_session.session_id, mcp_servers=[SSE]
        )
        assert resp is not None
        assert memory_service._session_mcp_servers[
            saved_session.session_id
        ] == _mcp_servers_to_wire([SSE])


class TestForkSessionPersists:
    @pytest.fixture
    async def saved_session(self, memory_service):
        prompt_id = await lookup_or_create_prompt("You are a test.", name="t")
        session = await AgentSession.create(
            prompt_id=prompt_id,
            prompt_args={"workspace": "/tmp", "display_tree": "test/"},
            tool_definitions=[],
            request_params={},
            model_identifier="test-model-id",
            cwd="/tmp",
            agent_idx=1,
            session_id="fork-source",
        )
        await session.add_message({"role": "user", "content": "hello"})
        return session

    async def test_fork_with_empty_list_is_toolless_by_design(
        self, agent, memory_service, saved_session
    ):
        """The interrogation fork: empty mcpServers = zero tools, persisted
        as an explicit [] so the task tool never 'inherits' by accident."""
        resp = await agent.fork_session(
            session_id=saved_session.session_id, cwd="/tmp", mcp_servers=[]
        )
        assert memory_service._session_mcp_servers[resp.session_id] == []

    async def test_fork_inherits_parent_list_when_client_says_so(
        self, agent, memory_service, saved_session, no_transport
    ):
        resp = await agent.fork_session(
            session_id=saved_session.session_id,
            cwd="/tmp",
            mcp_servers=[STDIO],
        )
        assert memory_service._session_mcp_servers[
            resp.session_id
        ] == _mcp_servers_to_wire([STDIO])


class TestMemoryClientRealDb:
    """The wrapper itself against real sqlite, two clients = two processes."""

    async def test_two_clients_one_file(self, tmp_path, test_config_dir):
        from crow_cli.agent.memory import MemoryClient

        db_path = str(tmp_path / "roundtrip.db")
        writer = MemoryClient(path=db_path, config_dir=test_config_dir)
        reader = MemoryClient(path=db_path, config_dir=test_config_dir)

        wire = _mcp_servers_to_wire([STDIO, HTTP])
        await writer.set_session_mcp_servers("quick-zephyr-otter", wire)
        assert await reader.get_session_mcp_servers("quick-zephyr-otter") == wire
        assert await reader.get_session_mcp_servers("never-seen") == []

        await writer.close()
        await reader.close()
