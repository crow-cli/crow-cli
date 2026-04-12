"""
Persistence Integrity Test Battery.

Critical tests to ensure 100% accuracy of persisted data used for session/prompt inputs.
Zero tolerance for token loss - if we're off by a single token, we must detect it.

This test battery focuses on:
1. In-memory vs persisted data consistency
2. Exact token counting at each step
3. Serialization/deserialization fidelity
4. Message order and completeness across react loop boundaries
5. Detecting token loss between in-memory state and database state
"""

import asyncio
import json
import logging
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SQLAlchemySession

from crow_cli.agent.db import Base, Message, Prompt, Session as SessionModel, create_database
from crow_cli.agent.logger import setup_logger
from crow_cli.agent.session import Session, lookup_or_create_prompt


def count_tokens_in_message(msg: dict) -> int:
    """
    Count tokens in a message by counting characters (approximation).

    For accurate testing, we use character count as a proxy for tokens.
    1 token ≈ 4 characters in most languages.

    This is NOT for actual API calls, just for detecting discrepancies.
    """
    total_chars = 0

    # Count content
    content = msg.get("content", "")
    if isinstance(content, str):
        total_chars += len(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                total_chars += len(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    total_chars += len(block.get("text", ""))
                elif block.get("type") == "image_url":
                    # Image data URLs are very long
                    image_url = block.get("image_url", {})
                    if isinstance(image_url, dict):
                        total_chars += len(image_url.get("url", ""))

    # Count reasoning_content (thinking)
    reasoning = msg.get("reasoning_content", "")
    if reasoning:
        total_chars += len(reasoning)

    # Count tool_calls
    tool_calls = msg.get("tool_calls", [])
    for call in tool_calls:
        if isinstance(call, dict):
            total_chars += len(call.get("id", ""))
            func = call.get("function", {})
            if isinstance(func, dict):
                total_chars += len(func.get("name", ""))
                total_chars += len(str(func.get("arguments", "")))

    # Count tool_call_id for tool responses
    if msg.get("role") == "tool":
        total_chars += len(msg.get("tool_call_id", ""))

    # Rough token approximation: 1 token ≈ 4 characters
    return total_chars // 4


def calculate_total_tokens(messages: list[dict]) -> int:
    """Calculate total tokens across all messages."""
    return sum(count_tokens_in_message(msg) for msg in messages)


def deep_compare_messages(
    in_memory: dict, persisted: dict, path: str = "root"
) -> list[str]:
    """
    Deep compare two message dicts and return list of differences.

    Args:
        in_memory: Message from in-memory session
        persisted: Message deserialized from database
        path: Current path in the object (for error messages)

    Returns:
        List of difference descriptions
    """
    differences = []

    # Check all keys in in_memory
    for key in in_memory:
        current_path = f"{path}.{key}" if path else key

        if key not in persisted:
            differences.append(f"Missing key in persisted: {current_path}")
            continue

        in_val = in_memory[key]
        pers_val = persisted[key]

        if isinstance(in_val, dict):
            differences.extend(deep_compare_messages(in_val, pers_val, current_path))
        elif isinstance(in_val, list):
            if not isinstance(pers_val, list):
                differences.append(
                    f"Type mismatch at {current_path}: list vs {type(pers_val).__name__}"
                )
            elif len(in_val) != len(pers_val):
                differences.append(
                    f"List length mismatch at {current_path}: {len(in_val)} vs {len(pers_val)}"
                )
            else:
                for i, (in_item, pers_item) in enumerate(zip(in_val, pers_val)):
                    item_path = f"{current_path}[{i}]"
                    if isinstance(in_item, dict):
                        differences.extend(
                            deep_compare_messages(in_item, pers_item, item_path)
                        )
                    elif in_item != pers_item:
                        differences.append(
                            f"Value mismatch at {item_path}: {repr(in_item)} vs {repr(pers_item)}"
                        )
        elif in_val != pers_val:
            differences.append(
                f"Value mismatch at {current_path}: {repr(in_val)} vs {repr(pers_val)}"
            )

    # Check for extra keys in persisted
    for key in persisted:
        if key not in in_memory:
            differences.append(f"Extra key in persisted: {path}.{key}")

    return differences


class TestMessageSerializationIntegrity:
    """Test that messages survive JSON serialization/deserialization without loss."""

    def test_simple_text_message_roundtrip(self, temp_db_uri, sample_prompt_template):
        """Simple text message should survive roundtrip perfectly."""
        prompt_id = lookup_or_create_prompt(sample_prompt_template, "test", temp_db_uri)
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Test", "workspace": "/tmp", "display_tree": ""},
            tool_definitions=[],
            request_params={},
            model_identifier="test",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        original_msg = {"role": "user", "content": "Hello, this is a test message!"}
        session.add_message(original_msg)

        # Reload and compare
        loaded = Session.load(session.session_id, temp_db_uri)
        loaded_msg = loaded.messages[1]  # First message after system

        assert loaded_msg == original_msg, (
            f"Message mismatch: {loaded_msg} != {original_msg}"
        )

    def test_multimodal_message_roundtrip(self, temp_db_uri, sample_prompt_template):
        """Multimodal message with images should survive roundtrip."""
        prompt_id = lookup_or_create_prompt(sample_prompt_template, "test", temp_db_uri)
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Test", "workspace": "/tmp", "display_tree": ""},
            tool_definitions=[],
            request_params={},
            model_identifier="test",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        # Create multimodal message
        original_msg = {
            "role": "user",
            "content": [
                {"type": "text", "text": "Here's an image:"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
                    },
                },
            ],
        }
        session.add_message(original_msg)

        # Reload and compare
        loaded = Session.load(session.session_id, temp_db_uri)
        loaded_msg = loaded.messages[1]

        assert loaded_msg == original_msg, (
            f"Multimodal message mismatch:\n{deep_compare_messages(original_msg, loaded_msg)}"
        )

    def test_tool_call_message_roundtrip(self, temp_db_uri, sample_prompt_template):
        """Message with tool_calls should survive roundtrip."""
        prompt_id = lookup_or_create_prompt(sample_prompt_template, "test", temp_db_uri)
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Test", "workspace": "/tmp", "display_tree": ""},
            tool_definitions=[],
            request_params={},
            model_identifier="test",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        original_msg = {
            "role": "assistant",
            "content": "Let me check that for you.",
            "tool_calls": [
                {
                    "id": "call_abc123",
                    "type": "function",
                    "function": {
                        "name": "terminal",
                        "arguments": '{"command": "ls", "path": "/tmp"}',
                    },
                }
            ],
        }
        session.add_message(original_msg)

        # Reload and compare
        loaded = Session.load(session.session_id, temp_db_uri)
        loaded_msg = loaded.messages[1]

        assert loaded_msg == original_msg, (
            f"Tool call message mismatch:\n{deep_compare_messages(original_msg, loaded_msg)}"
        )

    def test_thinking_content_roundtrip(self, temp_db_uri, sample_prompt_template):
        """Message with reasoning_content (thinking) should survive roundtrip."""
        prompt_id = lookup_or_create_prompt(sample_prompt_template, "test", temp_db_uri)
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Test", "workspace": "/tmp", "display_tree": ""},
            tool_definitions=[],
            request_params={},
            model_identifier="test",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        original_msg = {
            "role": "assistant",
            "content": "The answer is 42.",
            "reasoning_content": "Let me think about this step by step. First, I need to consider the problem...",
        }
        session.add_message(original_msg)

        # Reload and compare
        loaded = Session.load(session.session_id, temp_db_uri)
        loaded_msg = loaded.messages[1]

        assert loaded_msg == original_msg, (
            f"Thinking content mismatch:\n{deep_compare_messages(original_msg, loaded_msg)}"
        )

    def test_complex_nested_message_roundtrip(
        self, temp_db_uri, sample_prompt_template
    ):
        """Complex message with nested structures should survive roundtrip."""
        prompt_id = lookup_or_create_prompt(sample_prompt_template, "test", temp_db_uri)
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Test", "workspace": "/tmp", "display_tree": ""},
            tool_definitions=[],
            request_params={},
            model_identifier="test",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        original_msg = {
            "role": "assistant",
            "content": "Here's a complex response",
            "reasoning_content": "Thinking process...",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "edit",
                        "arguments": json.dumps(
                            {
                                "file_path": "/tmp/test.py",
                                "old_string": "old",
                                "new_string": "new",
                                "nested": {"key": "value", "list": [1, 2, 3]},
                            }
                        ),
                    },
                },
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {
                        "name": "terminal",
                        "arguments": json.dumps({"command": "echo", "args": ["hello"]}),
                    },
                },
            ],
        }
        session.add_message(original_msg)

        # Reload and compare
        loaded = Session.load(session.session_id, temp_db_uri)
        loaded_msg = loaded.messages[1]

        assert loaded_msg == original_msg, (
            f"Complex nested message mismatch:\n{deep_compare_messages(original_msg, loaded_msg)}"
        )


class TestInMemoryVsPersistedConsistency:
    """Test that in-memory state matches persisted state at all times."""

    @pytest.mark.asyncio
    async def test_message_immediate_persistence(
        self, temp_db_uri, sample_prompt_template
    ):
        """Message added to session should be immediately persisted to database."""
        prompt_id = lookup_or_create_prompt(sample_prompt_template, "test", temp_db_uri)
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Test", "workspace": "/tmp", "display_tree": ""},
            tool_definitions=[],
            request_params={},
            model_identifier="test",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        original_msg = {"role": "user", "content": "Test message"}

        # Add message
        session.add_message(original_msg)

        # Immediately query database directly (bypass session.load)
        engine = create_engine(temp_db_uri)
        db_session = SQLAlchemySession(engine)
        try:
            db_msg = (
                db_session.query(Message)
                .filter_by(session_id=session.session_id)
                .order_by(Message.id)
                .all()[-1]
            )
            persisted_msg = db_msg.data

            assert persisted_msg == original_msg, (
                f"Immediate persistence failed: {persisted_msg} != {original_msg}"
            )
        finally:
            db_session.close()

    def test_full_history_consistency(self, temp_db_uri, sample_prompt_template):
        """Full message history should be consistent between memory and database."""
        prompt_id = lookup_or_create_prompt(sample_prompt_template, "test", temp_db_uri)
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Test", "workspace": "/tmp", "display_tree": ""},
            tool_definitions=[],
            request_params={},
            model_identifier="test",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        # Add many messages
        test_messages = [
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Response 1"},
            {
                "role": "user",
                "content": "Message 2 with longer content to test token counting",
            },
            {
                "role": "assistant",
                "content": "Response 2",
                "reasoning_content": "Thinking...",
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "Tool output"},
        ]

        for msg in test_messages:
            session.add_message(msg)

        # Compare in-memory vs database
        engine = create_engine(temp_db_uri)
        db_session = SQLAlchemySession(engine)
        try:
            db_messages = (
                db_session.query(Message)
                .filter_by(session_id=session.session_id)
                .order_by(Message.id)
                .all()
            )

            assert len(session.messages) == len(db_messages), (
                f"Message count mismatch: {len(session.messages)} vs {len(db_messages)}"
            )

            for i, (mem_msg, db_msg) in enumerate(zip(session.messages, db_messages)):
                differences = deep_compare_messages(
                    mem_msg, db_msg.data, f"message[{i}]"
                )
                assert not differences, f"Differences at message {i}:\n" + "\n".join(
                    differences
                )
        finally:
            db_session.close()

    def test_token_count_consistency(self, temp_db_uri, sample_prompt_template):
        """Token counts should be consistent between in-memory and persisted messages."""
        prompt_id = lookup_or_create_prompt(sample_prompt_template, "test", temp_db_uri)
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Test", "workspace": "/tmp", "display_tree": ""},
            tool_definitions=[],
            request_params={},
            model_identifier="test",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        # Add messages with varying content sizes
        test_messages = [
            {"role": "user", "content": "x" * 100},
            {"role": "assistant", "content": "y" * 500},
            {"role": "user", "content": "z" * 1000},
            {
                "role": "assistant",
                "content": "a" * 2000,
                "reasoning_content": "b" * 1500,
            },
        ]

        for msg in test_messages:
            session.add_message(msg)

        # Calculate tokens in-memory
        in_memory_tokens = calculate_total_tokens(session.messages)

        # Calculate tokens from database
        engine = create_engine(temp_db_uri)
        db_session = SQLAlchemySession(engine)
        try:
            db_messages = (
                db_session.query(Message)
                .filter_by(session_id=session.session_id)
                .order_by(Message.id)
                .all()
            )
            persisted_tokens = calculate_total_tokens(
                [db_msg.data for db_msg in db_messages]
            )

            assert in_memory_tokens == persisted_tokens, (
                f"Token count mismatch: {in_memory_tokens} (memory) vs {persisted_tokens} (persisted)"
            )
            assert in_memory_tokens > 0, "Token count should be positive"
        finally:
            db_session.close()


class TestReactLoopBoundaryIntegrity:
    """Test data integrity across react loop boundaries (in-memory → persisted → reloaded)."""

    def test_session_state_after_add_assistant_response(
        self, temp_db_uri, sample_prompt_template
    ):
        """Session state after add_assistant_response should be fully persistent."""
        prompt_id = lookup_or_create_prompt(sample_prompt_template, "test", temp_db_uri)
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Test", "workspace": "/tmp", "display_tree": ""},
            tool_definitions=[],
            request_params={},
            model_identifier="test",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        # Create a mock logger
        logger = logging.getLogger("test_logger")
        logger.setLevel(logging.INFO)

        # Simulate react loop response
        thinking = ["Let", " me", " think", " about", " this"]
        content = ["The", " answer", " is", " 42"]
        tool_calls = [
            {
                "id": "call_xyz",
                "function_name": "terminal",
                "arguments": ['{"command":', '"ls"}'],
            }
        ]

        session.add_assistant_response(
            thinking=thinking,
            content=content,
            tool_call_inputs=[
                {
                    "id": "call_xyz",
                    "type": "function",
                    "function": {"name": "terminal", "arguments": '{"command": "ls"}'},
                }
            ],
            logger=logger,
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        )

        # Reload and verify
        loaded = Session.load(session.session_id, temp_db_uri)

        # Check message count
        assert len(loaded.messages) == 2, (
            f"Expected 2 messages, got {len(loaded.messages)}"
        )

        # Check assistant message content
        assistant_msg = loaded.messages[1]
        assert assistant_msg["role"] == "assistant"
        assert assistant_msg["content"] == "".join(content)
        assert assistant_msg["reasoning_content"] == "".join(thinking)
        assert "tool_calls" in assistant_msg

    def test_session_state_after_tool_response(
        self, temp_db_uri, sample_prompt_template
    ):
        """Session state after tool response should be fully persistent."""
        prompt_id = lookup_or_create_prompt(sample_prompt_template, "test", temp_db_uri)
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Test", "workspace": "/tmp", "display_tree": ""},
            tool_definitions=[],
            request_params={},
            model_identifier="test",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        # Create a mock logger
        logger = logging.getLogger("test_logger")
        logger.setLevel(logging.INFO)

        # Add assistant message with tool call
        session.add_assistant_response(
            thinking=[],
            content=["Running command"],
            tool_call_inputs=[
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "terminal", "arguments": '{"command": "ls"}'},
                }
            ],
            logger=logger,
        )

        # Add tool response
        tool_result = {
            "role": "tool",
            "tool_call_id": "call_123",
            "content": "file1.txt\nfile2.txt",
        }
        session.add_tool_response([tool_result], logger=logger)

        # Reload and verify
        loaded = Session.load(session.session_id, temp_db_uri)

        # Should have: system, assistant, tool
        assert len(loaded.messages) == 3, (
            f"Expected 3 messages, got {len(loaded.messages)}"
        )

        # Verify tool response
        tool_msg = loaded.messages[2]
        assert tool_msg["role"] == "tool"
        assert tool_msg["tool_call_id"] == "call_123"
        assert tool_msg["content"] == "file1.txt\nfile2.txt"

    def test_long_conversation_integrity(self, temp_db_uri, sample_prompt_template):
        """Long conversation (simulating 85k tokens) should maintain integrity."""
        prompt_id = lookup_or_create_prompt(sample_prompt_template, "test", temp_db_uri)
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Test", "workspace": "/tmp", "display_tree": ""},
            tool_definitions=[],
            request_params={},
            model_identifier="test",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        # Simulate long conversation with many turns
        num_turns = 100
        for i in range(num_turns):
            # User message
            user_content = (
                f"User message {i} with some content to make it longer. " * 10
            )
            session.add_message({"role": "user", "content": user_content})

            # Assistant response
            assistant_content = (
                f"Assistant response {i} with detailed information. " * 10
            )
            session.add_message(
                {
                    "role": "assistant",
                    "content": assistant_content,
                    "reasoning_content": f"Thinking about message {i}...",
                }
            )

            # Occasionally add tool calls
            if i % 5 == 0:
                session.add_message(
                    {
                        "role": "assistant",
                        "content": f"Using tool in turn {i}",
                        "tool_calls": [
                            {
                                "id": f"call_{i}",
                                "type": "function",
                                "function": {
                                    "name": "terminal",
                                    "arguments": f'{{"command": "echo {i}"}}',
                                },
                            }
                        ],
                    }
                )
                session.add_message(
                    {
                        "role": "tool",
                        "tool_call_id": f"call_{i}",
                        "content": f"Output {i}" * 20,
                    }
                )

        # Calculate in-memory tokens
        in_memory_tokens = calculate_total_tokens(session.messages)

        # Reload and compare
        loaded = Session.load(session.session_id, temp_db_uri)
        persisted_tokens = calculate_total_tokens(loaded.messages)

        # Verify
        assert len(loaded.messages) == len(session.messages), (
            f"Message count mismatch: {len(loaded.messages)} vs {len(session.messages)}"
        )

        assert in_memory_tokens == persisted_tokens, (
            f"Token count mismatch in long conversation: {in_memory_tokens} vs {persisted_tokens}"
        )

        # Deep compare all messages
        for i, (mem_msg, loaded_msg) in enumerate(
            zip(session.messages, loaded.messages)
        ):
            differences = deep_compare_messages(mem_msg, loaded_msg, f"message[{i}]")
            assert not differences, (
                f"Differences at message {i} in long conversation:\n"
                + "\n".join(differences[:5])
            )


class TestUsageTrackingIntegrity:
    """Test that usage/token tracking is accurate and consistent."""

    def test_usage_persistence(self, temp_db_uri, sample_prompt_template):
        """Usage data should be persisted with messages."""
        prompt_id = lookup_or_create_prompt(sample_prompt_template, "test", temp_db_uri)
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Test", "workspace": "/tmp", "display_tree": ""},
            tool_definitions=[],
            request_params={},
            model_identifier="test",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        usage = {"prompt_tokens": 1234, "completion_tokens": 567, "total_tokens": 1801}
        session.add_message({"role": "user", "content": "Test"}, usage=usage)

        # Verify usage in database
        engine = create_engine(temp_db_uri)
        db_session = SQLAlchemySession(engine)
        try:
            db_msg = (
                db_session.query(Message)
                .filter_by(session_id=session.session_id)
                .order_by(Message.id)
                .all()[-1]
            )

            assert db_msg.prompt_tokens == 1234
            assert db_msg.completion_tokens == 567
            assert db_msg.total_tokens == 1801
        finally:
            db_session.close()

    def test_usage_sum_across_messages(self, temp_db_uri, sample_prompt_template):
        """Sum of usage across messages should be accurate."""
        prompt_id = lookup_or_create_prompt(sample_prompt_template, "test", temp_db_uri)
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Test", "workspace": "/tmp", "display_tree": ""},
            tool_definitions=[],
            request_params={},
            model_identifier="test",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        # Add messages with usage
        usages = [
            {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            {"prompt_tokens": 200, "completion_tokens": 75, "total_tokens": 275},
            {"prompt_tokens": 300, "completion_tokens": 100, "total_tokens": 400},
        ]

        for i, usage in enumerate(usages):
            session.add_message(
                {
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"Message {i}",
                },
                usage,
            )

        # Calculate expected totals
        expected_prompt = sum(u["prompt_tokens"] for u in usages)
        expected_completion = sum(u["completion_tokens"] for u in usages)
        expected_total = sum(u["total_tokens"] for u in usages)

        # Verify from database
        engine = create_engine(temp_db_uri)
        db_session = SQLAlchemySession(engine)
        try:
            db_messages = (
                db_session.query(Message)
                .filter_by(session_id=session.session_id)
                .order_by(Message.id)
                .all()
            )

            actual_prompt = sum(m.prompt_tokens or 0 for m in db_messages)
            actual_completion = sum(m.completion_tokens or 0 for m in db_messages)
            actual_total = sum(m.total_tokens or 0 for m in db_messages)

            assert actual_prompt == expected_prompt, (
                f"Prompt tokens mismatch: {actual_prompt} vs {expected_prompt}"
            )
            assert actual_completion == expected_completion, (
                f"Completion tokens mismatch: {actual_completion} vs {expected_completion}"
            )
            assert actual_total == expected_total, (
                f"Total tokens mismatch: {actual_total} vs {expected_total}"
            )
        finally:
            db_session.close()


class TestEdgeCases:
    """Test edge cases that could cause token loss."""

    def test_empty_content_handling(self, temp_db_uri, sample_prompt_template):
        """Empty content should be handled consistently."""
        prompt_id = lookup_or_create_prompt(sample_prompt_template, "test", temp_db_uri)
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Test", "workspace": "/tmp", "display_tree": ""},
            tool_definitions=[],
            request_params={},
            model_identifier="test",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        # Add message with empty content
        session.add_message({"role": "user", "content": ""})

        # Reload and verify
        loaded = Session.load(session.session_id, temp_db_uri)
        assert loaded.messages[1]["content"] == ""

    def test_unicode_content_handling(self, temp_db_uri, sample_prompt_template):
        """Unicode content should survive roundtrip."""
        prompt_id = lookup_or_create_prompt(sample_prompt_template, "test", temp_db_uri)
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Test", "workspace": "/tmp", "display_tree": ""},
            tool_definitions=[],
            request_params={},
            model_identifier="test",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        unicode_msg = {"role": "user", "content": "Hello 世界 🌍 مرحبا שלום"}
        session.add_message(unicode_msg)

        # Reload and verify
        loaded = Session.load(session.session_id, temp_db_uri)
        assert loaded.messages[1] == unicode_msg

    def test_very_long_single_message(self, temp_db_uri, sample_prompt_template):
        """Very long single message should survive roundtrip."""
        prompt_id = lookup_or_create_prompt(sample_prompt_template, "test", temp_db_uri)
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Test", "workspace": "/tmp", "display_tree": ""},
            tool_definitions=[],
            request_params={},
            model_identifier="test",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        # Create message with ~10k characters
        long_content = "x" * 10000
        long_msg = {"role": "user", "content": long_content}
        session.add_message(long_msg)

        # Reload and verify
        loaded = Session.load(session.session_id, temp_db_uri)
        assert loaded.messages[1]["content"] == long_content
        assert len(loaded.messages[1]["content"]) == 10000

    def test_special_characters_in_tool_arguments(
        self, temp_db_uri, sample_prompt_template
    ):
        """Special characters in tool arguments should be preserved."""
        prompt_id = lookup_or_create_prompt(sample_prompt_template, "test", temp_db_uri)
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Test", "workspace": "/tmp", "display_tree": ""},
            tool_definitions=[],
            request_params={},
            model_identifier="test",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        # Tool arguments with special characters
        tool_msg = {
            "role": "assistant",
            "content": "Running command",
            "tool_calls": [
                {
                    "id": "call_special",
                    "type": "function",
                    "function": {
                        "name": "edit",
                        "arguments": '{"old_string": "if x == 0: \\n    print(\\"hello\\")", "new_string": "if x > 0: \\n    print(\\"world\\")"}',
                    },
                }
            ],
        }
        session.add_message(tool_msg)

        # Reload and verify
        loaded = Session.load(session.session_id, temp_db_uri)
        loaded_msg = loaded.messages[1]

        assert loaded_msg == tool_msg, (
            f"Special characters not preserved:\n{deep_compare_messages(tool_msg, loaded_msg)}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
