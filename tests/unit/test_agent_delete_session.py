"""``AcpAgent.delete_session`` — the wire method behind ``session/delete``.

The memory-layer footprint is :mod:`tests.memory.test_delete_session`; this is
the half a client can see: that the method exists at all (it was inherited as
a protocol stub whose ``...`` body serialised to the exact bytes a successful
delete returns), that an unknown session is an error rather than a second
silent success, and that the connection's in-memory state goes with the rows.
"""

import pytest
from acp.exceptions import RequestError
from acp.schema import DeleteSessionResponse

from crow_cli.agent.main import AcpAgent
from crow_cli.agent.session import AgentSession, lookup_or_create_prompt
from crow_cli.config import Config
from crow_cli.memory import create_database, get_engine, list_session_infos


class FakeMcpClient:
    """Stands in for a fastmcp Client, which is an async context manager the
    exit stack also holds. ``__aexit__`` refcounts and clamps at zero, so the
    stack's later ``aclose`` is a no-op — the count is what this asserts."""

    def __init__(self) -> None:
        self.exits = 0

    async def __aexit__(self, *exc) -> None:
        self.exits += 1


@pytest.fixture
async def agent(tmp_path):
    config = Config(config_dir=tmp_path)
    config.db_uri = f"sqlite:///{tmp_path / 'crow.db'}"
    create_database(config.db_uri)
    a = AcpAgent(config=config)
    a._conn = None  # set by the SDK at serve time; no session_update sends here
    return a


async def _make_session(agent, sid: str) -> AgentSession:
    prompt_id = await lookup_or_create_prompt(
        "You are {{name}}.", name="delete-test", memory_path=agent._memory_db_uri
    )
    session = await AgentSession.create(
        prompt_id=prompt_id,
        prompt_args={"name": "Crow"},
        tool_definitions=[],
        request_params={},
        model_identifier="test-model",
        memory_path=agent._memory_db_uri,
        cwd="/tmp",
        session_id=sid,
    )
    await session.add_message({"role": "user", "content": "hi"})
    return session


async def test_delete_answers_with_a_response_and_the_session_is_gone(agent):
    session = await _make_session(agent, "gone")
    await session.close()

    result = await agent.delete_session("gone")

    assert isinstance(result, DeleteSessionResponse)
    engine = get_engine(agent._memory_db_uri)
    try:
        infos, _ = list_session_infos(engine)
        assert infos == []
    finally:
        engine.dispose()


async def test_an_unknown_session_is_an_error_not_a_second_silent_success(agent):
    """The bug this method exists to fix was a success that deleted nothing.
    Answering the same way for a bad id would reintroduce it one level up."""
    with pytest.raises(RequestError) as exc:
        await agent.delete_session("never-existed")
    # the detail rides `data`, which to_error_obj puts on the wire — the same
    # shape fork_session uses, so a client can say WHICH id was unknown
    assert exc.value.code == -32602
    assert "never-existed" in exc.value.data


async def test_delete_clears_the_connections_in_memory_state(agent):
    """A session id the agent later re-mints must not inherit an MCP client,
    config values and a cancel event from a conversation that is gone."""
    session = await _make_session(agent, "doomed")
    agent._sessions[session.agent_id] = session
    client = FakeMcpClient()
    agent._mcp_clients["doomed"] = client
    agent._tools["doomed"] = [{"name": "execute"}]
    agent._cancel_events["doomed"] = object()
    agent._session_loggers["doomed"] = object()
    agent._config_values["doomed"] = {"model": "test-model"}

    await agent.delete_session("doomed")

    assert agent._sessions == {}
    assert agent._mcp_clients == {}
    assert agent._tools == {}
    assert agent._cancel_events == {}
    assert agent._session_loggers == {}
    assert agent._config_values == {}
    # the subprocess is closed here, not left for the connection to hang up on
    assert client.exits == 1


async def test_delete_clears_a_forks_session_row_too(agent):
    """``_sessions`` is keyed on agent_id and one session can have several, so
    clearing only the id the client passed would leave the branch behind."""
    session = await _make_session(agent, "trunk")
    agent._sessions[session.agent_id] = session
    agent._sessions["trunk-1-2"] = session

    await agent.delete_session("trunk")

    assert agent._sessions == {}


async def test_initialize_advertises_delete(agent):
    """A client gates the affordance on this. Claiming ``list`` and ``fork``
    but not ``delete`` is what let a UI offer a button the agent no-oped."""
    response = await agent.initialize(protocol_version=1)
    caps = response.agent_capabilities.session_capabilities
    assert caps.list is not None
    assert caps.delete is not None
    assert caps.fork is not None
