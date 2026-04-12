"""
Live LLM Integration Tests.

These tests actually call the LLM API to verify the full round-trip:
1. Session creates messages in memory
2. React loop sends to LLM
3. LLM responds
4. Response persists to database
5. Reloaded session matches in-memory state

IMPORTANT: These tests require a live LLM API to be configured.
They can be skipped if no API is available by setting SKIP_LIVE_TESTS=true

Usage:
    # Run all tests (skip live LLM tests if no API)
    uv --project . run pytest tests/ -v

    # Run live LLM tests (requires API configuration)
    uv --project . run pytest tests/test_live_llm_integration.py -v -s

    # Skip live tests explicitly
    SKIP_LIVE_TESTS=true uv --project . run pytest tests/test_live_llm_integration.py -v
"""

import asyncio
import logging
import os

import pytest
from openai import AsyncOpenAI

from crow_cli.agent.configure import Config, get_default_config_dir
from crow_cli.agent.llm import configure_llm
from crow_cli.agent.logger import setup_logger
from crow_cli.agent.session import Session, lookup_or_create_prompt

# Skip marker for live tests
pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_TESTS", "false").lower() == "true",
    reason="Live LLM tests skipped. Set SKIP_LIVE_TESTS=false to enable.",
)


def get_live_llm_client():
    """Get a live LLM client from configuration."""
    try:
        config_dir = get_default_config_dir()
        config = Config.load(config_dir)

        # Get first available provider
        if not config.llm.providers:
            pytest.skip("No LLM providers configured in ~/.crow/config.yaml")

        provider = next(iter(config.llm.providers.values()))
        llm = configure_llm(provider=provider, debug=False)

        return llm, config
    except Exception as e:
        pytest.skip(f"Could not configure LLM: {e}")


def precise_char_count(messages: list[dict]) -> int:
    """Count exact characters in messages."""
    total = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, str):
                    total += len(block)
                elif isinstance(block, dict):
                    if block.get("type") == "text":
                        total += len(block.get("text", ""))
                    elif block.get("type") == "image_url":
                        url = block.get("image_url", {})
                        if isinstance(url, dict):
                            total += len(url.get("url", ""))

        reasoning = msg.get("reasoning_content")
        if reasoning:
            total += len(reasoning)

    return total


class TestLiveLLMPersistence:
    """
    Test persistence with a live LLM.

    These tests verify that when an actual LLM responds, the
    data persists correctly without token loss.
    """

    @pytest.mark.asyncio
    async def test_live_llm_simple_question(
        self, temp_db_uri, sample_prompt_template, tmp_path
    ):
        """
        Send a simple question to live LLM and verify persistence.

        This is the minimal test case - one user message, one assistant response.
        """
        # Setup
        llm, config = get_live_llm_client()
        logger = logging.getLogger("test_logger")
        logger.setLevel(logging.INFO)

        prompt_id = lookup_or_create_prompt(sample_prompt_template, "test", temp_db_uri)
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Test", "workspace": "/tmp", "display_tree": ""},
            tool_definitions=[],
            request_params={"temperature": 0.7, "max_tokens": 200},
            model_identifier=config.llm.models["default"].model_id
            if "default" in config.llm.models
            else "test-model",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        # Add user message
        user_msg = "What is 2 + 2?"
        session.add_message({"role": "user", "content": user_msg})

        in_memory_before = len(session.messages)
        chars_before = precise_char_count(session.messages)

        # Call LLM
        response = await llm.chat.completions.create(
            model=session.model_identifier,
            messages=session.messages,
            stream=False,
            max_tokens=200,
        )

        # Add assistant response
        assistant_content = response.choices[0].message.content
        session.add_assistant_response(
            thinking=[],
            content=[assistant_content],
            tool_call_inputs=[],
            logger=logger,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
        )

        in_memory_after = len(session.messages)
        chars_after = precise_char_count(session.messages)

        # Verify in-memory state
        assert in_memory_after == in_memory_before + 1, (
            "Assistant message not added to memory"
        )
        assert chars_after > chars_before, "No content added"

        # Reload from database
        loaded = Session.load(session.session_id, temp_db_uri)

        # Verify persisted state
        assert len(loaded.messages) == len(session.messages), (
            f"Message count mismatch: {len(loaded.messages)} vs {len(session.messages)}"
        )

        persisted_chars = precise_char_count(loaded.messages)
        assert persisted_chars == chars_after, (
            f"Character loss detected: {chars_after} (memory) vs {persisted_chars} (persisted)"
        )

        # Verify content
        assert loaded.messages[1]["content"] == user_msg
        assert loaded.messages[2]["content"] == assistant_content

        print(f"✅ Live LLM test passed:")
        print(f"   User: {user_msg}")
        print(f"   Assistant: {assistant_content[:100]}...")
        print(f"   Total chars: {chars_after:,}")
        print(f"   No token loss detected")

    @pytest.mark.asyncio
    async def test_live_llm_multi_turn(
        self, temp_db_uri, sample_prompt_template, tmp_path
    ):
        """
        Multi-turn conversation with live LLM.

        Verify that multiple turns don't accumulate token loss.
        """
        # Setup
        llm, config = get_live_llm_client()
        logger = logging.getLogger("test_logger")
        logger.setLevel(logging.INFO)

        prompt_id = lookup_or_create_prompt(sample_prompt_template, "test", temp_db_uri)
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Test", "workspace": "/tmp", "display_tree": ""},
            tool_definitions=[],
            request_params={"temperature": 0.7, "max_tokens": 200},
            model_identifier=config.llm.models["default"].model_id
            if "default" in config.llm.models
            else "test-model",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        num_turns = 5
        total_chars_in_memory = 0
        total_chars_persisted = 0

        for turn in range(num_turns):
            user_msg = f"Turn {turn + 1}: What is the square of {turn + 1}?"
            session.add_message({"role": "user", "content": user_msg})

            # Call LLM
            response = await llm.chat.completions.create(
                model=session.model_identifier,
                messages=session.messages,
                stream=False,
                max_tokens=200,
            )

            assistant_content = response.choices[0].message.content
            session.add_assistant_response(
                thinking=[],
                content=[assistant_content],
                tool_call_inputs=[],
                logger=logger,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
            )

        # Capture in-memory state
        total_chars_in_memory = precise_char_count(session.messages)

        # Reload and compare
        loaded = Session.load(session.session_id, temp_db_uri)
        total_chars_persisted = precise_char_count(loaded.messages)

        # Verify
        assert len(loaded.messages) == len(session.messages), (
            f"Message count mismatch after {num_turns} turns"
        )

        assert total_chars_persisted == total_chars_in_memory, (
            f"Token loss after {num_turns} turns: {total_chars_in_memory} vs {total_chars_persisted}"
        )

        print(f"✅ Multi-turn live LLM test passed:")
        print(f"   Turns: {num_turns}")
        print(f"   Total messages: {len(session.messages)}")
        print(f"   Total chars: {total_chars_in_memory:,}")
        print(f"   No token loss detected")

    @pytest.mark.asyncio
    async def test_live_llm_streaming_response(
        self, temp_db_uri, sample_prompt_template, tmp_path
    ):
        """
        Test streaming response from live LLM.

        This simulates the actual react loop behavior where responses are streamed.
        """
        # Setup
        llm, config = get_live_llm_client()
        logger = logging.getLogger("test_logger")
        logger.setLevel(logging.INFO)

        prompt_id = lookup_or_create_prompt(sample_prompt_template, "test", temp_db_uri)
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Test", "workspace": "/tmp", "display_tree": ""},
            tool_definitions=[],
            request_params={"temperature": 0.7, "max_tokens": 500},
            model_identifier=config.llm.models["default"].model_id
            if "default" in config.llm.models
            else "test-model",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        # Add user message
        user_msg = "Write a short paragraph about artificial intelligence."
        session.add_message({"role": "user", "content": user_msg})

        in_memory_chars = precise_char_count(session.messages)

        # Call LLM with streaming
        response = await llm.chat.completions.create(
            model=session.model_identifier,
            messages=session.messages,
            stream=True,
            max_tokens=500,
            stream_options={"include_usage": True},
        )

        # Stream the response
        content_parts = []
        final_usage = None

        async for chunk in response:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta.content:
                    content_parts.append(delta.content)

            # Get usage from final chunk
            if hasattr(chunk, "usage") and chunk.usage:
                final_usage = {
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                    "total_tokens": chunk.usage.total_tokens,
                }

        assistant_content = "".join(content_parts)

        # Add to session
        session.add_assistant_response(
            thinking=[],
            content=[assistant_content],
            tool_call_inputs=[],
            logger=logger,
            usage=final_usage,
        )

        in_memory_chars_after = precise_char_count(session.messages)

        # Reload and compare
        loaded = Session.load(session.session_id, temp_db_uri)
        persisted_chars = precise_char_count(loaded.messages)

        # Verify
        assert len(loaded.messages) == len(session.messages)
        assert persisted_chars == in_memory_chars_after, (
            f"Token loss in streaming response: {in_memory_chars_after} vs {persisted_chars}"
        )

        assert len(assistant_content) > 50, "Response too short"

        print(f"✅ Streaming live LLM test passed:")
        print(f"   Response length: {len(assistant_content)} chars")
        print(
            f"   Total tokens: {final_usage['total_tokens'] if final_usage else 'N/A'}"
        )
        print(f"   No token loss detected")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
