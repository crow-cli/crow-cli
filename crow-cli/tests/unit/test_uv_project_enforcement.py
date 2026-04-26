"""Tests for --project enforcement in terminal commands."""

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from crow_cli.agent.tools import execute_acp_terminal


@pytest.fixture
def mock_conn():
    """Mock ACP Client connection."""
    return AsyncMock()


@pytest.fixture
def mock_sessions():
    """Mock session store."""
    session = MagicMock()
    session.cwd = "/tmp"
    return {"session_1": session}


@pytest.fixture
def mock_logger():
    """Mock logger."""
    return MagicMock()


@pytest.mark.asyncio
async def test_reject_uv_without_project(mock_conn, mock_sessions, mock_logger):
    """Test that 'uv run' without --project is rejected."""
    result = await execute_acp_terminal(
        conn=mock_conn,
        sessions=mock_sessions,
        turn_id="1",
        agent_id="session-1-0",
        tool_call_id="123",
        args={"command": "uv run test.py"},
        logger=mock_logger,
                hooks=[],
    )
    assert "REJECTED" in result
    assert "--project" in result
    mock_conn.create_terminal.assert_not_called()


@pytest.mark.asyncio
async def test_reject_uv_chained_without_project(mock_conn, mock_sessions, mock_logger):
    """Test that 'cd && uv run' without --project is rejected."""
    result = await execute_acp_terminal(
        conn=mock_conn,
        sessions=mock_sessions,
        turn_id="1",
        agent_id="session-1-0",
        tool_call_id="123",
        args={"command": "cd /tmp && uv run test.py"},
        logger=mock_logger,
                hooks=[],
    )
    assert "REJECTED" in result
    mock_conn.create_terminal.assert_not_called()


@pytest.mark.asyncio
async def test_reject_uv_sync_without_project(mock_conn, mock_sessions, mock_logger):
    """Test that 'uv sync' without --project is rejected."""
    result = await execute_acp_terminal(
        conn=mock_conn,
        sessions=mock_sessions,
        turn_id="1",
        agent_id="session-1-0",
        tool_call_id="123",
        args={"command": "uv sync"},
        logger=mock_logger,
                hooks=[],
    )
    assert "REJECTED" in result


@pytest.mark.asyncio
async def test_allow_uv_with_project(mock_conn, mock_sessions, mock_logger):
    """Test that 'uv --project' is allowed and executes."""
    # Setup mocks for successful execution
    mock_conn.create_terminal.return_value = AsyncMock(terminal_id="term_1")
    mock_conn.wait_for_terminal_exit.return_value = AsyncMock(exit_code=0, signal=None)
    mock_conn.terminal_output.return_value = AsyncMock(
        output="success", truncated=False
    )

    result = await execute_acp_terminal(
        conn=mock_conn,
        sessions=mock_sessions,
        turn_id="1",
        agent_id="session-1-0",
        tool_call_id="123",
        args={"command": "uv --project . run test.py"},
        logger=mock_logger,
                hooks=[],
    )
    assert "REJECTED" not in result
    mock_conn.create_terminal.assert_called_once()


@pytest.mark.asyncio
async def test_allow_uv_chained_with_project(mock_conn, mock_sessions, mock_logger):
    """Test that 'cd && uv --project' is allowed and executes."""
    mock_conn.create_terminal.return_value = AsyncMock(terminal_id="term_1")
    mock_conn.wait_for_terminal_exit.return_value = AsyncMock(exit_code=0, signal=None)
    mock_conn.terminal_output.return_value = AsyncMock(
        output="success", truncated=False
    )

    result = await execute_acp_terminal(
        conn=mock_conn,
        sessions=mock_sessions,
        turn_id="1",
        agent_id="session-1-0",
        tool_call_id="123",
        args={"command": "cd /tmp && uv --project . run test.py"},
        logger=mock_logger,
                hooks=[],
    )
    assert "REJECTED" not in result
    mock_conn.create_terminal.assert_called_once()


@pytest.mark.asyncio
async def test_allow_uvx_without_project(mock_conn, mock_sessions, mock_logger):
    """Test that 'uvx' commands are allowed (they don't need --project)."""
    mock_conn.create_terminal.return_value = AsyncMock(terminal_id="term_1")
    mock_conn.wait_for_terminal_exit.return_value = AsyncMock(exit_code=0, signal=None)
    mock_conn.terminal_output.return_value = AsyncMock(
        output="success", truncated=False
    )

    result = await execute_acp_terminal(
        conn=mock_conn,
        sessions=mock_sessions,
        turn_id="1",
        agent_id="session-1-0",
        tool_call_id="123",
        args={"command": "uvx some-package"},
        logger=mock_logger,
                hooks=[],
    )
    assert "REJECTED" not in result
    mock_conn.create_terminal.assert_called_once()
