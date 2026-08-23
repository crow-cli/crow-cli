"""Shared fixtures for Crow Agent tests."""

import tempfile
from pathlib import Path

import pytest
import yaml

from crow_cli.config import Config
from crow_cli.agent.memory import (
    AgentRecord,
    MemoryServiceError,
    MessageRecord,
    PromptRecord,
)


class FakeMemoryClient:
    """In-memory stand-in for the sqlite MemoryClient.

    The agent is fully decoupled from persistence: AgentSession talks to a
    MemoryClient. For hermetic unit tests we swap that client for
    this fake (patched over ``crow_cli.agent.session.MemoryClient``) instead of
    touching the real database. Storage is class-level so every instance the
    code constructs shares one dataset — writes via one client are readable via
    the next, exactly like the real service.
    """

    _agents: dict = {}
    _messages: dict = {}
    _prompts: dict = {}
    _session_mcp_servers: dict = {}
    _pid = [0]

    def __init__(self, base_url: str | None = None, *args, **kwargs):
        pass

    @classmethod
    def _reset(cls):
        cls._agents.clear()
        cls._messages.clear()
        cls._prompts.clear()
        cls._session_mcp_servers.clear()
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
    async def create_agent(self, *, agent_id, session_id, agent_idx=1,
                     fork_idx=1, forked_at=None, cwd="/tmp",
                     prompt_id=None, prompt_args=None, system_prompt="",
                     tool_definitions=None, request_params=None,
                     model_identifier="", **kwargs) -> AgentRecord:
        self._agents[agent_id] = {
            "agent_id": agent_id, "session_id": session_id, "agent_idx": agent_idx,
            "fork_idx": fork_idx, "forked_at": forked_at,
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

    async def get_max_agent_idx(self, session_id: str, fork_idx: int | None = 1) -> int:
        idxs = [
            a["agent_idx"]
            for a in self._agents.values()
            if a["session_id"] == session_id
            and (fork_idx is None or a.get("fork_idx", 1) == fork_idx)
        ]
        return max(idxs) if idxs else -1

    async def get_max_fork_idx(self, session_id: str, agent_idx: int) -> int:
        idxs = [
            a.get("fork_idx", 1)
            for a in self._agents.values()
            if a["session_id"] == session_id and a["agent_idx"] == agent_idx
        ]
        return max(idxs) if idxs else 1

    async def list_sessions(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return []

    # ---- session mcp servers (task system round trip) ----
    async def set_session_mcp_servers(self, session_id: str, servers: list) -> None:
        type(self)._session_mcp_servers[session_id] = list(servers)

    async def get_session_mcp_servers(self, session_id: str) -> list:
        return list(type(self)._session_mcp_servers.get(session_id, []))

    # ---- messages ----
    async def add_message(self, agent_id: str, message: dict, usage: dict | None = None) -> int:
        self._messages.setdefault(agent_id, []).append(message)
        return len(self._messages[agent_id])

    async def query_messages(
        self,
        *,
        session_id: str | None = None,
        agent_id: str | None = None,
        agent_idx: int | None = None,
        roles: list[str] | None = None,
        after: str | None = None,
        before: str | None = None,
        order: str = "asc",
        limit: int = -1,
        offset: int = 0,
    ) -> list:
        if agent_id is not None:
            agent_ids = [agent_id]
        elif session_id is not None:
            agent_ids = [
                a["agent_id"]
                for a in self._agents.values()
                if a["session_id"] == session_id
            ]
        else:
            raise MemoryServiceError(400, "query_messages needs session_id or agent_id")
        recs = []
        for aid in agent_ids:
            agent = self._agents.get(aid, {})
            if agent_idx is not None and agent.get("agent_idx") != agent_idx:
                continue
            for i, msg in enumerate(self._messages.get(aid, []), start=1):
                if roles and msg.get("role") not in roles:
                    continue
                recs.append(
                    MessageRecord(
                        id=i,
                        agent_id=aid,
                        session_id=agent.get("session_id", ""),
                        agent_idx=agent.get("agent_idx", 1),
                        role=msg.get("role", ""),
                        created_at="2026-01-01T00:00:00+00:00",
                        data=msg,
                        fork_idx=agent.get("fork_idx", 1),
                    )
                )
        recs.sort(key=lambda r: r.id, reverse=(order == "desc"))
        if offset:
            recs = recs[offset:]
        if limit is not None and limit >= 0:
            recs = recs[:limit]
        return recs

    async def save_messages(self, agent_id: str, messages: list[dict]) -> list[int]:
        existing = self._messages.setdefault(agent_id, [])
        start = len(existing)
        existing.extend(messages)
        return list(range(start + 1, len(existing) + 1))


@pytest.fixture
def memory_service(monkeypatch):
    """Patch the persistence client with the in-memory fake; reset per test.

    Persistence itself is tested in tests/memory/test_store.py. crow-cli
    unit tests that touch sessions use this fake so they stay hermetic (no
    real db).
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
# Test tiers — ALL mandatory. Every tier runs on every `pytest` invocation:
#
#   tests/unit/         fast, hermetic. Tests that touch sessions use the
#                       `memory_service` fake (see above).
#   tests/integration/  real sqlite persistence, agent spawn.
#   tests/e2e/          live LLM calls via the configured provider.
#
# Persistence itself is tested in tests/memory/test_store.py (sqlite +
# FTS5 + image extract/hydrate). The agent is fully decoupled from
# persistence: it talks to MemoryClient, which owns the sqlite file.
#
# The opt-in flags were removed 2026-08-22: optional tiers silently rotted
# (the session-fork sprint shipped with 10 broken integration tests nobody
# ever ran). If a tier is too expensive for some context, deselect it
# explicitly (pytest --deselect / -k) — never hide it behind a flag.
# ---------------------------------------------------------------------------
