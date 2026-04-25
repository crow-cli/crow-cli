"""
Test that reproduces the token loss between turns.

Runs multiple turns through the actual crow-cli code and compares
the payloads sent to the API on each turn.
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest

from crow_cli.agent.configure import Config
from crow_cli.agent.llm import configure_llm
from crow_cli.agent.prompt import normalize_blocks
from crow_cli.agent.react import send_request
from crow_cli.agent.session import Session


def normalize_messages_for_api(messages: list[dict]) -> list[dict]:
    """Exactly replicates send_request normalization logic."""
    normalized_messages = []
    for msg in messages:
        normalized_msg = dict(msg)
        content = msg.get("content")
        if isinstance(content, list):
            normalized_msg["content"] = normalize_blocks(content)
        normalized_messages.append(normalized_msg)
    return normalized_messages


def dump_payload(session_id: str, turn: int, normalized_messages: list[dict]) -> str:
    """Dump payload to ~/.crow/logs/ like send_request does."""
    import hashlib

    payload_hash = hashlib.sha256(
        json.dumps(normalized_messages, sort_keys=True).encode()
    ).hexdigest()[:12]
    log_dir = os.path.expanduser("~/.crow/logs")
    os.makedirs(log_dir, exist_ok=True)
    payload_path = os.path.join(
        log_dir, f"payload-turn{turn}-{session_id}-{payload_hash}.json"
    )
    with open(payload_path, "w") as f:
        json.dump(normalized_messages, f)
    return payload_path


def count_chars(messages: list[dict]) -> int:
    """Count total characters in message content."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            total += sum(
                len(b.get("text", "")) if isinstance(b, dict) else len(str(b))
                for b in content
            )
        else:
            total += len(str(content))
    return total


class TestTokenLossReproduction:
    """Run actual turns through crow-cli code and check for token loss."""

    def _create_test_session(self, config: Config, cwd: str = "/tmp") -> Session:
        """Create a fresh test session with minimal setup."""
        from crow_cli.agent.db import Session as SessionModel
        from crow_cli.agent.session import get_coolname

        session_id = get_coolname()
        system_prompt = "You are a test assistant. Be brief."

        # Create the session model directly
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session as SQLAlchemySession

        db = SQLAlchemySession(create_engine(config.db_uri))
        db.add(
            SessionModel(
                session_id=session_id,
                system_prompt=system_prompt,
                tool_definitions=[],
                request_params={"temperature": 0.2},
                model_identifier="qwen3.5-plus",
            )
        )
        db.commit()
        db.close()

        session = Session(session_id, db_uri=config.db_uri, cwd=cwd)
        session.messages = [{"role": "system", "content": system_prompt}]
        session.model_identifier = "qwen3.5-plus"
        session.tools = []
        session.request_params = {"temperature": 0.2}

        return session

    async def _run_turn(
        self, session: Session, llm, user_text: str, turn: int
    ) -> list[dict]:
        """Run a single turn: add user message, call send_request, dump payload."""
        # Add user message
        session.add_message({"role": "user", "content": user_text})

        # Normalize exactly as send_request does
        normalized = normalize_messages_for_api(session.messages)

        # Dump payload BEFORE sending
        payload_path = dump_payload(session.session_id, turn, normalized)
        chars = count_chars(normalized)

        # Send the request
        response = await send_request(
            llm=llm,
            session=session,
            tools=[],
            max_tokens=50,
        )

        # Consume the stream to get the result
        thinking, content, tool_calls = [], [], {}
        async for chunk in response:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta.content:
                    content.append(delta.content)
                if delta.tool_calls:
                    for call in delta.tool_calls:
                        if call.function and call.function.name:
                            tool_calls[call.index] = call
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    thinking.append(delta.reasoning_content)

        content_text = "".join(content)

        # Add assistant response
        msg = {"role": "assistant", "content": content_text}
        if thinking:
            msg["reasoning_content"] = "".join(thinking)
        if tool_calls:
            # Build tool_calls format for storage
            pass  # No tools in this test

        session.add_message(msg)

        print(f"\n=== Turn {turn} ===")
        print(f"Payload: {os.path.basename(payload_path)}")
        print(f"Messages: {len(session.messages)}")
        print(f"Content chars: {chars}")

        return normalized

    @pytest.mark.asyncio
    async def test_multi_turn_no_token_loss(self):
        """Run 5 turns and verify no content is lost between any of them."""
        config = Config.load()
        provider = config.llm.providers["litellm"]
        if not provider.base_url:
            pytest.skip("No litellm provider configured")

        from openai import AsyncOpenAI

        llm = AsyncOpenAI(api_key=provider.api_key, base_url=provider.base_url)

        session = self._create_test_session(config)

        prev_normalized = None
        prev_chars = None

        user_prompts = [
            "What is 2+2?",
            "What about 3+3?",
            "Now multiply 4*5",
            "Divide 100 by 7",
            "Square root of 144?",
        ]

        for turn, prompt in enumerate(user_prompts, 1):
            normalized = await self._run_turn(session, llm, prompt, turn)
            chars = count_chars(normalized)

            if prev_normalized is not None:
                # Verify message count is correct (should increase by 2 each turn: user + assistant)
                expected_count = 1 + (turn * 2)  # system + (user+assistant) * turns
                assert len(normalized) == expected_count, (
                    f"Turn {turn}: expected {expected_count} messages, got {len(normalized)}"
                )

                # Verify content didn't shrink
                assert chars >= prev_chars, (
                    f"Turn {turn}: content SHRUNK from {prev_chars} to {chars} chars! "
                    f"Lost {prev_chars - chars} chars"
                )

            prev_normalized = normalized
            prev_chars = chars

        print(f"\n=== Final Summary ===")
        print(f"Total turns: {len(user_prompts)}")
        print(f"Final messages: {len(session.messages)}")
        print(f"Final chars: {prev_chars}")

    @pytest.mark.asyncio
    async def test_multi_turn_with_tool_call_messages(self):
        """Run turns with fake tool call messages to test that path."""
        config = Config.load()
        provider = config.llm.providers["litellm"]
        if not provider.base_url:
            pytest.skip("No litellm provider configured")

        from openai import AsyncOpenAI

        llm = AsyncOpenAI(api_key=provider.api_key, base_url=provider.base_url)

        session = self._create_test_session(config)

        # Turn 1: normal prompt
        await self._run_turn(session, llm, "Read the file /tmp/test.txt", 1)

        # Simulate a tool call response (what the agent does after getting tool_calls from LLM)
        tool_call_msg = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_abc123",
                    "type": "function",
                    "function": {
                        "name": "read",
                        "arguments": '{"path": "/tmp/test.txt"}',
                    },
                }
            ],
        }
        session.add_message(tool_call_msg)

        tool_result_msg = {
            "role": "tool",
            "tool_call_id": "call_abc123",
            "content": "File contents here...",
        }
        session.add_message(tool_result_msg)

        # Turn 2: should include the tool call history
        prev_normalized = normalize_messages_for_api(session.messages)
        prev_chars = count_chars(prev_normalized)
        await self._run_turn(session, llm, "What does that file say?", 2)

        normalized = normalize_messages_for_api(session.messages)
        chars = count_chars(normalized)

        assert chars >= prev_chars, (
            f"Content shrunk after tool call turn: {prev_chars} -> {chars}"
        )
