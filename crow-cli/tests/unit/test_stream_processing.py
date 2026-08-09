"""
Stream-processing unit tests (hermetic — no LLM, no network).

These verify the chunk/response processing that underpins token-faithful
streaming: every reasoning/content/tool token must be accounted for and
surfaced as a ``(kind, text)`` event.

``process_chunk`` returns ``(thinking, content, tool_calls, new_tokens)``
where ``new_tokens`` is a LIST of ``(kind, text)`` events — a single chunk
can carry both reasoning and content (e.g. the reasoning->content
transition), and both are emitted so nothing is lost.

Live end-to-end streaming tests (real provider) live in
``tests/e2e/test_session_update_transmission.py``.
"""

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from crow_cli.agent.react import process_chunk, process_response


# ---------------------------------------------------------------------------
# Mock chunk objects (shaped like OpenAI chat-completion stream chunks)
# ---------------------------------------------------------------------------


@dataclass
class MockDelta:
    reasoning_content: str | None = None
    content: str | None = None
    tool_calls: list | None = None


@dataclass
class MockChoice:
    delta: MockDelta
    finish_reason: str | None = None


@dataclass
class MockChunk:
    choices: list
    id: str = "mock-id"
    model: str = "mock-model"
    usage: Any = None


def mk_chunk(
    reasoning: str | None = None,
    content: str | None = None,
    tool_calls: list | None = None,
    finish_reason: str | None = None,
) -> MockChunk:
    return MockChunk(
        choices=[
            MockChoice(
                delta=MockDelta(
                    reasoning_content=reasoning,
                    content=content,
                    tool_calls=tool_calls,
                ),
                finish_reason=finish_reason,
            )
        ]
    )


def mk_usage_chunk(prompt_tokens: int, completion_tokens: int) -> MockChunk:
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    usage.total_tokens = prompt_tokens + completion_tokens
    return MockChunk(choices=[], usage=usage)


async def async_iter(items):
    for item in items:
        yield item


# ---------------------------------------------------------------------------
# process_chunk — token accounting
# ---------------------------------------------------------------------------


class TestProcessChunk:
    """Verify process_chunk yields a token event for every non-empty field."""

    def test_single_reasoning_chunk(self):
        chunk = mk_chunk(reasoning="Let me")
        thinking: list[str] = []
        content: list[str] = []
        result = process_chunk(chunk, thinking, content, {})
        assert result[0] == ["Let me"]
        assert result[1] == []
        assert result[3] == [("thinking", "Let me")]

    def test_single_content_chunk(self):
        chunk = mk_chunk(content="The answer")
        result = process_chunk(chunk, [], [], {})
        assert result[0] == []
        assert result[1] == ["The answer"]
        assert result[3] == [("content", "The answer")]

    def test_transition_chunk_with_both_fields(self):
        """A chunk carrying BOTH reasoning and content emits both events.

        This is the token-loss fix: the old if/else dropped the content
        token when reasoning was also present. Now each non-empty field is
        processed independently, so nothing is lost.
        """
        chunk = mk_chunk(reasoning="thinking...", content="Yes")
        thinking: list[str] = []
        content: list[str] = []
        result = process_chunk(chunk, thinking, content, {})
        assert result[0] == ["thinking..."]
        assert result[1] == ["Yes"]  # content is NOT lost
        assert result[3] == [("thinking", "thinking..."), ("content", "Yes")]

    def test_empty_string_content_not_yielded(self):
        """Empty-string content must not produce a token event."""
        chunk = mk_chunk(reasoning="think", content="")
        result = process_chunk(chunk, [], [], {})
        assert result[3] == [("thinking", "think")]
        assert result[1] == []

    def test_final_usage_chunk(self):
        """A chunk with no choices yields no token events."""
        chunk = mk_usage_chunk(100, 50)
        result = process_chunk(chunk, [], [], {})
        assert result[3] == []

    def test_tool_call_chunk(self):
        tc = MagicMock()
        tc.index = 0
        tc.id = "call_1"
        tc.function.name = "search"
        tc.function.arguments = '{"q":'
        chunk = mk_chunk(tool_calls=[tc])
        result = process_chunk(chunk, [], [], {})
        # tool_calls accumulator is keyed by the chunk's tool_call index
        assert 0 in result[2]
        assert result[2][0]["id"] == "call_1"
        assert result[2][0]["function_name"] == "search"
        # a named tool call emits a single ("tool_call", (name, args)) event;
        # ("tool_args", ...) is only for name-less argument-continuation chunks
        assert result[3] == [("tool_call", ("search", '{"q":'))]

    def test_empty_chunk(self):
        """A chunk with empty delta yields no token events."""
        chunk = mk_chunk()
        result = process_chunk(chunk, [], [], {})
        assert result[3] == []


# ---------------------------------------------------------------------------
# process_response — full stream
# ---------------------------------------------------------------------------


class TestProcessResponse:
    """Verify process_response transmits every token via session_update."""

    @pytest.mark.asyncio
    async def test_all_reasoning_tokens_transmitted(self):
        chunks = [
            mk_chunk(reasoning="Let "),
            mk_chunk(reasoning="me "),
            mk_chunk(reasoning="think."),
            mk_usage_chunk(10, 5),
        ]

        tokens: list[tuple[str, str]] = []
        async for msg_type, token in process_response(async_iter(chunks), {}):
            if msg_type == "thinking":
                tokens.append(("thinking", token))
            elif msg_type == "content":
                tokens.append(("content", token))

        assert tokens == [
            ("thinking", "Let "),
            ("thinking", "me "),
            ("thinking", "think."),
        ]

    @pytest.mark.asyncio
    async def test_all_content_tokens_transmitted(self):
        chunks = [
            mk_chunk(content="The "),
            mk_chunk(content="answer "),
            mk_chunk(content="is 42."),
            mk_usage_chunk(10, 5),
        ]

        tokens: list[tuple[str, str]] = []
        async for msg_type, token in process_response(async_iter(chunks), {}):
            if msg_type in ("thinking", "content"):
                tokens.append((msg_type, token))

        assert tokens == [
            ("content", "The "),
            ("content", "answer "),
            ("content", "is 42."),
        ]

    @pytest.mark.asyncio
    async def test_reasoning_to_content_transition_no_loss(self):
        """The exact bug scenario: reasoning ends, content begins.

        Even when the transition happens within a single chunk, both the
        last reasoning token and the first content token must be transmitted.
        """
        chunks = [
            mk_chunk(reasoning="Step 1: "),
            mk_chunk(reasoning="compute. "),
            mk_chunk(reasoning="done.", content="The"),  # transition chunk
            mk_chunk(content=" answer"),
            mk_chunk(content=" is 42."),
            mk_usage_chunk(10, 5),
        ]

        tokens: list[tuple[str, str]] = []
        async for msg_type, token in process_response(async_iter(chunks), {}):
            if msg_type in ("thinking", "content"):
                tokens.append((msg_type, token))

        assert tokens == [
            ("thinking", "Step 1: "),
            ("thinking", "compute. "),
            ("thinking", "done."),
            ("content", "The"),  # first content token — must NOT be lost
            ("content", " answer"),
            ("content", " is 42."),
        ]


# ---------------------------------------------------------------------------
# The specific bug: reasoning -> content transition
# ---------------------------------------------------------------------------


class TestReasoningToContentTransition:
    """
    Regression tests for the token-loss bug at the reasoning->content
    boundary.
    """

    def test_transition_chunk_with_empty_reasoning(self):
        """When reasoning_content is empty string and content is non-empty."""
        chunk = mk_chunk(reasoning="", content="Yes")
        thinking: list[str] = []
        content: list[str] = []
        result = process_chunk(chunk, thinking, content, {})
        assert result[1] == ["Yes"]
        assert result[3] == [("content", "Yes")]

    def test_transition_chunk_with_none_reasoning(self):
        """When reasoning_content is None and content is non-empty."""
        chunk = mk_chunk(reasoning=None, content="Yes")
        thinking: list[str] = []
        content: list[str] = []
        result = process_chunk(chunk, thinking, content, {})
        assert result[1] == ["Yes"]
        assert result[3] == [("content", "Yes")]

    @pytest.mark.asyncio
    async def test_full_transition_stream_no_loss(self):
        """Full stream: reasoning chunks then content chunks. Zero loss."""
        chunks = [
            mk_chunk(reasoning="A"),
            mk_chunk(reasoning="B"),
            mk_chunk(reasoning="C"),
            mk_chunk(content="1"),  # first content — the bug drops this
            mk_chunk(content="2"),
            mk_chunk(content="3"),
            mk_usage_chunk(10, 6),
        ]

        thinking_tokens: list[str] = []
        content_tokens: list[str] = []
        async for msg_type, token in process_response(async_iter(chunks), {}):
            if msg_type == "thinking":
                thinking_tokens.append(token)
            elif msg_type == "content":
                content_tokens.append(token)

        assert thinking_tokens == ["A", "B", "C"]
        assert content_tokens == ["1", "2", "3"], (
            f"Content tokens lost! Got {content_tokens}, expected ['1', '2', '3']"
        )


# ---------------------------------------------------------------------------
# Chunk accounting (mocked process_chunk)
# ---------------------------------------------------------------------------


class TestChunkAccounting:
    @pytest.mark.asyncio
    async def test_all_chunks_produce_tokens(self):
        """Every chunk with non-empty delta must produce a token event.

        Uses mocked process_chunk to isolate: if this fails, the bug is in
        process_chunk's token detection, not in transmission.
        """
        chunks = [
            mk_chunk(reasoning="A"),
            mk_chunk(reasoning="B"),
            mk_chunk(content="1"),
            mk_chunk(content="2"),
            mk_usage_chunk(10, 4),
        ]

        call_count = 0
        token_count = 0

        original = process_chunk

        def counting_process_chunk(chunk, thinking, content, tool_calls):
            nonlocal call_count, token_count
            call_count += 1
            result = original(chunk, thinking, content, tool_calls)
            token_count += len(result[3])
            return result

        with patch("crow_cli.agent.react.process_chunk", counting_process_chunk):
            async for _ in process_response(async_iter(chunks), {}):
                pass

        assert call_count == 5, f"Expected 5 process_chunk calls, got {call_count}"
        assert token_count == 4, (
            f"Expected 4 token events from process_chunk, got {token_count}"
        )
