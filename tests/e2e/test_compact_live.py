"""Live compaction (end-to-end, real provider, real sqlite).

Compaction makes THREE real calls now — the summary plus a harness analysis and
a set of project ideas over the same history — and the two extra ones produce
files a human is supposed to read. A mocked pass can prove the plumbing; only a
live one can prove the prompts actually get a real model to produce a real
critique rather than a polite shrug.

The history below is scripted rather than earned by running real turns: it is
the conversation content the passes read, and paying for three react turns to
generate it would triple the cost of a test whose subject is the compaction
calls. It deliberately contains harness friction (an ambiguous ``edit`` that the
tool refused) so the analysis pass has something concrete to bite on.

Asserts are loose — the output is nondeterministic — but they are about
structure the prompts explicitly demand, so a prompt that stops working fails
here rather than quietly producing mush.
"""

import logging
from pathlib import Path

import pytest
import yaml

from crow_cli.agent.compact import analysis_path, compact, ideas_path
from crow_cli.config import Config
from crow_cli.agent.session import make_agent_session

from tests.e2e.test_session_update_transmission import get_llm_client

logger = logging.getLogger(__name__)


def _tool_call(call_id: str, name: str, arguments: str) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


# A short but real-shaped crow-cli session: a rename task, a search, an edit
# that the tool rejected for being ambiguous, a retry, and a test run.
HISTORY = [
    {
        "role": "user",
        "content": (
            "Rename the helper `_ancestors` to `ancestors` in "
            "src/crow_cli/agent/prompt.py and update every call site, so the "
            "CLI can reuse it for project-scope discovery."
        ),
    },
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            _tool_call(
                "call_1", "terminal", '{"command": "rg -n _ancestors src/ tests/"}'
            )
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": (
            "src/crow_cli/agent/prompt.py:203:def _ancestors(start: Path):\n"
            "src/crow_cli/agent/prompt.py:251:    for root in _ancestors(cwd):\n"
            "src/crow_cli/agent/prompt.py:360:    for root in _ancestors(cwd):\n"
        ),
    },
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            _tool_call(
                "call_2",
                "edit",
                '{"file_path": "src/crow_cli/agent/prompt.py", '
                '"old_string": "_ancestors", "new_string": "ancestors"}',
            )
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "call_2",
        "content": (
            "Error: old_string must be unique in the file — it matched 3 times. "
            "Provide more surrounding context, or pass replace_all=true."
        ),
    },
    {
        "role": "assistant",
        "content": (
            "The edit tool refused the bare identifier because it matched three "
            "times. Re-running with replace_all=true, which is what a rename "
            "actually wants — the error message naming the flag is the only "
            "reason I did not hand-widen the context three times instead."
        ),
        "tool_calls": [
            _tool_call(
                "call_3",
                "edit",
                '{"file_path": "src/crow_cli/agent/prompt.py", '
                '"old_string": "_ancestors", "new_string": "ancestors", '
                '"replace_all": true}',
            )
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "call_3",
        "content": "Successfully edited src/crow_cli/agent/prompt.py (3 replacements)",
    },
    {
        "role": "user",
        "content": "now make sure nothing else imports the old name and run the tests",
    },
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            _tool_call(
                "call_4",
                "terminal",
                '{"command": "uv --project . run pytest tests/unit/test_prompt.py -q"}',
            )
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "call_4",
        "content": "14 passed in 0.61s",
    },
    {
        "role": "assistant",
        "content": (
            "Done. `_ancestors` is now `ancestors` at all three sites and the "
            "prompt tests pass. Nothing outside prompt.py referenced the old "
            "name, so the CLI can import it directly."
        ),
    },
]

ANALYSIS_HEADINGS = (
    "## What worked well",
    "## What did not work",
    "## Bugs",
    "## Ideas",
)

IDEAS_HEADINGS = (
    "## Assumptions worth attacking",
    "## Prior art you should steal from",
    "## Directions nobody has pointed at",
    "## What would make this obsolete",
    "## Cheapest decisive experiments",
)


def _front_matter(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    assert text.startswith("---\n"), f"{path} has no frontmatter"
    head, body = text[len("---\n") :].split("\n---\n\n", 1)
    return yaml.safe_load(head), body


@pytest.mark.asyncio
async def test_live_compact_writes_a_real_analysis_and_real_ideas(tmp_path):
    """One real compaction: the summary becomes the new generation's first
    message, and the two reflection passes leave readable markdown behind."""
    client, model_id = get_llm_client()
    if client is None:
        pytest.skip("No LLM provider configured")

    config = Config.load()
    # Never touch the real db or the developer's real ~/.agents/crow/ideas.
    config.db_uri = f"sqlite:///{tmp_path / 'e2e.db'}"
    config.config_dir = tmp_path / "crow"
    project = tmp_path / "project"
    project.mkdir()

    session = await make_agent_session(
        config, tools=[], model_id=model_id, cwd=str(project)
    )
    for message in HISTORY:
        await session.add_message(message)

    new_session = await compact(session, client, config, logger=logger)

    # --- the summary still did its job -----------------------------------
    assert new_session.agent_idx == session.agent_idx + 1
    assert len(new_session.messages) == 2
    summary = str(new_session.messages[1].get("content") or "")
    assert "ancestors" in summary, f"summary lost the subject of the session: {summary[:400]}"

    # --- both notes exist, at the two designed scopes ---------------------
    analysis_file = analysis_path(config.config_dir, session.agent_id)
    ideas_file = ideas_path(session.cwd, session.agent_id)
    assert analysis_file.exists(), "the analysis pass wrote nothing"
    assert ideas_file.exists(), "the ideas pass wrote nothing"
    assert analysis_file.parent == config.config_dir / "ideas"
    assert ideas_file.parent == project / ".agents" / "crow" / "ideas"

    # --- and they are notes, not mush -------------------------------------
    meta, analysis = _front_matter(analysis_file)
    assert meta["kind"] == "analysis"
    assert meta["agent"] == session.agent_id
    assert meta["session"] == session.session_id
    assert meta["model"] == model_id
    assert len(analysis.strip()) > 200, analysis
    assert any(h in analysis for h in ANALYSIS_HEADINGS), analysis[:800]

    meta, ideas = _front_matter(ideas_file)
    assert meta["kind"] == "ideas"
    assert meta["agent"] == session.agent_id
    assert meta["cwd"] == session.cwd
    assert len(ideas.strip()) > 200, ideas
    assert any(h in ideas for h in IDEAS_HEADINGS), ideas[:800]

    # The analysis is about the harness, the ideas about the project. Both
    # prompts draw that line hard; a note that crossed it is a prompt failure.
    assert analysis != ideas

    # --- the notes stayed out of the context window -----------------------
    assert analysis.strip()[:200] not in summary
    assert ideas.strip()[:200] not in summary

    await session.close()
    await new_session.close()
