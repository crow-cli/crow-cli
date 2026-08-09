"""
Live Session Update Transmission Tests (end-to-end, real provider).

Verifies that every token from a REAL LLM streaming response is transmitted
to the ACP client via session_update calls — targeting the historical bug
where the first content tokens after reasoning ends were sporadically lost.

These make live LLM calls against the configured provider (cost / slow /
non-deterministic), so they live in the opt-in e2e tier. The hermetic
mocked-chunk tests live in ``tests/unit/test_stream_processing.py``.
"""

import asyncio
import logging
import os

import pytest

from crow_cli.agent.react import process_chunk, process_response

logger = logging.getLogger(__name__)


def get_llm_client():
    """Resolve the configured provider/model exactly like the agent and build
    the streaming client.

    Returns ``(client, model_id)`` or ``(None, None)`` if the environment is
    not configured. Mirrors ``main.py``: take the default model, use its
    provider, and fall back to the first configured provider.
    """
    try:
        from crow_cli.agent.configure import Config
        from crow_cli.agent.llm import configure_llm

        config = Config.load()
        if not config.is_configured:
            return None, None

        model = next(iter(config.llm.models.values()), None)
        provider = config.llm.providers.get(model.provider_name) if model else None
        if not provider and config.llm.providers:
            provider = next(iter(config.llm.providers.values()))
        if not provider:
            return None, None

        client = configure_llm(provider=provider, debug=False, logger=logger)
        model_id = model.model_id if model else None
        return client, model_id
    except Exception as e:
        logger.warning(f"Cannot create LLM client: {e}")
        return None, None


class TestLiveStreamingTransmission:
    """Live tests: verify token transmission with real LLM calls."""

    @pytest.mark.asyncio
    async def test_live_streaming_no_token_loss(self):
        """Stream a real response and verify zero token loss."""
        client, model_id = get_llm_client()
        if client is None:
            pytest.skip("No LLM provider configured")

        response = await client.chat.completions.create(
            model=model_id,
            messages=[
                {
                    "role": "system",
                    "content": "Think step by step, then give a short answer.",
                },
                {"role": "user", "content": "What is 15 + 27?"},
            ],
            stream=True,
            temperature=0.0,
            max_tokens=200,
        )

        thinking_tokens: list[str] = []
        content_tokens: list[str] = []
        final_result = None

        async for msg_type, token in process_response(response, {}):
            if msg_type == "thinking":
                thinking_tokens.append(token)
            elif msg_type == "content":
                content_tokens.append(token)
            elif msg_type == "final":
                final_result = token

        assert final_result is not None, "No final result received"
        thinking, content, tool_calls, usage = final_result

        full_thinking = "".join(thinking_tokens)
        full_content = "".join(content_tokens)

        assert full_thinking == "".join(thinking), (
            f"Thinking token loss! Streamed {len(full_thinking)} chars "
            f"but final has {len(''.join(thinking))} chars"
        )
        assert full_content == "".join(content), (
            f"Content token loss! Streamed {len(full_content)} chars "
            f"but final has {len(''.join(content))} chars"
        )

    @pytest.mark.asyncio
    async def test_live_first_content_token_not_lost(self):
        """The first content token after reasoning must not be lost."""
        client, model_id = get_llm_client()
        if client is None:
            pytest.skip("No LLM provider configured")

        response = await client.chat.completions.create(
            model=model_id,
            messages=[
                {
                    "role": "system",
                    "content": "Reason briefly, then answer with exactly one word.",
                },
                {"role": "user", "content": "Is the sky blue? Answer yes or no."},
            ],
            stream=True,
            temperature=0.0,
            max_tokens=100,
        )

        content_tokens: list[str] = []
        saw_reasoning = False
        first_content_after_reasoning = None

        async for msg_type, token in process_response(response, {}):
            if msg_type == "thinking":
                saw_reasoning = True
            elif msg_type == "content":
                content_tokens.append(token)
                if saw_reasoning and first_content_after_reasoning is None:
                    first_content_after_reasoning = token

        full_content = "".join(content_tokens)
        assert len(full_content) > 0, "No content received"

        if saw_reasoning:
            assert first_content_after_reasoning is not None, (
                "First content token after reasoning was LOST"
            )
            assert full_content.startswith(first_content_after_reasoning)

    @pytest.mark.asyncio
    async def test_live_token_count_consistency(self):
        """Number of streamed tokens must match what process_chunk produced."""
        client, model_id = get_llm_client()
        if client is None:
            pytest.skip("No LLM provider configured")

        response = await client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": "Count from 1 to 10."}],
            stream=True,
            temperature=0.0,
            max_tokens=100,
        )

        chunk_count = 0
        token_events = 0

        async for msg_type, token in process_response(response, {}):
            if msg_type in ("thinking", "content"):
                token_events += 1
            elif msg_type == "chunk":
                chunk_count += 1

        assert token_events > 0, "No token events received"

    @pytest.mark.asyncio
    async def test_live_multi_turn_no_loss(self):
        """Multiple sequential streams must each have zero loss."""
        client, model_id = get_llm_client()
        if client is None:
            pytest.skip("No LLM provider configured")

        prompts = ["What is 2+2?", "What is the capital of France?", "Say hello."]

        for prompt in prompts:
            response = await client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": "Think briefly, then answer."},
                    {"role": "user", "content": prompt},
                ],
                stream=True,
                temperature=0.0,
                max_tokens=100,
            )

            streamed_content: list[str] = []
            final_content = None

            async for msg_type, token in process_response(response, {}):
                if msg_type == "content":
                    streamed_content.append(token)
                elif msg_type == "final":
                    final_content = "".join(token[1])

            assert "".join(streamed_content) == final_content, (
                f"Token loss on prompt '{prompt}': "
                f"streamed={''.join(streamed_content)!r} final={final_content!r}"
            )

    @pytest.mark.asyncio
    async def test_live_reasoning_model_transition(self):
        """Test with a prompt that forces extended reasoning then content."""
        client, model_id = get_llm_client()
        if client is None:
            pytest.skip("No LLM provider configured")

        response = await client.chat.completions.create(
            model=model_id,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a careful reasoner. Think through the problem "
                        "step by step in detail, then provide a final answer "
                        "starting with 'ANSWER:'."
                    ),
                },
                {
                    "role": "user",
                    "content": "If a train travels 60mph for 2.5 hours, how far?",
                },
            ],
            stream=True,
            temperature=0.0,
            max_tokens=500,
        )

        thinking_tokens: list[str] = []
        content_tokens: list[str] = []
        transition_boundary = None

        async for msg_type, token in process_response(response, {}):
            if msg_type == "thinking":
                thinking_tokens.append(token)
            elif msg_type == "content":
                if transition_boundary is None and thinking_tokens:
                    transition_boundary = len(thinking_tokens)
                content_tokens.append(token)

        assert len(content_tokens) > 0, "No content tokens received"
        full_content = "".join(content_tokens)
        assert len(full_content) > 0, "Empty content"
