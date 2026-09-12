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
from acp.schema import TextContentBlock

from crow_cli.agent.compact import COMPACTION_PROMPT, CompactResponse
from crow_cli.agent.main import AcpAgent
from crow_cli.agent.prompt import SystemPromptResponse
from crow_cli.agent.session import make_agent_session
from tests.integration.test_react_loop_cancel_integrity import SESSION_ID, FakeConn


# Which compaction pass a request belongs to, read off the trailing user prompt.
# One entry, because the default strategy asks exactly one question. A prompt
# that is not in here is a KeyError on purpose: it means something other than
# the default compactor ran, and a test that did not arrange that.
_KINDS = {COMPACTION_PROMPT: "summary"}


class SummarizerLLM:
    """The LLM boundary: a streamed completion for the summary call.

    ``compact()`` streams (a local model can take minutes for a whole summary,
    which unstreamed trips the client's read timeout); everything else in the
    compaction path — persistence, the new agent row, registry rebinding — is
    the real thing.

    ``fail_on`` names passes that should raise, which is how "a slash handler
    must not raise" gets exercised through the real dispatch rather than
    against ``compact()`` directly.
    """

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
                body = outer.summary
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
    would be the degenerate "crow launched from $HOME" case, where walking up
    from the workspace finds the config dir's own AGENTS.md.
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


async def test_compact_makes_one_call_over_the_real_history(
    agent_with_history, monkeypatch
):
    """/compact asks the model ONE question — the summary — over the session's
    real history: a rendered system prompt and messages rehydrated from sqlite,
    not a synthetic list.

    The unit tests drive ``compact()`` directly. This drives the real slash
    dispatch through ``Agent.prompt``, so it covers the path a user takes.
    """
    agent, session = agent_with_history
    llm = SummarizerLLM()
    monkeypatch.setattr("crow_cli.agent.slash.configure_llm", lambda **kwargs: llm)

    response = await agent.prompt(
        [TextContentBlock(type="text", text="/compact")], session_id=SESSION_ID
    )

    assert response.stop_reason == "end_turn"
    assert llm.kinds == ["summary"]
    call = llm.create_kwargs[0]
    assert call["stream"] is True
    assert call["tool_choice"] == "none"
    assert call["messages"][-1]["content"] == COMPACTION_PROMPT
    # The prefix IS the session's own history, system prompt first, verbatim.
    prefix = call["messages"][:-1]
    assert prefix[0]["role"] == "system"
    assert prefix[0]["content"] == session.messages[0]["content"]
    assert prefix[: len(session.messages)] == session.messages
    # /compact leaves a trailing user message and providers reject user+user,
    # so history_prefix pads it with an assistant placeholder.
    assert prefix[-1]["role"] == "assistant"
    assert len(prefix) == len(session.messages) + 1


async def test_a_failed_summary_is_reported_not_raised(agent_with_history, monkeypatch):
    """A slash handler must not raise: an exception becomes an ACP internal
    error, which the client reads as a failed turn. A provider that chokes on
    the summary is reported as a result instead, and no generation is minted."""
    agent, session = agent_with_history
    llm = SummarizerLLM(fail_on=("summary",))
    monkeypatch.setattr("crow_cli.agent.slash.configure_llm", lambda **kwargs: llm)

    response = await agent.prompt(
        [TextContentBlock(type="text", text="/compact")], session_id=SESSION_ID
    )

    assert response.stop_reason == "end_turn"
    assert "error during compaction" in sent_text(agent._conn).lower()
    assert (await agent._resolve_session(SESSION_ID)).agent_id == session.agent_id


async def test_compact_routes_through_the_agents_own_callables(
    agent_with_history, monkeypatch
):
    """``/compact`` runs the AGENT'S compactor and system-prompt callables — the
    slash path and the react-threshold path share one contract, so a project's
    strategy reaches both.

    The custom compactor here never touches the model. If the handler had fallen
    back to the default there would be a summary call in ``create_kwargs`` and
    crow's own prompt on the successor.
    """
    agent, session = agent_with_history
    llm = SummarizerLLM()
    monkeypatch.setattr("crow_cli.agent.slash.configure_llm", lambda **kwargs: llm)

    seen = {}

    async def project_compactor(ctx):
        seen["ctx"] = ctx
        system_prompt = ctx.system_prompt(ctx)
        return CompactResponse(
            system_template=system_prompt.template,
            system_args=system_prompt.template_args,
            prompt=f"PROJECT HANDOFF for generation {ctx.session.agent_idx + 1}",
        )

    def project_system_prompt(ctx):
        return SystemPromptResponse(
            template="Project agent, generation {{ generation }}.",
            template_args={"generation": ctx.session.agent_idx + 1},
        )

    agent._compactor = project_compactor
    agent._compact_system_prompt = project_system_prompt

    response = await agent.prompt(
        [TextContentBlock(type="text", text="/compact")], session_id=SESSION_ID
    )

    assert response.stop_reason == "end_turn"
    assert llm.create_kwargs == []
    assert seen["ctx"].session.agent_id == session.agent_id
    assert seen["ctx"].llm_client is llm
    assert seen["ctx"].config is agent._config

    compacted = await agent._resolve_session(SESSION_ID)
    assert compacted.agent_idx == session.agent_idx + 1
    assert compacted.messages[0]["content"] == "Project agent, generation 2."
    assert compacted.messages[1]["content"] == "PROJECT HANDOFF for generation 2"
    assert "compacted" in sent_text(agent._conn).lower()


async def test_new_session_renders_the_agents_system_prompt_callable(
    test_config, tmp_path
):
    """The other half of the contract, at the moment it is used: ``session/new``
    renders whatever the agent's ``system_prompt`` callable returned, and mints
    the session id BEFORE calling it, because crow's own template tells the
    agent which session it is and a replacement has to be able to say the same.
    """
    config = test_config
    config.db_uri = f"sqlite:///{tmp_path / 'new-session.db'}"
    project = tmp_path / "project"
    project.mkdir()

    seen = {}

    def project_system_prompt(cfg, cwd, session_id=None):
        seen["call"] = (cfg, cwd, session_id)
        return SystemPromptResponse(
            template="Project agent in {{ workspace }}, session {{ session_id }}.",
            template_args={"workspace": cwd, "session_id": session_id},
        )

    agent = AcpAgent(config=config, hooks=[], system_prompt=project_system_prompt)
    agent._conn = FakeConn()
    response = await agent.new_session(cwd=str(project), mcp_servers=[])

    assert seen["call"] == (config, str(project), response.session_id)

    session = await agent._resolve_session(response.session_id)
    assert session.messages[0]["content"] == (
        f"Project agent in {project}, session {response.session_id}."
    )
    # workspace survived, which is what keeps this session in the session list
    assert session.prompt_args["workspace"] == str(project)


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
