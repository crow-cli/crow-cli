"""Slash commands through the real prompt dispatch (real sqlite persistence).

``/compact`` is the reason this module exists. The handlers live apart from the
agent and nothing exercised them, so they rotted against the agent's current
attributes — a per-session logger dict instead of ``_session_logger``, config
values keyed by wire session id instead of agent id — and a slash command that
raises turns into an ACP internal error rather than a result. These tests drive
``Agent.prompt`` with slash text so dispatch and handler are covered together.
"""

from types import SimpleNamespace

import pytest
import yaml
from acp.schema import TextContentBlock

from crow_cli.agent.compact import (
    ANALYSIS_PROMPT,
    COMPACTION_PROMPT,
    IDEAS_PROMPT,
    analysis_path,
    ideas_path,
)
from crow_cli.agent.main import AcpAgent
from crow_cli.agent.session import make_agent_session
from tests.integration.test_react_loop_cancel_integrity import SESSION_ID, FakeConn


# Which of compaction's three passes a request belongs to, read off the only
# thing that differs between them: the trailing user prompt.
_KINDS = {
    COMPACTION_PROMPT: "summary",
    ANALYSIS_PROMPT: "analysis",
    IDEAS_PROMPT: "ideas",
}


class SummarizerLLM:
    """The LLM boundary: streamed completions, one per compaction pass.

    ``compact()`` streams (a local model can take minutes for a whole summary,
    which unstreamed trips the client's read timeout); everything else in the
    compaction path — persistence, the new agent row, registry rebinding, the
    two reflection files — is the real thing.

    Each pass gets distinguishable text so a test can tell which file came from
    which prompt. ``fail_on`` names passes that should raise, which is how the
    "a reflection must not break a compaction" guarantee gets exercised through
    the real slash dispatch rather than against ``compact()`` directly.
    """

    BODIES = {
        "analysis": "## Bugs\nthe edit tool silently picked the wrong occurrence",
        "ideas": "## Prior art you should steal from\na real system, a real mechanism",
    }

    def __init__(
        self,
        summary: str = "## Summary\nthe conversation so far",
        fail_on: tuple[str, ...] = (),
    ):
        self.summary = summary
        self.fail_on = tuple(fail_on)
        self.create_kwargs: list[dict] = []
        self.kinds: list[str] = []
        outer = self

        class Completions:
            async def create(self, **kwargs):
                outer.create_kwargs.append(kwargs)
                kind = _KINDS[kwargs["messages"][-1]["content"]]
                outer.kinds.append(kind)
                if kind in outer.fail_on:
                    raise RuntimeError(f"the {kind} pass exploded")
                body = outer.summary if kind == "summary" else outer.BODIES[kind]
                if not kwargs.get("stream"):
                    return SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                message=SimpleNamespace(content=body)
                            )
                        ],
                        usage=SimpleNamespace(
                            prompt_tokens=10, completion_tokens=5, total_tokens=15
                        ),
                    )

                async def gen():
                    yield SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(content=body)
                            )
                        ],
                        usage=None,
                    )
                    yield SimpleNamespace(
                        choices=[],
                        usage=SimpleNamespace(
                            prompt_tokens=10, completion_tokens=5, total_tokens=15
                        ),
                    )

                return gen()

        self.chat = SimpleNamespace(completions=Completions())


def front_matter(path) -> tuple[dict, str]:
    """Split a reflection file into its crow-written frontmatter and the model's
    body. The header is YAML on purpose: a note is only useful if something
    other than a human can join it back to the session that produced it."""
    text = path.read_text()
    assert text.startswith("---\n"), f"{path} has no frontmatter"
    head, body = text[len("---\n") :].split("\n---\n\n", 1)
    return yaml.safe_load(head), body


def sent_text(conn: FakeConn) -> str:
    """All agent message text the fake client received.

    ``update_agent_message`` wraps one block per update; a list is handled too so
    this does not silently drop text if that ever changes.
    """
    chunks = []
    for update in conn.updates:
        content = getattr(update, "content", None)
        for block in content if isinstance(content, list) else [content] if content else []:
            chunks.append(getattr(block, "text", "") or "")
    return "\n".join(chunks)


@pytest.fixture
async def agent_with_history(test_config, tmp_path):
    """A live session with a few turns, wired into an agent the way a real
    connection would have it (tools provisioned, model resolved).

    ``cwd`` is a subdirectory of ``tmp_path``, not ``tmp_path`` itself: the test
    config dir is ``tmp_path/.agents/crow``, so a session rooted at ``tmp_path``
    would be the degenerate "crow launched from $HOME" case where the project
    scope and the global scope are one directory (covered separately in
    tests/unit/test_compact.py).
    """
    config = test_config
    config.db_uri = f"sqlite:///{tmp_path / 'crow.db'}"
    project = tmp_path / "project"
    project.mkdir()
    session = await make_agent_session(
        config,
        tools=[],
        model_id="test-model-id",
        cwd=str(project),
        session_id=SESSION_ID,
    )
    for message in (
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
        {"role": "user", "content": "third"},
    ):
        await session.add_message(message)

    agent = AcpAgent(config=config, hooks=[])
    agent._conn = FakeConn()
    agent._sessions[session.agent_id] = session
    agent._tools[session.session_id] = []
    agent._config_values[session.session_id] = {"model": "test-provider:test-model-id"}
    return agent, session


async def test_compact_slash_command_creates_a_new_generation(agent_with_history, monkeypatch):
    """/compact must summarize through the LLM and hand back a compacted session."""
    agent, session = agent_with_history
    llm = SummarizerLLM()
    monkeypatch.setattr("crow_cli.agent.slash.configure_llm", lambda **kwargs: llm)

    response = await agent.prompt([TextContentBlock(type="text", text="/compact")], session_id=SESSION_ID)

    assert response.stop_reason == "end_turn"
    assert llm.create_kwargs, "the compaction prompt never reached the LLM"
    assert "compact" in sent_text(agent._conn).lower()


async def test_compact_slash_command_rebinds_the_live_session(agent_with_history, monkeypatch):
    """After /compact the next resolution returns the new generation, not the old.

    Compaction mints a new agent row inside the same wire sessionId; the agent's
    cache has to hold it or the following prompt replays the uncompressed history.
    """
    agent, session = agent_with_history
    monkeypatch.setattr(
        "crow_cli.agent.slash.configure_llm", lambda **kwargs: SummarizerLLM()
    )

    await agent.prompt([TextContentBlock(type="text", text="/compact")], session_id=SESSION_ID)

    compacted = await agent._resolve_session(SESSION_ID)
    assert compacted.agent_idx == session.agent_idx + 1
    assert len(compacted.messages) < len(session.messages)


async def test_compact_with_too_little_history_says_so(agent_with_history, monkeypatch):
    """No LLM call and a human-readable refusal when there is nothing to compact."""
    agent, session = agent_with_history
    session.messages = [session.messages[0]] if session.messages else []
    called = []
    monkeypatch.setattr(
        "crow_cli.agent.slash.configure_llm",
        lambda **kwargs: called.append(1) or SummarizerLLM(),
    )

    await agent.prompt([TextContentBlock(type="text", text="/compact")], session_id=SESSION_ID)

    assert not called
    assert "not enough conversation history" in sent_text(agent._conn).lower()


async def test_compact_slash_command_writes_the_analysis_and_the_ideas(
    agent_with_history, monkeypatch
):
    """/compact leaves two notes behind: a harness analysis under the config dir
    and project ideas under the working tree, both named for the generation that
    was compacted.

    The unit tests drive ``compact()`` directly. This drives the real slash
    dispatch through ``Agent.prompt`` against real sqlite persistence, so it
    covers the path a user actually takes — and the session shape that path
    produces, which is a system prompt full of skills/tree/AGENTS.md blocks and
    messages rehydrated from the db, not a synthetic list.
    """
    agent, session = agent_with_history
    llm = SummarizerLLM()
    monkeypatch.setattr("crow_cli.agent.slash.configure_llm", lambda **kwargs: llm)

    response = await agent.prompt(
        [TextContentBlock(type="text", text="/compact")], session_id=SESSION_ID
    )

    assert response.stop_reason == "end_turn"
    assert llm.kinds == ["summary", "analysis", "ideas"]

    analysis = analysis_path(agent._config.config_dir, session.agent_id)
    ideas = ideas_path(session.cwd, session.agent_id)

    meta, body = front_matter(analysis)
    assert meta["kind"] == "analysis"
    assert meta["agent"] == session.agent_id
    assert meta["session"] == session.session_id
    assert "generated" in meta
    assert body.startswith("## Bugs")

    meta, body = front_matter(ideas)
    assert meta["kind"] == "ideas"
    assert meta["agent"] == session.agent_id
    assert meta["cwd"] == session.cwd
    assert body.startswith("## Prior art")


async def test_all_three_passes_share_one_message_prefix(
    agent_with_history, monkeypatch
):
    """Compaction asks three questions of one conversation and should pay for
    the history once: every pass sends a byte-identical prefix and only the
    trailing prompt differs, which is what makes the provider's prompt-prefix
    cache hit on passes two and three.

    Worth asserting against a real session, not just a synthetic one — the
    prefix here includes a rendered system prompt and db-round-tripped message
    dicts, so anything non-deterministic in either would show up as a cache miss
    in production and as a failure here.
    """
    agent, session = agent_with_history
    llm = SummarizerLLM()
    monkeypatch.setattr("crow_cli.agent.slash.configure_llm", lambda **kwargs: llm)

    await agent.prompt(
        [TextContentBlock(type="text", text="/compact")], session_id=SESSION_ID
    )

    assert len(llm.create_kwargs) == 3
    assert [k["messages"][-1]["content"] for k in llm.create_kwargs] == [
        COMPACTION_PROMPT,
        ANALYSIS_PROMPT,
        IDEAS_PROMPT,
    ]
    prefixes = [k["messages"][:-1] for k in llm.create_kwargs]
    assert prefixes[0] == prefixes[1] == prefixes[2]
    assert prefixes[0][0]["role"] == "system"


async def test_a_failed_reflection_still_compacts(agent_with_history, monkeypatch):
    """The reflections run after the summary is durable, and each fails alone.

    A provider that chokes on the analysis prompt must not turn a successful
    /compact into an error the user has to recover from — the summary is already
    in the database and the new generation is already live by then.
    """
    agent, session = agent_with_history
    llm = SummarizerLLM(fail_on=("analysis",))
    monkeypatch.setattr("crow_cli.agent.slash.configure_llm", lambda **kwargs: llm)

    response = await agent.prompt(
        [TextContentBlock(type="text", text="/compact")], session_id=SESSION_ID
    )

    assert response.stop_reason == "end_turn"
    assert "error during compaction" not in sent_text(agent._conn).lower()

    compacted = await agent._resolve_session(SESSION_ID)
    assert compacted.agent_idx == session.agent_idx + 1
    assert "the conversation so far" in compacted.messages[1]["content"]

    # The analysis is missing; the ideas pass is independent and still ran.
    assert not analysis_path(agent._config.config_dir, session.agent_id).exists()
    assert ideas_path(session.cwd, session.agent_id).exists()


async def test_reflections_never_leak_into_the_compacted_history(
    agent_with_history, monkeypatch
):
    """The next generation inherits the summary, not its predecessor's
    self-criticism. The notes are files on disk precisely so they stay out of
    the context window."""
    agent, session = agent_with_history
    llm = SummarizerLLM()
    monkeypatch.setattr("crow_cli.agent.slash.configure_llm", lambda **kwargs: llm)

    await agent.prompt(
        [TextContentBlock(type="text", text="/compact")], session_id=SESSION_ID
    )

    compacted = await agent._resolve_session(SESSION_ID)
    joined = "\n".join(str(m.get("content", "")) for m in compacted.messages)
    assert SummarizerLLM.BODIES["analysis"] not in joined
    assert SummarizerLLM.BODIES["ideas"] not in joined


async def test_unknown_command_is_reported(agent_with_history):
    await agent_with_history[0].prompt(
        [TextContentBlock(type="text", text="/nope")], session_id=SESSION_ID
    )
    assert "Unknown command: /nope" in sent_text(agent_with_history[0]._conn)


async def test_help_lists_registered_commands(agent_with_history):
    await agent_with_history[0].prompt(
        [TextContentBlock(type="text", text="/help")], session_id=SESSION_ID
    )
    text = sent_text(agent_with_history[0]._conn)
    assert "/compact" in text
    assert "/stop" in text
