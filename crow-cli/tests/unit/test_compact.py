"""Unit tests for compaction (no live LLM, no live service).

The summarization LLM call is mocked, and persistence is faked via the
``memory_service`` fixture (an in-memory stand-in for the sqlite MemoryClient).

``compact()`` (crow_cli.agent.compact) is async and takes a ``Config``. It
summarizes the conversation into a NEW agent record (``agent_idx + 1``) whose
history is ``[system, user(summary + last_messages)]``, and leaves the
ORIGINAL session untouched. The ``on_compact`` callback receives the original
``agent_id`` and the new session.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from crow_cli.agent.compact import compact
from crow_cli.agent.configure import Config
from crow_cli.agent.session import AgentSession, lookup_or_create_prompt


class TestCompaction:
    """Test the new-agent-record compaction contract without live LLM calls."""

    @pytest.fixture
    def compact_config(self, memory_service):
        """Real config; persistence is redirected to the in-memory fake."""
        config = Config.load()
        # Inline template so make_agent_session doesn't read a prompt file.
        config.system_prompt = "You are {{name}}. Workspace: {{workspace}}."
        return config

    @pytest.fixture
    async def setup_session(self, memory_service, sample_prompt_template):
        """Create a 1-positioned session with a long conversation."""
        prompt_id = await lookup_or_create_prompt(sample_prompt_template, name="test-prompt")
        session = await AgentSession.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Crow", "workspace": "/tmp", "display_tree": "test/"},
            tool_definitions=[],
            request_params={"temperature": 0.7},
            model_identifier="test-model",
            cwd="/tmp",
            agent_idx=1,
        )
        for i in range(20):
            await session.add_message({"role": "user", "content": f"User message {i}"})
            await session.add_message(
                {"role": "assistant", "content": f"Assistant response {i}"}
            )
        return session

    @pytest.fixture
    def mock_llm(self):
        """Mock LLM whose summarization call returns a fixed summary."""
        llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "COMPACTED SUMMARY"
        mock_response.usage = MagicMock(
            prompt_tokens=100, completion_tokens=50, total_tokens=150
        )
        llm.chat.completions.create = AsyncMock(return_value=mock_response)
        return llm

    @pytest.mark.asyncio
    async def test_compact_calls_llm_with_tool_choice_none(
        self, setup_session, mock_llm, compact_config
    ):
        """Compaction summarizes via a single non-tool-calling request."""
        session = setup_session
        await compact(session, mock_llm, compact_config, logger=MagicMock())

        mock_llm.chat.completions.create.assert_called_once()
        kwargs = mock_llm.chat.completions.create.call_args.kwargs
        assert kwargs["tool_choice"] == "none"
        assert kwargs["model"] == "test-model"

    @pytest.mark.asyncio
    async def test_compact_uses_config_temperature_not_session_params(
        self, setup_session, mock_llm, compact_config
    ):
        """Compaction samples with config.TEMPERATURE — NOT the session's
        request_params (0.7 here) and NOT the provider default of 1.0, which
        makes the model ramble instead of compress."""
        compact_config.TEMPERATURE = 0.4
        await compact(setup_session, mock_llm, compact_config, logger=MagicMock())

        kwargs = mock_llm.chat.completions.create.call_args.kwargs
        assert kwargs["temperature"] == 0.4
        assert "reasoning_effort" not in kwargs

    @pytest.mark.asyncio
    async def test_compact_uses_reasoning_effort_instead_of_temperature(
        self, setup_session, mock_llm, compact_config
    ):
        """Reasoning models reject temperature — compaction must swap too."""
        compact_config.reasoning_effort = "high"
        await compact(setup_session, mock_llm, compact_config, logger=MagicMock())

        kwargs = mock_llm.chat.completions.create.call_args.kwargs
        assert kwargs["reasoning_effort"] == "high"
        assert "temperature" not in kwargs

    @pytest.mark.asyncio
    async def test_compact_creates_new_agent_record(
        self, setup_session, mock_llm, compact_config
    ):
        """Compaction creates a NEW agent record at agent_idx + 1."""
        session = setup_session
        result = await compact(session, mock_llm, compact_config, logger=MagicMock())

        assert result.agent_idx == session.agent_idx + 1
        assert result.agent_id == f"{session.session_id}-{session.agent_idx + 1}"
        assert result.agent_id != session.agent_id

        # The new record is persisted and loadable.
        reloaded = await AgentSession.load(result.agent_id)
        assert reloaded.agent_id == result.agent_id

    @pytest.mark.asyncio
    async def test_compact_new_session_is_summarized(
        self, setup_session, mock_llm, compact_config
    ):
        """The new session's history is [system, user(summary + last messages)]."""
        session = setup_session
        result = await compact(session, mock_llm, compact_config, logger=MagicMock())

        assert len(result.messages) == 2
        assert result.messages[0]["role"] == "system"
        assert result.messages[1]["role"] == "user"
        assert "COMPACTED SUMMARY" in result.messages[1]["content"]

    @pytest.mark.asyncio
    async def test_compact_preserves_original_session(
        self, setup_session, mock_llm, compact_config
    ):
        """The original session is left completely untouched."""
        session = setup_session
        original_count = len(session.messages)
        original_agent_id = session.agent_id

        await compact(session, mock_llm, compact_config, logger=MagicMock())

        # In-memory object unchanged.
        assert len(session.messages) == original_count
        # Persisted original record unchanged.
        reloaded = await AgentSession.load(original_agent_id)
        assert len(reloaded.messages) == original_count

    @pytest.mark.asyncio
    async def test_compact_on_compact_callback(
        self, setup_session, mock_llm, compact_config
    ):
        """on_compact receives the original agent_id and the new session."""
        session = setup_session
        calls = []

        def on_compact(old_agent_id, new_session):
            calls.append((old_agent_id, new_session))

        result = await compact(
            session, mock_llm, compact_config, on_compact=on_compact, logger=MagicMock()
        )

        assert len(calls) == 1
        old_agent_id, new_session = calls[0]
        assert old_agent_id == session.agent_id  # agent_id, not session_id
        assert new_session is result

    @pytest.mark.asyncio
    async def test_compact_preserves_tools_and_model(
        self, setup_session, mock_llm, compact_config
    ):
        """Tools and model identifier carry over to the new session."""
        session = setup_session
        session.tools = [{"name": "read_file", "description": "Read a file"}]

        result = await compact(session, mock_llm, compact_config, logger=MagicMock())

        assert result.tools == session.tools
        assert result.model_identifier == session.model_identifier
