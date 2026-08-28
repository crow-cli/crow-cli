"""System prompt assembly: skills catalog rendering and bootstrap discovery."""

from __future__ import annotations

from crow_cli.agent.prompt import render_template
from crow_cli.config.default.defaults import SYSTEM_PROMPT

SKILLS_URL = "https://crow-ai.dev/llms.txt"


def render(**overrides) -> str:
    """Render the real system prompt with a minimal, predictable context."""
    context = {
        "session_id": "test-session",
        "workspace": "/work",
        "display_tree": "/work",
        "agents_full": [],
        "agents_catalog": [],
        "skills": [],
        "skills_dir": "/home/tester/.agents/skills",
        "skills_roots": ["/home/tester/.agents/skills"],
    }
    context.update(overrides)
    return render_template(SYSTEM_PROMPT, **context)


def test_skills_block_lists_catalog_when_present():
    out = render(
        skills=[{"name": "sg", "description": "ast-grep", "path": "/x/sg/SKILL.md"}],
    )
    assert "**sg**" in out
    assert "/x/sg/SKILL.md" in out
    # populated catalog still gets the discovery pointer for missing skills
    assert SKILLS_URL in out


def test_skills_block_lists_every_root_in_precedence_order():
    out = render(
        skills=[{"name": "sg", "description": "ast-grep", "path": "/work/.agents/skills/sg/SKILL.md"}],
        skills_roots=["/work/.agents/skills", "/home/tester/.agents/skills"],
    )
    assert "/work/.agents/skills" in out
    assert "/home/tester/.agents/skills" in out
    assert out.index("/work/.agents/skills") < out.index("/home/tester/.agents/skills")


def test_bootstrap_block_when_no_skills():
    out = render()
    assert SKILLS_URL in out
    assert "No skills are installed" in out
    assert "Add-only" in out


def test_rules_block_loads_files_in_full():
    out = render(
        agents_full=[
            {"path": "/home/tester/.agents/AGENTS.md", "content": "GLOBAL RULE"},
            {"path": "/work/AGENTS.md", "content": "PROJECT RULE"},
        ]
    )
    assert "<RULES>" in out
    assert "GLOBAL RULE" in out
    assert "PROJECT RULE" in out


def test_rules_block_lists_catalog_with_location_and_preview():
    out = render(
        agents_catalog=[
            {"path": "/work/packages/api/AGENTS.md", "preview": "line one\nline two"}
        ]
    )
    assert "`/work/packages/api/AGENTS.md`" in out
    # The preview is flattened onto the catalog line, not expanded into the prompt.
    assert "line one line two" in out
    assert "\nline two" not in out


def test_no_rules_block_when_nothing_found():
    assert "<RULES>" not in render()
