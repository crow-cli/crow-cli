"""System prompt skills bootstrap — llms.txt discovery when skills are missing."""

from __future__ import annotations

from crow_cli.agent.default.defaults import SYSTEM_PROMPT
from crow_cli.agent.prompt import render_template

SKILLS_URL = "https://crow-ai.dev/llms.txt"


def test_skills_block_lists_catalog_when_present():
    out = render_template(
        SYSTEM_PROMPT,
        skills=[{"name": "sg", "description": "ast-grep", "path": "/x/sg/SKILL.md"}],
        skills_dir="/x",
    )
    assert "**sg**" in out
    # populated catalog still gets the discovery pointer for missing skills
    assert SKILLS_URL in out


def test_bootstrap_block_when_no_skills():
    out = render_template(SYSTEM_PROMPT, skills=[], skills_dir="/x")
    assert SKILLS_URL in out
    assert "No skills are installed" in out
    assert "Add-only" in out
