"""Shared fixtures for Crow Agent tests."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from crow_cli.agent.configure import Config
from crow_cli.agent.memory import AgentRecord, MemoryServiceError, PromptRecord


class FakeMemoryClient:
    """In-memory stand-in for the crow-memory service.

    The agent is fully decoupled from persistence: AgentSession talks to a
    MemoryClient over HTTP. For hermetic unit tests we swap that client for
    this fake (patched over ``crow_cli.agent.session.MemoryClient``) instead of
    standing up the real service. Storage is class-level so every instance the
    code constructs shares one dataset — writes via one client are readable via
    the next, exactly like the real service.
    """

    _agents: dict = {}
    _messages: dict = {}
    _prompts: dict = {}
    _pid = [0]

    def __init__(self, base_url: str | None = None, *args, **kwargs):
        pass

    @classmethod
    def _reset(cls):
        cls._agents.clear()
        cls._messages.clear()
        cls._prompts.clear()
        cls._pid[0] = 0

    async def close(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass

    async def health(self):
        return {"status": "ok"}

    # ---- prompts ----
    async def lookup_or_create_prompt(self, template: str, name: str = "crow-default") -> str:
        for pid, p in self._prompts.items():
            if p["template"] == template:
                return pid
        self._pid[0] += 1
        pid = f"prompt-{self._pid[0]}"
        self._prompts[pid] = {"id": pid, "name": name, "template": template, "created": True}
        return pid

    async def get_prompt(self, prompt_id: str) -> PromptRecord:
        if prompt_id not in self._prompts:
            raise MemoryServiceError(404, f"prompt '{prompt_id}' not found")
        return PromptRecord.from_dict(self._prompts[prompt_id])

    # ---- agents ----
    async def create_agent(self, *, agent_id, session_id, agent_idx=1, cwd="/tmp",
                     prompt_id=None, prompt_args=None, system_prompt="",
                     tool_definitions=None, request_params=None,
                     model_identifier="", **kwargs) -> AgentRecord:
        self._agents[agent_id] = {
            "agent_id": agent_id, "session_id": session_id, "agent_idx": agent_idx,
            "cwd": cwd, "prompt_id": prompt_id or "", "prompt_args": prompt_args or {},
            "system_prompt": system_prompt, "tool_definitions": tool_definitions or [],
            "request_params": request_params or {}, "model_identifier": model_identifier,
            "status": "active", "created_at": "2026-01-01T00:00:00+00:00",
        }
        self._messages.setdefault(agent_id, [])
        return AgentRecord.from_dict(self._agents[agent_id])

    async def load(self, agent_id: str, hydrate: bool = False) -> tuple[AgentRecord, list[dict]]:
        if agent_id not in self._agents:
            raise MemoryServiceError(404, f"agent '{agent_id}' not found")
        return (
            AgentRecord.from_dict(self._agents[agent_id]),
            list(self._messages.get(agent_id, [])),
        )

    async def list_agents(self, session_id: str | None = None) -> list[AgentRecord]:
        return [
            AgentRecord.from_dict(a)
            for a in self._agents.values()
            if session_id is None or a["session_id"] == session_id
        ]

    async def get_max_agent_idx(self, session_id: str) -> int:
        idxs = [a["agent_idx"] for a in self._agents.values() if a["session_id"] == session_id]
        return max(idxs) if idxs else -1

    async def list_sessions(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return []

    # ---- messages ----
    async def add_message(self, agent_id: str, message: dict, usage: dict | None = None) -> int:
        self._messages.setdefault(agent_id, []).append(message)
        return len(self._messages[agent_id])

    async def save_messages(self, agent_id: str, messages: list[dict]) -> list[int]:
        existing = self._messages.setdefault(agent_id, [])
        start = len(existing)
        existing.extend(messages)
        return list(range(start + 1, len(existing) + 1))


@pytest.fixture
def memory_service(monkeypatch):
    """Patch the persistence client with the in-memory fake; reset per test.

    Persistence itself is tested in crow-memory. crow-cli unit tests that touch
    sessions use this fake so they stay hermetic (no running service required).
    """
    FakeMemoryClient._reset()
    import crow_cli.agent.session as session_mod

    monkeypatch.setattr(session_mod, "MemoryClient", FakeMemoryClient)
    return FakeMemoryClient


@pytest.fixture
def test_config_dir(tmp_path):
    """Create a temporary config directory with test config."""
    config_dir = tmp_path / ".agents" / "crow"
    config_dir.mkdir(parents=True)

    # Create .env file
    env_file = config_dir / ".env"
    env_file.write_text("TEST_VAR=test_value\nAPI_KEY=test_api_key\n")

    # Create config.yaml
    config_file = config_dir / "config.yaml"
    config_data = {
        "providers": {
            "test-provider": {
                "api_key": "${API_KEY}",
                "base_url": "https://test.example.com/v1",
            }
        },
        "models": {
            "test-model": {"provider": "test-provider", "model": "test-model-id"}
        },
    }
    config_file.write_text(yaml.dump(config_data))

    return config_dir


@pytest.fixture
def test_config(test_config_dir):
    """Load test configuration."""
    return Config.load(test_config_dir)


@pytest.fixture
def sample_prompt_template():
    """Sample system prompt template."""
    return """You are {{name}}.
Workspace: {{workspace}}
Directory: {{display_tree}}
"""


@pytest.fixture
def sample_tool_definition():
    """Sample tool definition for testing."""
    return {
        "name": "test_tool",
        "description": "A test tool",
        "inputSchema": {
            "type": "object",
            "properties": {"param1": {"type": "string"}},
            "required": ["param1"],
        },
    }


@pytest.fixture
def sample_messages():
    """Sample conversation messages."""
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there! How can I help?"},
    ]


@pytest.fixture
def test_file_content(tmp_path):
    """Create a test file and return its path and content."""
    file_path = tmp_path / "test.txt"
    content = "Hello, World!\nThis is a test file."
    file_path.write_text(content)
    return {"path": str(file_path), "content": content}


@pytest.fixture
def sample_workspace(tmp_path):
    """Create a sample workspace directory structure."""
    # Create some files
    (tmp_path / "file1.txt").write_text("File 1 content")
    (tmp_path / "file2.py").write_text("print('hello')")

    # Create subdirectory
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "file3.txt").write_text("File 3 content")

    return str(tmp_path)


# ---------------------------------------------------------------------------
# Test tiers
#
#   tests/unit/         fast, hermetic — always run. Tests that touch sessions
#                       use the `memory_service` fake (see above), so no running
#                       crow-memory service is required.
#   tests/integration/  spawn the agent / real environment — opt-in
#   tests/e2e/          make live LLM calls via the configured provider — opt-in
#
# Persistence itself is tested in crow-memory (crow-memory/src + its smoke
# tests), not here. The agent is fully decoupled from persistence: it talks to
# the crow-memory service over HTTP. The long-term direction is a always-on
# daemon/service (ACP v2), at which point service-backed tests would run against
# a dedicated instance on a test port rather than a fake.
#
# Default `pytest` runs only the unit tier so the suite is green and fast.
# Run the real tests with:
#   pytest --run-integration        (or CROW_RUN_INTEGRATION=1)
#   pytest --run-e2e                (or CROW_RUN_E2E=1)  [live LLM: cost/slow]
# ---------------------------------------------------------------------------


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="run integration tests (spawn the agent / real environment)",
    )
    parser.addoption(
        "--run-e2e",
        action="store_true",
        default=False,
        help="run end-to-end tests (make live LLM calls via the configured provider)",
    )


def pytest_collection_modifyitems(config, items):
    run_integration = config.getoption("--run-integration") or os.environ.get(
        "CROW_RUN_INTEGRATION"
    )
    run_e2e = config.getoption("--run-e2e") or os.environ.get("CROW_RUN_E2E")

    skip_integration = pytest.mark.skip(
        reason="integration tier: pass --run-integration (or CROW_RUN_INTEGRATION=1)"
    )
    skip_e2e = pytest.mark.skip(
        reason="e2e tier: pass --run-e2e (or CROW_RUN_E2E=1) — makes live LLM calls"
    )

    for item in items:
        path = str(item.path)
        if "/integration/" in path and not run_integration:
            item.add_marker(skip_integration)
        elif "/e2e/" in path and not run_e2e:
            item.add_marker(skip_e2e)
