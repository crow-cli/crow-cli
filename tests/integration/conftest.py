"""Fixtures for tests that drive the real crow-cli TUI.

Isolation matters: the TUI writes session tabs to the shared crow.db and logs
under the XDG dirs, so point every home at a temp directory before anything
reads it. `get_default_config_dir` resolves the module global at call time, so
monkeypatching it redirects config + db cleanly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from crow_cli.tui.agent_servers import resolve_agent_server

MOCK_AGENT_PATH = Path(__file__).parent / "mock_acp_agent.py"


@pytest.fixture
def isolated_crow_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect crow's config dir (and therefore crow.db) plus XDG dirs to tmp."""
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    state_dir = tmp_path / "state"

    import crow_cli.config.config as config_module

    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_DIR", config_dir)
    monkeypatch.setenv("XDG_DATA_HOME", str(data_dir))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _blast_server(env: dict[str, str]) -> dict:
    """An `agent_servers` custom entry pointing at the load-blast mock agent."""
    return {
        "type": "custom",
        "command": sys.executable,
        "args": [str(MOCK_AGENT_PATH)],
        "env": env,
    }


BLAST_ENV = {
    # ~20s of stream from a fast endpoint: 600 tokens/sec.
    "CROW_MOCK_CHUNKS": "12000",
    "CROW_MOCK_CHUNK_CHARS": "10",
    "CROW_MOCK_TOKENS_PER_SEC": "600",
    "PYTHONUNBUFFERED": "1",
}


@pytest.fixture
def blast_agent(isolated_crow_home: Path) -> tuple[dict, Path]:
    """The mock agent resolved exactly like `crow-cli -a blast`.

    Returns the agent definition and the path the mock writes its diagnostics
    (chunk counts, cancel arrival) to.
    """
    log_path = isolated_crow_home.parent / "mock_agent.log"
    servers = {"blast": _blast_server({**BLAST_ENV, "CROW_MOCK_LOG": str(log_path)})}
    return resolve_agent_server("blast", servers), log_path


@pytest.fixture
def wedged_agent(isolated_crow_home: Path) -> tuple[dict, Path]:
    """The mock agent, ignoring `session/cancel` and streaming to the end.

    Models an agent that does not cooperate: cancelling must still unlock the
    UI on the client's own clock.
    """
    log_path = isolated_crow_home.parent / "wedged_agent.log"
    servers = {
        "wedged": _blast_server(
            {
                **BLAST_ENV,
                "CROW_MOCK_IGNORE_CANCEL": "1",
                "CROW_MOCK_LOG": str(log_path),
            }
        )
    }
    return resolve_agent_server("wedged", servers), log_path
