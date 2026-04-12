"""
Token Loss Detection Tests.

These tests specifically target the bug you reported:
- 300 token loss out of 85k tokens after a long react loop
- Full reprocessing on backend when sending message from client to session/prompt
- In-memory works flawlessly, but persisted data loses tokens

This test suite simulates the exact scenario and detects even single-token discrepancies.
"""

import asyncio
import json
import logging
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SQLAlchemySession

from crow_cli.agent.db import Message
from crow_cli.agent.db import Session as SessionModel
from crow_cli.agent.logger import setup_logger
from crow_cli.agent.session import Session, lookup_or_create_prompt


def precise_char_count(messages: list[dict]) -> int:
    """
    Count exact characters in messages (more precise than token counting).

    This is the "microscope" - we count every single character to detect
    even the smallest data loss.
    """
    total = 0

    for msg in messages:
        # System and user messages
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

        # Reasoning content (thinking)
        reasoning = msg.get("reasoning_content")
        if reasoning:
            total += len(reasoning)

        # Tool calls
        tool_calls = msg.get("tool_calls", [])
        for call in tool_calls:
            if isinstance(call, dict):
                total += len(call.get("id", ""))
                func = call.get("function", {})
                if isinstance(func, dict):
                    total += len(func.get("name", ""))
                    args = func.get("arguments", "")
                    total += len(str(args))

        # Tool responses
        if msg.get("role") == "tool":
            total += len(msg.get("tool_call_id", ""))
            total += len(msg.get("content", ""))

    return total


class TestLongReactLoopTokenLoss:
    """
    Simulate the exact bug scenario: long react loop with potential token loss.
    """

    @pytest.mark.asyncio
    async def test_simulate_85k_token_conversation(
        self, temp_db_uri, sample_prompt_template, tmp_path
    ):
        """
        Simulate an 85k token conversation and verify NO token loss occurs.

        This is the exact scenario you reported:
        - Long react loop (many turns)
        - ~85k tokens total
        - Potential 300 token loss
        """
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

        logger = logging.getLogger("test_logger")
        logger.setLevel(logging.INFO)

        # Simulate a very long conversation (~85k tokens)
        # Using ~340k characters (85k * 4 chars/token)
        target_chars = 340000
        current_chars = len(session.messages[0]["content"])  # Start with system prompt
        turn = 0

        while current_chars < target_chars:
            turn += 1

            # Create user message with substantial content
            user_content = (
                f"""User query {turn}: Analyze this complex problem and provide a detailed response.

Context: We're working on a sophisticated software engineering task that requires
deep analysis and multiple iterations. This message is part of a long conversation
history that's accumulating tokens rapidly.

Specific request: Please provide a comprehensive answer that covers multiple aspects
of the problem, including edge cases, performance considerations, and best practices.
This needs to be thorough and well-structured.

Additional context for turn {turn}:
- We need to consider the implications of this approach
- There are multiple stakeholders involved
- The solution must be scalable and maintainable
- We should document all assumptions and decisions

"""
                * 10
            )

            session.add_message({"role": "user", "content": user_content})
            current_chars += len(user_content)

            # Create assistant response with thinking and tool calls
            thinking_content = f"""Let me think through this systematically. First, I need to understand the core requirements
and constraints of this problem. The user is asking for a comprehensive analysis that
covers multiple dimensions.

Key considerations:
1. The technical implementation details
2. The architectural implications
3. Performance and scalability concerns
4. Maintenance and documentation requirements

I should structure my response to address each of these areas thoroughly while
maintaining clarity and precision. The solution needs to be both correct and
practical for real-world deployment.

For turn {turn}, I need to ensure I'm building on the previous context while
adding new insights and analysis. This is part of an ongoing conversation that
requires maintaining coherence across many turns.

"""

            content = (
                f"""Based on my analysis, here's a comprehensive response to your query:

## Executive Summary

The problem you've described requires a multi-faceted approach that balances
technical excellence with practical considerations. Let me break this down
into key areas.

## Technical Analysis

### Core Requirements
{user_content[:200]}...

### Implementation Strategy
The implementation should follow established patterns while adapting to the
specific constraints of your environment. This includes:

1. Modular architecture for maintainability
2. Clear separation of concerns
3. Comprehensive error handling
4. Thorough testing coverage

### Performance Considerations
Performance is critical, especially given the scale you're operating at.
Key optimization strategies include:

- Efficient data structures and algorithms
- Caching where appropriate
- Parallel processing for independent operations
- Monitoring and profiling to identify bottlenecks

## Recommendations

Based on this analysis, I recommend the following approach:

1. Start with a solid foundation
2. Iterate based on feedback
3. Monitor and measure continuously
4. Document decisions and rationale

## Next Steps

Would you like me to dive deeper into any specific aspect? I can also
help with implementation details or provide code examples.

"""
                * 5
            )

            session.add_assistant_response(
                thinking=thinking_content.split(),
                content=content.split(),
                tool_call_inputs=[],
                logger=logger,
                usage={
                    "prompt_tokens": len(user_content) // 4,
                    "completion_tokens": len(content) // 4,
                    "total_tokens": (len(user_content) + len(content)) // 4,
                },
            )

            # Periodically add tool calls
            if turn % 3 == 0:
                tool_args = json.dumps(
                    {
                        "command": "analyze",
                        "parameters": {"depth": turn, "scope": "comprehensive"},
                        "metadata": {
                            "turn": turn,
                            "timestamp": f"2024-01-01T00:00:{turn:02d}",
                        },
                    }
                )

                session.add_assistant_response(
                    thinking=[],
                    content=[f"Using analysis tool for turn {turn}"],
                    tool_call_inputs=[
                        {
                            "id": f"call_turn_{turn}",
                            "type": "function",
                            "function": {"name": "terminal", "arguments": tool_args},
                        }
                    ],
                    logger=logger,
                )

                session.add_tool_response(
                    [
                        {
                            "role": "tool",
                            "tool_call_id": f"call_turn_{turn}",
                            "content": f"Analysis complete for turn {turn}. Results: "
                            + "x" * 500,
                        }
                    ],
                    logger=logger,
                )

        # CRITICAL: Capture in-memory state BEFORE any database operations
        in_memory_chars = precise_char_count(session.messages)
        in_memory_msg_count = len(session.messages)

        # Now simulate what happens when client sends a new message
        # This is where you observed the token loss

        # First, reload the session from database (simulating client -> server boundary)
        reloaded_session = Session.load(session.session_id, temp_db_uri)

        # Capture persisted state
        persisted_chars = precise_char_count(reloaded_session.messages)
        persisted_msg_count = len(reloaded_session.messages)

        # CRITICAL ASSERTIONS - Detect even single character loss
        assert in_memory_msg_count == persisted_msg_count, (
            f"MESSAGE COUNT MISMATCH: {in_memory_msg_count} (memory) vs {persisted_msg_count} (persisted)\n"
            f"This indicates messages were lost during persistence!"
        )

        # Allow for tiny rounding differences, but NOT 300 tokens (~1200 chars)
        char_difference = abs(in_memory_chars - persisted_chars)
        tolerance = 100  # Very generous tolerance - should be 0 in practice

        assert char_difference < tolerance, (
            f"TOKEN LOSS DETECTED!\n"
            f"In-memory characters: {in_memory_chars:,}\n"
            f"Persisted characters: {persisted_chars:,}\n"
            f"Difference: {char_difference:,} characters (~{char_difference // 4} tokens)\n"
            f"\nThis is the bug you reported - data loss during persistence!"
        )

        # Deep comparison of all messages
        for i, (mem_msg, pers_msg) in enumerate(
            zip(session.messages, reloaded_session.messages)
        ):
            if mem_msg != pers_msg:
                # Find exactly where they differ
                mem_chars = precise_char_count([mem_msg])
                pers_chars = precise_char_count([pers_msg])

                assert False, (
                    f"Message {i} differs between memory and persistence:\n"
                    f"  Memory chars: {mem_chars}\n"
                    f"  Persisted chars: {pers_chars}\n"
                    f"  Difference: {abs(mem_chars - pers_chars)}\n"
                    f"\nFull message comparison failed at message index {i}"
                )

    @pytest.mark.asyncio
    async def test_rapid_message_accumulation(
        self, temp_db_uri, sample_prompt_template
    ):
        """
        Test rapid message accumulation to catch buffering/persistence issues.
        """
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

        logger = logging.getLogger("test_logger")
        logger.setLevel(logging.INFO)

        # Rapidly add many messages
        num_messages = 500
        for i in range(num_messages):
            msg_content = f"Message {i}: " + "x" * 100
            session.add_message(
                {"role": "user" if i % 2 == 0 else "assistant", "content": msg_content}
            )

        # Check in-memory
        in_memory_count = len(session.messages)
        in_memory_chars = precise_char_count(session.messages)

        # Reload from database
        reloaded = Session.load(session.session_id, temp_db_uri)

        # Verify
        assert len(reloaded.messages) == in_memory_count, (
            f"Message count mismatch: {len(reloaded.messages)} vs {in_memory_count}"
        )

        persisted_chars = precise_char_count(reloaded.messages)
        assert persisted_chars == in_memory_chars, (
            f"Character count mismatch after rapid accumulation: {persisted_chars} vs {in_memory_chars}"
        )

    @pytest.mark.asyncio
    async def test_tool_call_chain_integrity(self, temp_db_uri, sample_prompt_template):
        """
        Test integrity of long chains of tool calls and responses.
        """
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

        logger = logging.getLogger("test_logger")
        logger.setLevel(logging.INFO)

        # Simulate long chain of tool calls
        num_tools = 100
        for i in range(num_tools):
            # Assistant makes tool call
            tool_args = json.dumps(
                {
                    "iteration": i,
                    "data": "x" * 200,
                    "metadata": {"nested": {"key": f"value_{i}"}},
                }
            )

            session.add_assistant_response(
                thinking=[],
                content=[f"Calling tool {i}"],
                tool_call_inputs=[
                    {
                        "id": f"tool_{i}",
                        "type": "function",
                        "function": {"name": "terminal", "arguments": tool_args},
                    }
                ],
                logger=logger,
            )

            # Tool responds
            session.add_tool_response(
                [
                    {
                        "role": "tool",
                        "tool_call_id": f"tool_{i}",
                        "content": f"Tool {i} output: " + "y" * 300,
                    }
                ],
                logger=logger,
            )

        # Verify integrity
        in_memory_chars = precise_char_count(session.messages)

        reloaded = Session.load(session.session_id, temp_db_uri)
        persisted_chars = precise_char_count(reloaded.messages)

        assert len(reloaded.messages) == len(session.messages), (
            f"Tool chain message count mismatch: {len(reloaded.messages)} vs {len(session.messages)}"
        )

        assert persisted_chars == in_memory_chars, (
            f"Tool chain character loss: {in_memory_chars} -> {persisted_chars} (lost {in_memory_chars - persisted_chars})"
        )

    @pytest.mark.asyncio
    async def test_mixed_content_types_integrity(
        self, temp_db_uri, sample_prompt_template
    ):
        """
        Test integrity with mixed content types (text, images, tool calls, thinking).
        """
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

        logger = logging.getLogger("test_logger")
        logger.setLevel(logging.INFO)

        # Add mixed content types
        for i in range(50):
            # Text message
            session.add_message(
                {"role": "user", "content": f"Text message {i}: " + "a" * 100}
            )

            # Multimodal message
            session.add_message(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Image description {i}"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{'b' * 500}"},
                        },
                    ],
                }
            )

            # Assistant with thinking and tool calls
            session.add_assistant_response(
                thinking=[f"Thinking token {j}" for j in range(20)],
                content=[f"Response token {j}" for j in range(30)],
                tool_call_inputs=[
                    {
                        "id": f"call_{i}",
                        "type": "function",
                        "function": {
                            "name": "edit",
                            "arguments": json.dumps(
                                {"file": f"file_{i}.txt", "content": "c" * 200}
                            ),
                        },
                    }
                ],
                logger=logger,
            )

        # Verify
        in_memory_chars = precise_char_count(session.messages)

        reloaded = Session.load(session.session_id, temp_db_uri)
        persisted_chars = precise_char_count(reloaded.messages)

        assert persisted_chars == in_memory_chars, (
            f"Mixed content integrity failure:\n"
            f"  In-memory: {in_memory_chars:,} chars\n"
            f"  Persisted: {persisted_chars:,} chars\n"
            f"  Lost: {in_memory_chars - persisted_chars:,} chars (~{(in_memory_chars - persisted_chars) // 4} tokens)"
        )


class TestClientServerBoundary:
    """
    Test the exact boundary where you observed token loss:
    Client -> Session.prompt() -> Database -> React Loop
    """

    @pytest.mark.asyncio
    async def test_client_to_session_boundary(
        self, temp_db_uri, sample_prompt_template
    ):
        """
        Simulate the exact flow:
        1. Client sends message
        2. Session.add_message() persists to DB
        3. React loop reads from session.messages (in-memory)
        4. Verify no loss at boundary
        """
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

        logger = logging.getLogger("test_logger")
        logger.setLevel(logging.INFO)

        # Simulate client sending multiple messages
        client_messages = []
        for i in range(20):
            content = f"Client message {i}: " + "x" * 200
            client_messages.append({"role": "user", "content": content})
            session.add_message({"role": "user", "content": content})

        # In-memory view (what react loop sees)
        in_memory_messages = list(session.messages)
        in_memory_chars = precise_char_count(in_memory_messages)

        # Simulate: new process loads session from DB
        loaded_session = Session.load(session.session_id, temp_db_uri)

        # Loaded view (what new process sees)
        loaded_messages = list(loaded_session.messages)
        loaded_chars = precise_char_count(loaded_messages)

        # CRITICAL: These must match exactly
        assert len(in_memory_messages) == len(loaded_messages), (
            f"Message count mismatch at client/server boundary: {len(in_memory_messages)} vs {len(loaded_messages)}"
        )

        assert in_memory_chars == loaded_chars, (
            f"TOKEN LOSS at client/server boundary!\n"
            f"  In-memory: {in_memory_chars:,} chars\n"
            f"  Loaded: {loaded_chars:,} chars\n"
            f"  Lost: {in_memory_chars - loaded_chars:,} chars (~{(in_memory_chars - loaded_chars) // 4} tokens)"
        )

        # Deep comparison
        for i, (mem_msg, loaded_msg) in enumerate(
            zip(in_memory_messages, loaded_messages)
        ):
            assert mem_msg == loaded_msg, f"Message {i} differs at boundary"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
