"""Unit tests for session lifecycle.

The session/persistence contract (create/load/add_message round-trips) is
tested in tests/memory/test_store.py, which owns the storage layer. Here we
cover the cancellation-persistence contract (thinking-only turns must survive)
against the in-memory fake client. The prompt context builders that used to
live alongside these helpers moved to ``crow_cli.agent.prompt`` and are tested
in ``test_prompt.py``.
"""

import logging

import pytest

from crow_cli.agent.session import (
    AgentSession,
    lookup_or_create_prompt,
)


class TestCancelledTurnPersistence:
    """A turn cancelled while the model is still thinking has no content and
    no tool calls — the accumulated reasoning is the only record of what the
    agent was doing. It must be persisted so reconstruction hands it back to
    the next turn (and query_session can show it)."""

    @pytest.fixture
    async def session(self, memory_service, sample_prompt_template):
        prompt_id = await lookup_or_create_prompt(
            sample_prompt_template, name="test-prompt"
        )
        return await AgentSession.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Crow", "workspace": "/tmp", "display_tree": "test/"},
            tool_definitions=[],
            request_params={},
            model_identifier="test-model",
            cwd="/tmp",
            agent_idx=1,
        )

    async def test_thinking_only_turn_is_persisted(self, session, memory_service):
        await session.add_assistant_response(
            ["thinking ", "about the task"], [], [], logging.getLogger("test")
        )
        stored = memory_service._messages[session.agent_id]
        assert stored[-1] == {
            "role": "assistant",
            "content": "",
            "reasoning_content": "thinking about the task",
        }

    async def test_empty_turn_is_not_persisted(self, session, memory_service):
        before = len(memory_service._messages[session.agent_id])
        await session.add_assistant_response([], [], [], logging.getLogger("test"))
        assert len(memory_service._messages[session.agent_id]) == before
