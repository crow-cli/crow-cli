"""CLI --fork / --fork-idx flag validation (typer layer, no agent spawn).

The full fork flow is gated by the E2E tier; here we only pin down the
argument contract: both flags need -s/--session, and they exclude each other.
"""

import pytest
from rich.console import Console
from typer.testing import CliRunner

from crow_cli.cli import main as cli_main
from crow_cli.cli.main import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def wide_console(monkeypatch):
    # Keep rich from wrapping the error lines so assertions stay simple.
    monkeypatch.setattr(cli_main.client, "_console", Console(width=200))


def test_fork_requires_session():
    result = runner.invoke(app, ["run", "--fork", "hello"])
    assert result.exit_code == 1
    assert "require -s/--session" in result.output


def test_fork_idx_requires_session():
    result = runner.invoke(app, ["run", "--fork-idx", "2", "hello"])
    assert result.exit_code == 1
    assert "require -s/--session" in result.output


def test_fork_and_fork_idx_mutually_exclusive():
    result = runner.invoke(app, ["run", "-s", "abc", "--fork", "--fork-idx", "2", "hello"])
    assert result.exit_code == 1
    assert "mutually exclusive" in result.output
