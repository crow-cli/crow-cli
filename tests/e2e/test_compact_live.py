"""Live compaction on the DEFAULT path (end-to-end, real provider, real sqlite).

Compaction is a callable now and a project can replace it — that is what
``test_custom_compactor_live.py`` drives over ACP with its own agent script.
This is the other half of the same claim: with nothing passed in, ``compact()``
still does what crow-cli always did — crow's own system prompt, one summary,
the harness owning every bit of new-session arithmetic — and it no longer
spends two extra live calls writing reflection notes nobody asked for.

The history below is scripted rather than earned by running real turns: it is
the conversation content the summary reads, and paying for react turns to
generate it would multiply the cost of a test whose subject is the compaction
call itself. It is shaped like a real crow-cli session (a rename, a search, an
``edit`` the tool refused for being ambiguous, a retry, a test run) so the
summary has something concrete to lose or keep.

Asserts are loose where the output is nondeterministic and strict where the
contract is not.
"""

import logging

import pytest

from crow_cli.agent.compact import compact
from crow_cli.agent.prompt import default_system_prompt, render_template
from crow_cli.agent.session import make_agent_session
from crow_cli.config import Config
from crow_cli.memory import build_agent_id, get_engine, get_prompt

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


@pytest.mark.asyncio
async def test_live_default_compact_mints_the_next_generation(tmp_path):
    """One real compaction with nothing passed in: the default strategy, crow's
    default system prompt, and the harness doing every bit of the arithmetic."""
    client, model_id = get_llm_client()
    if client is None:
        pytest.skip("No LLM provider configured")

    config = Config.load()
    # Never touch the real db — and hand the reflection passes a config_dir
    # they would have to create in order to be caught writing into it.
    config.db_uri = f"sqlite:///{tmp_path / 'e2e.db'}"
    config.config_dir = tmp_path / "crow"
    project = tmp_path / "project"
    project.mkdir()

    session = await make_agent_session(
        config, tools=[], model_id=model_id, cwd=str(project)
    )
    for message in HISTORY:
        await session.add_message(message)

    handed_off: list[tuple[str, str]] = []

    def on_compact(old_agent_id: str, compacted) -> None:
        handed_off.append((old_agent_id, compacted.agent_id))

    new_session = await compact(
        session, client, config, on_compact=on_compact, logger=logger
    )

    # --- the harness did the arithmetic; the caller did none of it ---------
    assert handed_off == [(session.agent_id, new_session.agent_id)]
    assert new_session.agent_idx == session.agent_idx + 1
    assert new_session.session_id == session.session_id
    assert new_session.fork_idx == session.fork_idx
    assert new_session.agent_id == build_agent_id(
        session.session_id, session.agent_idx + 1, session.fork_idx
    )

    # --- one summary message, and a real one ------------------------------
    assert [m["role"] for m in new_session.messages] == ["system", "user"]
    handoff = str(new_session.messages[1]["content"])
    assert "ancestors" in handoff, f"summary lost the subject: {handoff[:400]}"
    assert "Last messages:" in handoff
    assert len(handoff.strip()) > 400, handoff

    # --- crow's OWN prompt: same template row, same args, re-rendered -------
    default = default_system_prompt(config, str(project), session.session_id)
    assert new_session.prompt_id == session.prompt_id
    engine = get_engine(config.db_uri)
    assert get_prompt(engine, new_session.prompt_id).template == default.template
    assert new_session.prompt_args == default.template_args
    system = str(new_session.messages[0]["content"])
    assert system == render_template(default.template, **default.template_args)
    # workspace survived, which is what keeps the session in the session list
    assert str(project) in system

    # --- and the two reflection passes are really gone --------------------
    assert not (config.config_dir / "analysis").exists()
    assert not (project / ".agents").exists()

    await session.close()
    await new_session.close()
