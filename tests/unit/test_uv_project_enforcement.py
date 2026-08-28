"""Tests for --project enforcement in terminal commands."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from crow_cli.agent.context import TurnCtx
from crow_cli.agent.hooks import uv_project_hook
from crow_cli.agent.tools import execute_acp_terminal


@pytest.fixture
def mock_conn():
    """Mock ACP Client connection."""
    return AsyncMock()


@pytest.fixture
def mock_session():
    """Trunk agent row (fork_idx=1) with a cwd."""
    session = MagicMock()
    session.cwd = "/tmp"
    session.agent_id = "session-1-1"
    return session


@pytest.fixture
def mock_logger():
    """Mock logger."""
    return MagicMock()


@pytest.fixture
def ctx(mock_conn, mock_session, mock_logger):
    """One prompt turn: real TurnCtx, mocked conn/session.

    The uv_project_hook is installed exactly as the agent installs it, so the
    test exercises the real hook path inside execute_acp_terminal.
    """
    return TurnCtx(
        conn=mock_conn,
        config=MagicMock(),
        session=mock_session,
        turn_id="1",
        logger=mock_logger,
        hooks=(uv_project_hook,),
    )


def _terminal_mocks(mock_conn):
    """Wire the ACP terminal round trip to succeed."""
    mock_conn.create_terminal.return_value = AsyncMock(terminal_id="term_1")
    mock_conn.wait_for_terminal_exit.return_value = AsyncMock(exit_code=0, signal=None)
    mock_conn.terminal_output.return_value = AsyncMock(
        output="success", truncated=False
    )


@pytest.mark.asyncio
async def test_reject_uv_without_project(ctx, mock_conn):
    """Test that 'uv run' without --project is rejected."""
    result = await execute_acp_terminal(ctx, "123", {"command": "uv run test.py"})
    assert "REJECTED" in result
    assert "--project" in result
    mock_conn.create_terminal.assert_not_called()


@pytest.mark.asyncio
async def test_reject_uv_chained_without_project(ctx, mock_conn):
    """Test that 'cd && uv run' without --project is rejected."""
    result = await execute_acp_terminal(
        ctx, "123", {"command": "cd /tmp && uv run test.py"}
    )
    assert "REJECTED" in result
    mock_conn.create_terminal.assert_not_called()


@pytest.mark.asyncio
async def test_allow_uv_sync_exempt_from_project_flag(ctx, mock_conn):
    """'uv sync' is exempt from the --project requirement (it targets the cwd project)."""
    _terminal_mocks(mock_conn)

    result = await execute_acp_terminal(ctx, "123", {"command": "uv sync"})
    assert "REJECTED" not in result
    mock_conn.create_terminal.assert_called_once()


@pytest.mark.asyncio
async def test_allow_uv_with_project(ctx, mock_conn):
    """Test that 'uv --project' is allowed and executes."""
    _terminal_mocks(mock_conn)

    result = await execute_acp_terminal(
        ctx, "123", {"command": "uv --project . run test.py"}
    )
    assert "REJECTED" not in result
    mock_conn.create_terminal.assert_called_once()


@pytest.mark.asyncio
async def test_allow_uv_chained_with_project(ctx, mock_conn):
    """Test that 'cd && uv --project' is allowed and executes."""
    _terminal_mocks(mock_conn)

    result = await execute_acp_terminal(
        ctx, "123", {"command": "cd /tmp && uv --project . run test.py"}
    )
    assert "REJECTED" not in result
    mock_conn.create_terminal.assert_called_once()


@pytest.mark.asyncio
async def test_allow_uvx_without_project(ctx, mock_conn):
    """Test that 'uvx' commands are allowed (they don't need --project)."""
    _terminal_mocks(mock_conn)

    result = await execute_acp_terminal(ctx, "123", {"command": "uvx some-package"})
    assert "REJECTED" not in result
    mock_conn.create_terminal.assert_called_once()
