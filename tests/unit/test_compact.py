"""Unit tests for compaction (no live LLM, no live service).

The summarization LLM call is mocked, and persistence is faked via the
``memory_service`` fixture (an in-memory stand-in for the sqlite MemoryClient).

``compact()`` (crow_cli.agent.compact) is async and takes a ``Config``. It
summarizes the conversation into a NEW agent record (``agent_idx + 1``) whose
history is ``[system, user(summary + last_messages)]``, and leaves the
ORIGINAL session untouched. The ``on_compact`` callback receives the original
``agent_id`` and the new session.

Compaction is a CALLABLE. ``compact()`` builds a ``CompactCtx``, hands it to
``compactor`` (default ``default_compactor``: one summary call over the real
history), and then does every bit of new-session mechanics itself — next
``agent_idx`` inside the same wire session, the agent row, the handoff message,
``on_compact``. The callable returns a ``CompactResponse``: the successor's
system template, its template args, and the prompt that opens it. Nothing here
writes reflection notes any more; a project that wants that pass supplies its
own compactor (see ``examples/custom_compactor.py``).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from crow_cli.agent.compact import (
    COMPACTION_PROMPT,
    CompactResponse,
    compact,
    default_compactor,
)
from crow_cli.agent.prompt import SystemPromptResponse
from crow_cli.config import Config, LLModel
from crow_cli.agent.session import AgentSession, lookup_or_create_prompt
from crow_cli.memory import build_agent_id


def _content_chunk(text):
    """A streamed chunk carrying one content delta (final chunks have none)."""
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=text))], usage=None
    )


def _usage_chunk(prompt_tokens=100, completion_tokens=50, total_tokens=150):
    """The closing chunk: no choices, usage only."""
    return SimpleNamespace(
        choices=[],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        ),
    )


def _stream(chunks):
    """An async iterator over ``chunks``, like the openai SDK's stream object."""

    async def gen():
        for chunk in chunks:
            yield chunk

    return gen()


# What the summary call "returns" — fragmented, so a test can prove the deltas
# were reassembled. Keyed on the trailing prompt the way the provider sees it,
# which is also how a custom compactor's own question gets its own answer.
_BODIES = {
    COMPACTION_PROMPT: ["COMPACTED ", "SUMMARY"],
}


def _fake_stream(messages):
    """A fresh stream for one call, keyed on that call's trailing prompt.

    A fresh generator per call matters: an async generator is consumed once, so
    a single ``return_value`` would leave a second call reading an exhausted
    iterator and silently produce nothing.
    """
    body = _BODIES[messages[-1]["content"]]
    return _stream([_content_chunk(t) for t in body] + [_usage_chunk()])


def _summary_call(mock_llm):
    """The first LLM call — the summary. ``call_args`` is the LAST one, and a
    custom compactor is free to have made more than one."""
    return mock_llm.chat.completions.create.call_args_list[0]


# Module-level so both test classes below share one set of fakes.
@pytest.fixture
def compact_config(memory_service, tmp_path):
    """Real config, with persistence AND the config dir redirected so a unit
    test never leaves anything in the developer's ``~/.agents/crow``."""
    config = Config.load()
    # Inline template so make_agent_session doesn't read a prompt file.
    config.system_prompt = "You are {{name}}. Workspace: {{workspace}}."
    config.config_dir = tmp_path / "crow"
    return config


@pytest.fixture
async def setup_session(memory_service, sample_prompt_template, tmp_path):
    """A 1-positioned session with a long conversation, rooted at a tmp project
    dir (created because ``make_agent_session`` walks it to build the tree)."""
    project = tmp_path / "project"
    project.mkdir()
    prompt_id = await lookup_or_create_prompt(sample_prompt_template, name="test-prompt")
    session = await AgentSession.create(
        prompt_id=prompt_id,
        prompt_args={"name": "Crow", "workspace": "/tmp", "display_tree": "test/"},
        tool_definitions=[],
        request_params={"temperature": 0.7},
        model_identifier="test-model",
        cwd=str(project),
        agent_idx=1,
    )
    for i in range(20):
        await session.add_message({"role": "user", "content": f"User message {i}"})
        await session.add_message(
            {"role": "assistant", "content": f"Assistant response {i}"}
        )
    return session


@pytest.fixture
def mock_llm():
    """Mock LLM that STREAMS a fixed answer per call, split across chunks.

    Compaction must stream (see test_compact_streams_so_slow_models_do_not_time_out),
    so the fake returns an async iterator of chat-completion chunks rather than
    a single response object. Each body is deliberately fragmented to prove the
    pieces are reassembled.
    """
    llm = AsyncMock()
    llm.chat.completions.create = AsyncMock(
        side_effect=lambda **kwargs: _fake_stream(kwargs["messages"])
    )
    return llm


class TestCompaction:
    """Test the new-agent-record compaction contract without live LLM calls."""

    @pytest.mark.asyncio
    async def test_compact_streams_so_slow_models_do_not_time_out(
        self, setup_session, mock_llm, compact_config
    ):
        """Regression: compaction used a non-streaming request, so a local model
        that takes minutes to produce the whole summary hit the client's read
        timeout (openai.APITimeoutError) and compaction died. Streaming only has
        to emit *a* chunk within the timeout window."""
        session = setup_session
        result = await compact(session, mock_llm, compact_config, logger=MagicMock())

        kwargs = _summary_call(mock_llm).kwargs
        assert kwargs["stream"] is True
        assert kwargs["stream_options"] == {"include_usage": True}

        # The fragmented deltas were accumulated into one summary, and usage
        # came off the closing usage-only chunk.
        assert "COMPACTED SUMMARY" in result.messages[1]["content"]

    @pytest.mark.asyncio
    async def test_compact_calls_llm_with_tool_choice_none(
        self, setup_session, mock_llm, compact_config
    ):
        """Compaction summarizes via a non-tool-calling request."""
        session = setup_session
        await compact(session, mock_llm, compact_config, logger=MagicMock())

        kwargs = _summary_call(mock_llm).kwargs
        assert kwargs["tool_choice"] == "none"
        assert kwargs["model"] == "test-model"

    @pytest.mark.asyncio
    async def test_compact_uses_model_temperature_not_session_params(
        self, setup_session, mock_llm, compact_config
    ):
        """Compaction samples with the model's per-model temperature — NOT
        the session's request_params (0.7 here) and NOT the provider default
        of 1.0, which makes the model ramble instead of compress."""
        compact_config.llm.models["test-model"] = LLModel(
            name="test-model",
            provider_name="test-provider",
            model_id="test-model",
            temperature=0.4,
        )
        await compact(setup_session, mock_llm, compact_config, logger=MagicMock())

        kwargs = _summary_call(mock_llm).kwargs
        assert kwargs["temperature"] == 0.4
        assert "reasoning_effort" not in kwargs

    @pytest.mark.asyncio
    async def test_compact_uses_reasoning_effort_instead_of_temperature(
        self, setup_session, mock_llm, compact_config
    ):
        """Reasoning models reject temperature — compaction must swap too."""
        compact_config.llm.models["test-model"] = LLModel(
            name="test-model",
            provider_name="test-provider",
            model_id="test-model",
            reasoning_effort="high",
        )
        await compact(setup_session, mock_llm, compact_config, logger=MagicMock())

        kwargs = _summary_call(mock_llm).kwargs
        assert kwargs["reasoning_effort"] == "high"
        assert "temperature" not in kwargs

    @pytest.mark.asyncio
    async def test_compact_creates_new_agent_record(
        self, setup_session, mock_llm, compact_config
    ):
        """Compaction creates a NEW agent record at agent_idx + 1."""
        session = setup_session
        result = await compact(session, mock_llm, compact_config, logger=MagicMock())

        assert result.agent_idx == session.agent_idx + 1
        # schema v5: three-part id, compaction stays on the same fork
        assert result.fork_idx == session.fork_idx
        assert result.agent_id == build_agent_id(
            session.session_id, session.agent_idx + 1, session.fork_idx
        )
        assert result.agent_id != session.agent_id

        # The new record is persisted and loadable.
        reloaded = await AgentSession.load(result.agent_id)
        assert reloaded.agent_id == result.agent_id

    @pytest.mark.asyncio
    async def test_compact_new_session_is_summarized(
        self, setup_session, mock_llm, compact_config
    ):
        """The new session's history is [system, user(summary + last messages)]."""
        session = setup_session
        result = await compact(session, mock_llm, compact_config, logger=MagicMock())

        assert len(result.messages) == 2
        assert result.messages[0]["role"] == "system"
        assert result.messages[1]["role"] == "user"
        assert "COMPACTED SUMMARY" in result.messages[1]["content"]

    @pytest.mark.asyncio
    async def test_compact_preserves_original_session(
        self, setup_session, mock_llm, compact_config
    ):
        """The original session is left completely untouched."""
        session = setup_session
        original_count = len(session.messages)
        original_agent_id = session.agent_id

        await compact(session, mock_llm, compact_config, logger=MagicMock())

        # In-memory object unchanged.
        assert len(session.messages) == original_count
        # Persisted original record unchanged.
        reloaded = await AgentSession.load(original_agent_id)
        assert len(reloaded.messages) == original_count

    @pytest.mark.asyncio
    async def test_compact_on_compact_callback(
        self, setup_session, mock_llm, compact_config
    ):
        """on_compact receives the original agent_id and the new session."""
        session = setup_session
        calls = []

        def on_compact(old_agent_id, new_session):
            calls.append((old_agent_id, new_session))

        result = await compact(
            session, mock_llm, compact_config, on_compact=on_compact, logger=MagicMock()
        )

        assert len(calls) == 1
        old_agent_id, new_session = calls[0]
        assert old_agent_id == session.agent_id  # agent_id, not session_id
        assert new_session is result

    @pytest.mark.asyncio
    async def test_compact_preserves_tools_and_model(
        self, setup_session, mock_llm, compact_config
    ):
        """Tools and model identifier carry over to the new session."""
        session = setup_session
        session.tools = [{"name": "read_file", "description": "Read a file"}]

        result = await compact(session, mock_llm, compact_config, logger=MagicMock())

        assert result.tools == session.tools
        assert result.model_identifier == session.model_identifier


class TestCompactionContract:
    """Compaction and system-prompt creation are ONE contract.

    The compactor is handed a ``CompactCtx`` that carries the system-prompt
    callable, and returns a ``CompactResponse`` describing the successor. It
    never mints a session: ``compact()`` owns the agent_idx arithmetic, the
    row, the handoff message and ``on_compact``, so a project's strategy cannot
    get the mechanics wrong and does not have to know them.
    """

    @pytest.mark.asyncio
    async def test_the_default_path_makes_exactly_one_llm_call(
        self, setup_session, mock_llm, compact_config
    ):
        """The two reflection passes are gone. Compaction costs one summary."""
        await compact(setup_session, mock_llm, compact_config, logger=MagicMock())
        assert mock_llm.chat.completions.create.call_count == 1

    @pytest.mark.asyncio
    async def test_the_ctx_carries_everything_a_strategy_needs(
        self, setup_session, mock_llm, compact_config
    ):
        """Session, client, config, logger — and the coupled system-prompt
        callable, which by default produces crow's own prompt."""
        seen = {}

        async def spy(ctx):
            seen["ctx"] = ctx
            return await default_compactor(ctx)

        await compact(
            setup_session, mock_llm, compact_config,
            logger=MagicMock(), compactor=spy,
        )

        ctx = seen["ctx"]
        assert ctx.session is setup_session
        assert ctx.llm_client is mock_llm
        assert ctx.config is compact_config
        assert ctx.logger is not None
        default = ctx.system_prompt(ctx)
        assert default.template
        # Load-bearing: the session list is filtered on this arg.
        assert default.template_args["workspace"] == setup_session.cwd

    @pytest.mark.asyncio
    async def test_a_custom_compactor_replaces_the_summary_entirely(
        self, setup_session, mock_llm, compact_config
    ):
        """A strategy that never calls the model is a legal strategy: whatever
        it returns IS the next generation."""
        template = "Generation {{ generation }} of {{ workspace }}."
        args = {"generation": 2, "workspace": setup_session.cwd}

        async def no_llm(ctx):
            return CompactResponse(
                system_template=template,
                system_args=args,
                prompt="HANDOFF: pick up where the last generation stopped.",
            )

        result = await compact(
            setup_session, mock_llm, compact_config,
            logger=MagicMock(), compactor=no_llm,
        )

        assert mock_llm.chat.completions.create.call_count == 0
        assert [m["role"] for m in result.messages] == ["system", "user"]
        assert result.messages[0]["content"] == f"Generation 2 of {setup_session.cwd}."
        assert result.messages[1]["content"].startswith("HANDOFF:")
        assert result.prompt_args == args

    @pytest.mark.asyncio
    async def test_a_custom_compactor_can_reuse_the_default_summary(
        self, setup_session, mock_llm, compact_config
    ):
        """The default strategy is a building block, not a take-it-or-leave-it:
        a project keeps the summary and adds its own scaffolding around it."""

        async def wrapped(ctx):
            base = await default_compactor(ctx)
            return CompactResponse(
                system_template=base.system_template,
                system_args=base.system_args,
                prompt=f"PROJECT RULES FIRST.\n\n{base.prompt}",
            )

        result = await compact(
            setup_session, mock_llm, compact_config,
            logger=MagicMock(), compactor=wrapped,
        )

        assert mock_llm.chat.completions.create.call_count == 1
        handoff = result.messages[1]["content"]
        assert handoff.startswith("PROJECT RULES FIRST.")
        assert "COMPACTED SUMMARY" in handoff

    @pytest.mark.asyncio
    async def test_the_system_prompt_callable_can_be_replaced_on_its_own(
        self, setup_session, mock_llm, compact_config
    ):
        """Keep the default summary, replace only the successor's prompt — the
        two halves of the contract are separately swappable."""
        old_prompt_id = setup_session.prompt_id

        def sys_prompt(ctx):
            return SystemPromptResponse(
                template="You are generation {{ generation }}. Workspace: {{ workspace }}.",
                template_args={
                    "generation": ctx.session.agent_idx + 1,
                    "workspace": ctx.session.cwd,
                },
            )

        result = await compact(
            setup_session, mock_llm, compact_config,
            logger=MagicMock(), system_prompt=sys_prompt,
        )

        assert "COMPACTED SUMMARY" in result.messages[1]["content"]
        assert result.messages[0]["content"] == (
            f"You are generation 2. Workspace: {setup_session.cwd}."
        )
        # A different template is a different prompts row; the source
        # generation's prompt is untouched.
        assert result.prompt_id != old_prompt_id
        assert setup_session.prompt_id == old_prompt_id

    @pytest.mark.asyncio
    async def test_the_callable_never_has_to_spell_an_agent_id(
        self, setup_session, mock_llm, compact_config
    ):
        """The mechanics are the harness's. A CompactResponse carries no
        session id, no agent index, no fork index — and the successor still
        lands in the right place, with on_compact told about it."""
        handed_off = []

        async def no_ids(ctx):
            return CompactResponse(
                system_template="Successor.",
                system_args={},
                prompt="carry on",
            )

        result = await compact(
            setup_session, mock_llm, compact_config,
            on_compact=lambda old, new: handed_off.append((old, new)),
            logger=MagicMock(), compactor=no_ids,
        )

        assert handed_off == [(setup_session.agent_id, result)]
        assert result.session_id == setup_session.session_id
        assert result.fork_idx == setup_session.fork_idx
        assert result.agent_idx == setup_session.agent_idx + 1
        assert result.agent_id == build_agent_id(
            setup_session.session_id, setup_session.agent_idx + 1, setup_session.fork_idx
        )
        # And the generation it replaced is untouched: still 1, still holding
        # its own full history (system + the 40 scripted messages).
        assert setup_session.agent_idx == 1
        reloaded = await AgentSession.load(setup_session.agent_id)
        assert len(reloaded.messages) == 41
