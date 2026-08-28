"""Slash commands through the real prompt dispatch (real sqlite persistence).

``/compact`` is the reason this module exists. The handlers live apart from the
agent and nothing exercised them, so they rotted against the agent's current
attributes — a per-session logger dict instead of ``_session_logger``, config
values keyed by wire session id instead of agent id — and a slash command that
raises turns into an ACP internal error rather than a result. These tests drive
``Agent.prompt`` with slash text so dispatch and handler are covered together.
"""

from types import SimpleNamespace

import pytest
from acp.schema import TextContentBlock

from crow_cli.agent.main import AcpAgent
from crow_cli.agent.session import make_agent_session
from tests.integration.test_react_loop_cancel_integrity import SESSION_ID, FakeConn


class SummarizerLLM:
    """The LLM boundary: one non-streaming completion returning a fixed summary.

    ``compact()`` asks for a plain (non-streamed) completion; everything else in
    the compaction path — persistence, the new agent row, registry rebinding — is
    the real thing.
    """

    def __init__(self, summary: str = "## Summary\nthe conversation so far"):
        self.summary = summary
        self.create_kwargs: list[dict] = []
        outer = self

        class Completions:
            async def create(self, **kwargs):
                outer.create_kwargs.append(kwargs)
                message = SimpleNamespace(content=outer.summary)
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=message)],
                    usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                )

        self.chat = SimpleNamespace(completions=Completions())


def sent_text(conn: FakeConn) -> str:
    """All agent message text the fake client received.

    ``update_agent_message`` wraps one block per update; a list is handled too so
    this does not silently drop text if that ever changes.
    """
    chunks = []
    for update in conn.updates:
        content = getattr(update, "content", None)
        for block in content if isinstance(content, list) else [content] if content else []:
            chunks.append(getattr(block, "text", "") or "")
    return "\n".join(chunks)


@pytest.fixture
async def agent_with_history(test_config, tmp_path):
    """A live session with a few turns, wired into an agent the way a real
    connection would have it (tools provisioned, model resolved)."""
    config = test_config
    config.db_uri = f"sqlite:///{tmp_path / 'crow.db'}"
    session = await make_agent_session(
        config,
        tools=[],
        model_id="test-model-id",
        cwd=str(tmp_path),
        session_id=SESSION_ID,
    )
    for message in (
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
        {"role": "user", "content": "third"},
    ):
        await session.add_message(message)

    agent = AcpAgent(config=config, hooks=[])
    agent._conn = FakeConn()
    agent._sessions[session.agent_id] = session
    agent._tools[session.session_id] = []
    agent._config_values[session.session_id] = {"model": "test-provider:test-model-id"}
    return agent, session


async def test_compact_slash_command_creates_a_new_generation(agent_with_history, monkeypatch):
    """/compact must summarize through the LLM and hand back a compacted session."""
    agent, session = agent_with_history
    llm = SummarizerLLM()
    monkeypatch.setattr("crow_cli.agent.slash.configure_llm", lambda **kwargs: llm)

    response = await agent.prompt([TextContentBlock(type="text", text="/compact")], session_id=SESSION_ID)

    assert response.stop_reason == "end_turn"
    assert llm.create_kwargs, "the compaction prompt never reached the LLM"
    assert "compact" in sent_text(agent._conn).lower()


async def test_compact_slash_command_rebinds_the_live_session(agent_with_history, monkeypatch):
    """After /compact the next resolution returns the new generation, not the old.

    Compaction mints a new agent row inside the same wire sessionId; the agent's
    cache has to hold it or the following prompt replays the uncompressed history.
    """
    agent, session = agent_with_history
    monkeypatch.setattr(
        "crow_cli.agent.slash.configure_llm", lambda **kwargs: SummarizerLLM()
    )

    await agent.prompt([TextContentBlock(type="text", text="/compact")], session_id=SESSION_ID)

    compacted = await agent._resolve_session(SESSION_ID)
    assert compacted.agent_idx == session.agent_idx + 1
    assert len(compacted.messages) < len(session.messages)


async def test_compact_with_too_little_history_says_so(agent_with_history, monkeypatch):
    """No LLM call and a human-readable refusal when there is nothing to compact."""
    agent, session = agent_with_history
    session.messages = [session.messages[0]] if session.messages else []
    called = []
    monkeypatch.setattr(
        "crow_cli.agent.slash.configure_llm",
        lambda **kwargs: called.append(1) or SummarizerLLM(),
    )

    await agent.prompt([TextContentBlock(type="text", text="/compact")], session_id=SESSION_ID)

    assert not called
    assert "not enough conversation history" in sent_text(agent._conn).lower()


async def test_unknown_command_is_reported(agent_with_history):
    await agent_with_history[0].prompt(
        [TextContentBlock(type="text", text="/nope")], session_id=SESSION_ID
    )
    assert "Unknown command: /nope" in sent_text(agent_with_history[0]._conn)


async def test_help_lists_registered_commands(agent_with_history):
    await agent_with_history[0].prompt(
        [TextContentBlock(type="text", text="/help")], session_id=SESSION_ID
    )
    text = sent_text(agent_with_history[0]._conn)
    assert "/compact" in text
    assert "/stop" in text
