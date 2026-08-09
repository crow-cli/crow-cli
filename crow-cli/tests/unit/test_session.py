"""Unit tests for session helpers.

The session/persistence contract (create/load/add_message round-trips) is
tested in crow-memory, which owns the storage layer. Here we cover the pure
helpers and the cancellation-persistence contract (thinking-only turns must
survive), the latter against the in-memory fake client.
"""

import logging

import pytest

from crow_cli.agent.session import (
    AgentSession,
    _parse_frontmatter,
    get_skills,
    lookup_or_create_prompt,
)


class TestParseFrontmatter:
    """Frontmatter is parsed with PyYAML, not a hand-rolled parser."""

    def test_simple_mapping(self):
        meta = _parse_frontmatter("---\nname: x\ndescription: y\n---\nbody")
        assert meta == {"name": "x", "description": "y"}

    def test_folded_scalar_and_extra_keys(self):
        text = "---\nname: x\ndescription: >-\n  folded\n  text.\nversion: 2\n---\nbody"
        meta = _parse_frontmatter(text)
        assert meta["description"] == "folded text."
        assert meta["version"] == 2

    def test_no_frontmatter_returns_none(self):
        assert _parse_frontmatter("# just markdown") is None

    def test_invalid_yaml_returns_none(self):
        assert _parse_frontmatter('---\nname: "unclosed\n---\n') is None

    def test_non_mapping_returns_none(self):
        assert _parse_frontmatter("---\n- a\n- b\n---\n") is None


class TestGetSkills:
    """get_skills returns structured skills and skips invalid entries."""

    def _mk(self, root, name, content):
        d = root / name
        d.mkdir()
        (d / "SKILL.md").write_text(content)

    def test_returns_structured_skills(self, tmp_path):
        self._mk(tmp_path, "alpha", "---\nname: alpha\ndescription: first\n---\n")
        self._mk(tmp_path, "beta", "---\nname: beta\ndescription: second\n---\n")
        skills = {s["name"]: s for s in get_skills(tmp_path)}
        assert set(skills) == {"alpha", "beta"}
        assert skills["alpha"]["description"] == "first"
        assert skills["alpha"]["path"].endswith("alpha/SKILL.md")

    def test_skips_invalid_entries(self, tmp_path):
        self._mk(tmp_path, "good", "---\nname: good\ndescription: ok\n---\n")
        self._mk(tmp_path, "no-name", "---\ndescription: missing name\n---\n")
        self._mk(tmp_path, "no-fm", "# no frontmatter\n")
        self._mk(tmp_path, "bad-yaml", '---\nname: "unclosed\n---\n')
        (tmp_path / "stray-file").write_text("not a skill dir")
        assert {s["name"] for s in get_skills(tmp_path)} == {"good"}

    def test_missing_dir_returns_empty(self, tmp_path):
        assert get_skills(tmp_path / "does-not-exist") == []


class TestCancelledTurnPersistence:
    """A turn cancelled while the model is still thinking has no content and
    no tool calls — the accumulated reasoning is the only record of what the
    agent was doing. It must be persisted so reconstruction hands it back to
    the next turn (and query_session can show it)."""

    @pytest.fixture
    async def session(self, memory_service, sample_prompt_template):
        prompt_id = await lookup_or_create_prompt(
            sample_prompt_template, name="test-prompt"
        )
        return await AgentSession.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Crow", "workspace": "/tmp", "display_tree": "test/"},
            tool_definitions=[],
            request_params={},
            model_identifier="test-model",
            cwd="/tmp",
            agent_idx=1,
        )

    async def test_thinking_only_turn_is_persisted(self, session, memory_service):
        await session.add_assistant_response(
            ["thinking ", "about the task"], [], [], logging.getLogger("test")
        )
        stored = memory_service._messages[session.agent_id]
        assert stored[-1] == {
            "role": "assistant",
            "content": "",
            "reasoning_content": "thinking about the task",
        }

    async def test_empty_turn_is_not_persisted(self, session, memory_service):
        before = len(memory_service._messages[session.agent_id])
        await session.add_assistant_response([], [], [], logging.getLogger("test"))
        assert len(memory_service._messages[session.agent_id]) == before
