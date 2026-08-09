#!/usr/bin/env python3
"""
Test script to verify error handling in send_request function.
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

from openai import APIConnectionError, APIError, APITimeoutError, RateLimitError
from openai._exceptions import APITimeoutError as APITimeoutError2

sys.path.insert(0, "/home/thomas/src/backup/nid-backup/crow-cli/src")

from crow_cli.agent.react import send_request
from crow_cli.agent.session import AgentSession


async def test_timeout_error_retry():
    """Test that timeout errors trigger retry logic."""
    print("Testing timeout error retry...")

    # Create mock objects
    mock_llm = MagicMock()
    mock_session = MagicMock(spec=AgentSession)
    mock_session.model_identifier = "test-model"
    mock_session.messages = [{"role": "user", "content": "test"}]
    mock_tools = []

    # Make the API call fail with timeout twice, then succeed
    call_count = 0

    async def mock_create(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise APITimeoutError("Request timed out", response=MagicMock())
        return MagicMock()

    mock_llm.chat.completions.create = mock_create

    # Test with short retry delay
    result = await send_request(
        mock_llm, mock_session, mock_tools, max_retries=3, retry_delay=0.1
    )

    assert call_count == 3, f"Expected 3 calls, got {call_count}"
    print(f"✓ Timeout retry test passed ({call_count} calls made)")


async def test_rate_limit_error_retry():
    """Test that rate limit errors trigger retry logic."""
    print("Testing rate limit error retry...")

    # Create mock objects
    mock_llm = MagicMock()
    mock_session = MagicMock(spec=AgentSession)
    mock_session.model_identifier = "test-model"
    mock_session.messages = [{"role": "user", "content": "test"}]
    mock_tools = []

    # Make the API call fail with rate limit twice, then succeed
    call_count = 0

    async def mock_create(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RateLimitError("Rate limit exceeded", response=MagicMock())
        return MagicMock()

    mock_llm.chat.completions.create = mock_create

    # Test with short retry delay
    result = await send_request(
        mock_llm, mock_session, mock_tools, max_retries=3, retry_delay=0.1
    )

    assert call_count == 3, f"Expected 3 calls, got {call_count}"
    print(f"✓ Rate limit retry test passed ({call_count} calls made)")


async def test_connection_error_retry():
    """Test that connection errors trigger retry logic."""
    print("Testing connection error retry...")

    # Create mock objects
    mock_llm = MagicMock()
    mock_session = MagicMock(spec=AgentSession)
    mock_session.model_identifier = "test-model"
    mock_session.messages = [{"role": "user", "content": "test"}]
    mock_tools = []

    # Make the API call fail with connection error twice, then succeed
    call_count = 0

    async def mock_create(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise APIConnectionError("Connection failed", response=MagicMock())
        return MagicMock()

    mock_llm.chat.completions.create = mock_create

    # Test with short retry delay
    result = await send_request(
        mock_llm, mock_session, mock_tools, max_retries=3, retry_delay=0.1
    )

    assert call_count == 3, f"Expected 3 calls, got {call_count}"
    print(f"✓ Connection error retry test passed ({call_count} calls made)")


async def test_max_retries_exceeded():
    """Test that error is raised after max retries."""
    print("Testing max retries exceeded...")

    # Create mock objects
    mock_llm = MagicMock()
    mock_session = MagicMock(spec=AgentSession)
    mock_session.model_identifier = "test-model"
    mock_session.messages = [{"role": "user", "content": "test"}]
    mock_tools = []

    # Always fail
    call_count = 0

    async def mock_create(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise APITimeoutError("Request timed out", response=MagicMock())

    mock_llm.chat.completions.create = mock_create

    # Test with short retry delay
    try:
        await send_request(
            mock_llm, mock_session, mock_tools, max_retries=2, retry_delay=0.1
        )
        assert False, "Should have raised an exception"
    except APITimeoutError:
        pass

    assert call_count == 2, f"Expected 2 calls, got {call_count}"
    print(f"✓ Max retries test passed ({call_count} calls made before failure)")


async def test_successful_request():
    """Test that successful requests work normally."""
    print("Testing successful request...")

    # Create mock objects
    mock_llm = MagicMock()
    mock_session = MagicMock(spec=SAgentession)
    mock_session.model_identifier = "test-model"
    mock_session.messages = [{"role": "user", "content": "test"}]
    mock_tools = []

    # Always succeed
    call_count = 0

    async def mock_create(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return MagicMock()

    mock_llm.chat.completions.create = mock_create

    # Test
    result = await send_request(mock_llm, mock_session, mock_tools)

    assert call_count == 1, f"Expected 1 call, got {call_count}"
    print(f"✓ Successful request test passed")


async def main():
    """Run all tests."""
    print("=" * 50)
    print("Testing send_request error handling")
    print("=" * 50)

    await test_successful_request()
    await test_timeout_error_retry()
    await test_rate_limit_error_retry()
    await test_connection_error_retry()
    await test_max_retries_exceeded()

    print("=" * 50)
    print("All tests passed! ✓")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
