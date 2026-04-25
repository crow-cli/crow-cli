"""
Session Update Transmission Tests.

Tests that verify every single token from the LLM streaming response
is transmitted to the ACP client via session_update calls.

This targets the bug where the first content tokens after reasoning end
are sporadically lost during transmission.

Unit tests use mock chunks to test parsing logic.
Integration tests use crow-cli's litellm provider config.
"""

import asyncio
import base64
import logging
import os
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from crow_cli.agent.configure import Config, get_default_config_dir
from crow_cli.agent.llm import configure_llm
from crow_cli.agent.react import process_chunk, process_response, react_loop

# ---------------------------------------------------------------------------
# Get the litellm client from crow-cli config
# ---------------------------------------------------------------------------


def get_litellm_client():
    """Get the litellm client from crow-cli's actual config."""
    config_dir = get_default_config_dir()
    config = Config.load(config_dir=config_dir)

    provider = config.llm.providers.get("litellm")
    if not provider:
        pytest.skip("litellm provider not configured")

    llm = configure_llm(provider=provider, debug=False)

    # Use qwen3.5-plus (has reasoning support)
    model_id = None
    if "qwen3.5-plus" in config.llm.models:
        model_id = config.llm.models["qwen3.5-plus"].model_id
    elif config.llm.models:
        model_id = next(iter(config.llm.models.values())).model_id
    else:
        pytest.skip("No models configured for litellm")

    return llm, model_id


# ---------------------------------------------------------------------------
# Mock streaming chunk helpers (for unit tests only)
# ---------------------------------------------------------------------------


@dataclass
class MockDelta:
    """Mimics openai.types.chat.chat_completion_chunk.ChoiceDelta"""

    content: str | None = None
    reasoning_content: str | None = None
    tool_calls: Any = None


@dataclass
class MockChoice:
    """Mimics openai.types.chat.chat_completion_chunk.Choice"""

    delta: MockDelta


@dataclass
class MockChunk:
    """Mimics openai.types.chat.chat_completion_chunk.ChatCompletionChunk"""

    choices: list[MockChoice]
    usage: Any = None


def mk_chunk(content: str | None = None, reasoning: str | None = None) -> MockChunk:
    """Create a mock streaming chunk."""
    return MockChunk(
        choices=[
            MockChoice(delta=MockDelta(content=content, reasoning_content=reasoning))
        ]
    )


def mk_usage_chunk(
    prompt_tokens=100, completion_tokens=50, total_tokens=150
) -> MockChunk:
    """Create a final usage chunk."""
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    usage.total_tokens = total_tokens
    return MockChunk(choices=[], usage=usage)


async def async_iter(chunks: list):
    """Async generator that yields mock chunks."""
    for chunk in chunks:
        yield chunk


# ---------------------------------------------------------------------------
# Unit tests for process_chunk
# ---------------------------------------------------------------------------


class TestProcessChunk:
    """Test that process_chunk correctly handles every type of chunk."""

    def test_reasoning_chunk_only(self):
        thinking, content, tool_calls = [], [], {}
        chunk = mk_chunk(reasoning="Let me think")
        result = process_chunk(chunk, thinking, content, tool_calls)
        assert result[3] == ("thinking", "Let me think")
        assert thinking == ["Let me think"]

    def test_content_chunk_only(self):
        thinking, content, tool_calls = [], [], {}
        chunk = mk_chunk(content="Hello")
        result = process_chunk(chunk, thinking, content, tool_calls)
        assert result[3] == ("content", "Hello")
        assert content == ["Hello"]

    def test_reasoning_then_content_transition(self):
        thinking, content, tool_calls = [], [], {}
        chunk1 = mk_chunk(reasoning="thinking...")
        process_chunk(chunk1, thinking, content, tool_calls)
        assert thinking == ["thinking..."]

        chunk2 = mk_chunk(content="Yes, the answer")
        result = process_chunk(chunk2, thinking, content, tool_calls)
        assert result[3] == ("content", "Yes, the answer")
        assert content == ["Yes, the answer"]

    def test_chunk_with_both_fields_empty_reasoning(self):
        """reasoning_content="" is falsy, so content wins."""
        thinking, content, tool_calls = [], [], {}
        delta = MockDelta(content="Yes", reasoning_content="")
        chunk = MockChunk(choices=[MockChoice(delta=delta)])
        result = process_chunk(chunk, thinking, content, tool_calls)
        assert result[3] == ("content", "Yes")
        assert content == ["Yes"]

    def test_chunk_with_both_fields_nonempty_content_is_lost(self):
        """Documents the if/else limitation: content lost if both non-empty."""
        thinking, content, tool_calls = [], [], {}
        delta = MockDelta(content="Yes", reasoning_content="thinking...")
        chunk = MockChunk(choices=[MockChoice(delta=delta)])
        result = process_chunk(chunk, thinking, content, tool_calls)
        assert result[3] == ("thinking", "thinking...")
        assert content == [], (
            "Content lost when both fields non-empty (documented behavior)"
        )

    def test_empty_string_content_not_yielded(self):
        thinking, content, tool_calls = [], [], {}
        chunk = mk_chunk(content="")
        result = process_chunk(chunk, thinking, content, tool_calls)
        assert result[3] == (None, None)

    def test_final_usage_chunk(self):
        thinking, content, tool_calls = [], [], {}
        chunk = mk_usage_chunk()
        result = process_chunk(chunk, thinking, content, tool_calls)
        assert result[3] == (None, None)


# ---------------------------------------------------------------------------
# Unit tests for process_response
# ---------------------------------------------------------------------------


class TestProcessResponse:
    """Test that process_response yields every token from the stream."""

    @pytest.mark.asyncio
    async def test_full_reasoning_then_content_stream(self):
        async def mock_stream():
            yield mk_chunk(reasoning="Let ")
            yield mk_chunk(reasoning="me ")
            yield mk_chunk(reasoning="think")
            yield mk_chunk(content="Yes")
            yield mk_chunk(content=", the ")
            yield mk_chunk(content="answer")
            yield mk_chunk(content=" is 42")
            yield mk_usage_chunk(100, 50, 150)

        accumulator = {"thinking": [], "content": [], "tool_calls": {}}
        tokens = []
        async for msg_type, token in process_response(mock_stream(), accumulator):
            tokens.append((msg_type, token))

        assert tokens[0] == ("thinking", "Let ")
        assert tokens[3] == ("content", "Yes")

        final_type, final_data = tokens[-1]
        assert final_type == "final"
        thinking, content, _, _ = final_data
        assert "".join(thinking) == "Let me think"
        assert "".join(content) == "Yes, the answer is 42"

    @pytest.mark.asyncio
    async def test_first_content_token_after_reasoning_is_yielded(self):
        async def mock_stream():
            yield mk_chunk(reasoning="reasoning...")
            yield mk_chunk(content="First")
            yield mk_chunk(content=" token")
            yield mk_usage_chunk()

        accumulator = {"thinking": [], "content": [], "tool_calls": {}}
        tokens = []
        async for msg_type, token in process_response(mock_stream(), accumulator):
            tokens.append((msg_type, token))

        content_tokens = [(t, tok) for t, tok in tokens if t == "content"]
        assert len(content_tokens) >= 1
        assert content_tokens[0] == ("content", "First")

    @pytest.mark.asyncio
    async def test_no_token_loss_in_long_stream(self):
        async def mock_stream():
            for i in range(100):
                yield mk_chunk(reasoning=f"r{i}")
            for i in range(100):
                yield mk_chunk(content=f"c{i}")
            yield mk_usage_chunk(5000, 2000, 7000)

        accumulator = {"thinking": [], "content": [], "tool_calls": {}}
        thinking_count = 0
        content_count = 0

        async for msg_type, token in process_response(mock_stream(), accumulator):
            if msg_type == "content":
                content_count += 1
            elif msg_type == "thinking":
                thinking_count += 1

        assert thinking_count == 100
        assert content_count == 100


# ---------------------------------------------------------------------------
# Live integration tests using crow-cli's litellm provider
# ---------------------------------------------------------------------------


class TestLiveStreamingTransmission:
    """
    Test the full streaming pipeline using crow-cli's actual litellm provider.
    """

    @pytest.mark.asyncio
    async def test_live_streaming_reasoning_to_content_transition(
        self, temp_db_uri, sample_prompt_template
    ):
        """
        Use crow-cli's litellm to test the reasoning→content transition.
        qwen3.5-plus supports reasoning, so this exercises the exact transition point.
        """
        llm, model_id = get_litellm_client()
        logger = logging.getLogger("test_live")
        logger.setLevel(logging.INFO)
        logger.addHandler(logging.NullHandler())

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is 17 * 23? Think step by step."},
        ]

        response = await llm.chat.completions.create(
            model=model_id,
            messages=messages,
            stream=True,
            max_tokens=500,
            stream_options={"include_usage": True},
        )

        accumulator = {"thinking": [], "content": [], "tool_calls": {}}
        content_tokens = []
        thinking_tokens = []
        final_usage = None

        async for msg_type, token in process_response(response, accumulator):
            if msg_type == "thinking":
                thinking_tokens.append(token)
            elif msg_type == "content":
                content_tokens.append(token)
            elif msg_type == "final":
                thinking, content, tool_calls, usage = token
                final_usage = usage

        full_thinking = "".join(thinking_tokens)
        full_content = "".join(content_tokens)

        # Verify consistency between yielded tokens and accumulator
        if thinking_tokens:
            assert full_thinking == "".join(accumulator["thinking"]), (
                f"Thinking tokens lost!\n"
                f"  yielded: {full_thinking!r}\n"
                f"  accumulator: {''.join(accumulator['thinking'])!r}"
            )

        assert full_content == "".join(accumulator["content"]), (
            f"Content tokens lost!\n"
            f"  yielded: {full_content!r}\n"
            f"  accumulator: {''.join(accumulator['content'])!r}"
        )

        assert len(content_tokens) > 0, "No content tokens received from LLM"

        # The critical check: if there was reasoning followed by content,
        # the first content token after reasoning must NOT be lost
        if thinking_tokens and content_tokens:
            # The transition point: last thinking token, first content token
            # must both be present and non-empty
            assert len(thinking_tokens[-1]) > 0, "Last thinking token was empty"
            assert len(content_tokens[0]) > 0, (
                f"First content token after reasoning was lost/empty! "
                f"Got: {content_tokens[0]!r}"
            )

        print(f"✅ Live streaming test passed:")
        print(f"   Model: {model_id}")
        print(f"   Thinking tokens: {len(thinking_tokens)}")
        print(f"   Content tokens: {len(content_tokens)}")
        print(f"   Thinking chars: {len(full_thinking)}")
        print(f"   Content chars: {len(full_content)}")
        if final_usage:
            print(f"   Total tokens: {final_usage['total_tokens']}")

    @pytest.mark.asyncio
    async def test_live_streaming_no_loss_over_many_tokens(
        self, temp_db_uri, sample_prompt_template
    ):
        """
        Stream a longer response and verify no token loss at any point.
        """
        llm, model_id = get_litellm_client()
        logger = logging.getLogger("test_live_long")
        logger.setLevel(logging.INFO)
        logger.addHandler(logging.NullHandler())

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": (
                    "Write a detailed explanation of how transformers work. "
                    "Cover attention mechanisms, positional encoding, and "
                    "encoder-decoder architecture. Write at least 5 paragraphs."
                ),
            },
        ]

        response = await llm.chat.completions.create(
            model=model_id,
            messages=messages,
            stream=True,
            max_tokens=2000,
            stream_options={"include_usage": True},
        )

        accumulator = {"thinking": [], "content": [], "tool_calls": {}}
        thinking_count = 0
        content_count = 0
        final_usage = None

        async for msg_type, token in process_response(response, accumulator):
            if msg_type == "thinking":
                thinking_count += 1
            elif msg_type == "content":
                content_count += 1
            elif msg_type == "final":
                _, _, _, usage = token
                final_usage = usage

        full_content = "".join(accumulator["content"])
        full_thinking = "".join(accumulator["thinking"])

        assert len(full_content) > 200, f"Response too short: {len(full_content)} chars"

        # Every yielded token must match accumulator
        assert thinking_count == len(accumulator["thinking"]), (
            f"Thinking count mismatch: {thinking_count} vs {len(accumulator['thinking'])}"
        )
        assert content_count == len(accumulator["content"]), (
            f"Content count mismatch: {content_count} vs {len(accumulator['content'])}"
        )

        print(f"✅ Live streaming long response test passed:")
        print(f"   Model: {model_id}")
        print(f"   Thinking tokens: {thinking_count}")
        print(f"   Content tokens: {content_count}")
        print(f"   Thinking chars: {len(full_thinking)}")
        print(f"   Content chars: {len(full_content)}")
        if final_usage:
            print(f"   Total tokens: {final_usage['total_tokens']}")

    @pytest.mark.asyncio
    async def test_live_streaming_with_multimodal_prompt(
        self, temp_db_uri, sample_prompt_template
    ):
        """
        Test with an image prompt - the exact scenario where the bug was reported.
        """
        llm, model_id = get_litellm_client()
        logger = logging.getLogger("test_live_multimodal")
        logger.setLevel(logging.INFO)
        logger.addHandler(logging.NullHandler())

        # Valid 16x16 red PNG (generated with struct+zlib, verified with PIL)
        tiny_png = (
            "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAF0lEQVR4"
            "nGP4z8BAEiJN9aiGUQ1DSgMAkPn/Afnh+ngAAAAASUVORK5CYII="
        )

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What do you see in this image?"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{tiny_png}"},
                    },
                ],
            },
        ]

        response = await llm.chat.completions.create(
            model=model_id,
            messages=messages,
            stream=True,
            max_tokens=500,
            stream_options={"include_usage": True},
        )

        accumulator = {"thinking": [], "content": [], "tool_calls": {}}
        content_tokens = []
        thinking_tokens = []
        first_content_token = None
        first_thinking_after_content = None
        final_usage = None

        async for msg_type, token in process_response(response, accumulator):
            if msg_type == "thinking":
                thinking_tokens.append(token)
            elif msg_type == "content":
                if first_content_token is None:
                    first_content_token = token
                content_tokens.append(token)
            elif msg_type == "final":
                thinking, content, tool_calls, usage = token
                final_usage = usage

        full_thinking = "".join(thinking_tokens)
        full_content = "".join(content_tokens)

        # Must have received content
        assert len(content_tokens) > 0, "No content tokens received"

        # First content token must not be empty
        assert first_content_token is not None
        assert len(first_content_token) > 0, (
            f"First content token was empty: {first_content_token!r}"
        )

        # Verify consistency
        assert full_content == "".join(accumulator["content"]), (
            f"Content mismatch for multimodal prompt"
        )

        print(f"✅ Live multimodal streaming test passed:")
        print(f"   Model: {model_id}")
        print(f"   First content token: {first_content_token!r}")
        print(f"   Content tokens: {len(content_tokens)}")
        print(f"   Content length: {len(full_content)} chars")
        if final_usage:
            print(f"   Total tokens: {final_usage['total_tokens']}")


# ---------------------------------------------------------------------------
# Tests for reasoning -> content transition (mock-based edge cases)
# ---------------------------------------------------------------------------


class TestReasoningToContentTransition:
    """Tests for the exact moment reasoning ends and content begins."""

    @pytest.mark.asyncio
    async def test_transition_chunk_with_empty_reasoning(self):
        thinking, content, tool_calls = [], [], {}
        chunk1 = mk_chunk(reasoning="done thinking")
        process_chunk(chunk1, thinking, content, tool_calls)

        delta = MockDelta(content="First", reasoning_content="")
        chunk2 = MockChunk(choices=[MockChoice(delta=delta)])
        result = process_chunk(chunk2, thinking, content, tool_calls)
        assert result[3] == ("content", "First")
        assert content == ["First"]

    @pytest.mark.asyncio
    async def test_transition_chunk_with_none_reasoning(self):
        thinking, content, tool_calls = [], [], {}
        delta = MockDelta(content="First", reasoning_content=None)
        chunk = MockChunk(choices=[MockChoice(delta=delta)])
        result = process_chunk(chunk, thinking, content, tool_calls)
        assert result[3] == ("content", "First")
        assert content == ["First"]

    @pytest.mark.asyncio
    async def test_full_transition_stream_no_loss(self):
        async def mock_stream():
            for word in ["I ", "need ", "to ", "analyze ", "this "]:
                yield mk_chunk(reasoning=word)
            yield mk_chunk(reasoning="carefully")
            yield mk_chunk(content="The ")
            for word in ["analysis ", "shows ", "a ", "cat ", "in ", "a ", "box"]:
                yield mk_chunk(content=word)
            yield mk_usage_chunk(500, 200, 700)

        accumulator = {"thinking": [], "content": [], "tool_calls": {}}
        tokens = []
        async for msg_type, token in process_response(mock_stream(), accumulator):
            tokens.append((msg_type, token))

        thinking_tokens = [tok for t, tok in tokens if t == "thinking"]
        content_tokens = [tok for t, tok in tokens if t == "content"]

        assert "".join(thinking_tokens) == "I need to analyze this carefully"
        assert content_tokens[0] == "The "
        assert "".join(content_tokens) == "The analysis shows a cat in a box"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
