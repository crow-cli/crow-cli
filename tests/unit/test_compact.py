"""Unit tests for compaction (no live LLM, no live service).

The summarization LLM call is mocked, and persistence is faked via the
``memory_service`` fixture (an in-memory stand-in for the sqlite MemoryClient).

``compact()`` (crow_cli.agent.compact) is async and takes a ``Config``. It
summarizes the conversation into a NEW agent record (``agent_idx + 1``) whose
history is ``[system, user(summary + last_messages)]``, and leaves the
ORIGINAL session untouched. The ``on_compact`` callback receives the original
``agent_id`` and the new session.

Compaction makes THREE LLM calls, not one: the summary, then a harness analysis
and a set of project ideas over the same history (``write_reflections``). The
``mock_llm`` fixture answers each prompt with distinguishable text so a test can
tell which pass produced what; ``_summary_call`` picks the first call back out of
``call_args_list`` for assertions that are about the summary specifically.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from crow_cli.agent.compact import (
    ANALYSIS_PROMPT,
    COMPACTION_PROMPT,
    DEGENERATE_RUN,
    IDEAS_PROMPT,
    analysis_path,
    compact,
    degenerate_repeat,
    ideas_path,
    write_reflections,
)
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


# What each pass "returns". Keyed on the trailing prompt so the fake can tell
# the three calls apart the way the real provider would.
_BODIES = {
    COMPACTION_PROMPT: ["COMPACTED ", "SUMMARY"],
    ANALYSIS_PROMPT: ["## What worked well\n", "ANALYSIS BODY"],
    IDEAS_PROMPT: ["## Prior art you should steal from\n", "IDEAS BODY"],
}


def _fake_stream(messages):
    """A fresh stream for one call, keyed on that call's trailing prompt.

    A fresh generator per call matters: an async generator is consumed once, so
    a single ``return_value`` would leave passes two and three reading an
    exhausted iterator and silently produce empty files.
    """
    body = _BODIES[messages[-1]["content"]]
    return _stream([_content_chunk(t) for t in body] + [_usage_chunk()])


def _summary_call(mock_llm):
    """The first LLM call — the summary. ``call_args`` is the LAST one."""
    return mock_llm.chat.completions.create.call_args_list[0]


class TestCompaction:
    """Test the new-agent-record compaction contract without live LLM calls."""

    @pytest.fixture
    def compact_config(self, memory_service, tmp_path):
        """Real config; persistence AND the config dir are redirected.

        ``config_dir`` has to move: the harness analysis is written to
        ``<config_dir>/analysis/``, and a unit test must not leave files in the
        developer's real ``~/.agents/crow``.
        """
        config = Config.load()
        # Inline template so make_agent_session doesn't read a prompt file.
        config.system_prompt = "You are {{name}}. Workspace: {{workspace}}."
        config.config_dir = tmp_path / "crow"
        return config

    @pytest.fixture
    async def setup_session(self, memory_service, sample_prompt_template, tmp_path):
        """Create a 1-positioned session with a long conversation.

        ``cwd`` is a tmp path for the same reason ``config_dir`` is: project
        ideas are written to ``<cwd>/.agents/crow/ideas/``. It is created
        because ``make_agent_session`` walks it to build the directory tree.
        """
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
    def mock_llm(self):
        """Mock LLM that STREAMS a fixed answer per pass, split across chunks.

        Compaction must stream (see test_compact_streams_so_slow_models_do_not_time_out),
        so the fake returns an async iterator of chat-completion chunks rather
        than a single response object. Each body is deliberately fragmented to
        prove the pieces are reassembled.
        """
        llm = AsyncMock()
        llm.chat.completions.create = AsyncMock(
            side_effect=lambda **kwargs: _fake_stream(kwargs["messages"])
        )
        return llm

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

    # ---------------------------------------------------------------------
    # The two extra passes: harness analysis (global) + project ideas (local).
    # ---------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_compact_runs_three_passes_over_an_identical_prefix(
        self, setup_session, mock_llm, compact_config
    ):
        """The kv-cache contract: all three passes send a byte-identical message
        prefix and differ only in the trailing user prompt.

        Prefix caching is provider-side, so "reuse the warm cache" means the
        bytes have to match, not that the passes have to share a Python list.
        Each pass rebuilds its own prefix from the session — which also means
        one pass cannot leak its prompt into the next.
        """
        session = setup_session
        await compact(session, mock_llm, compact_config, logger=MagicMock())

        calls = mock_llm.chat.completions.create.call_args_list
        assert len(calls) == 3
        assert [c.kwargs["messages"][-1]["content"] for c in calls] == [
            COMPACTION_PROMPT,
            ANALYSIS_PROMPT,
            IDEAS_PROMPT,
        ]

        prefixes = [c.kwargs["messages"][:-1] for c in calls]
        assert prefixes[0] == prefixes[1] == prefixes[2]
        assert prefixes[0][0]["role"] == "system"
        # Fresh list per pass, not one shared list appended to three times.
        assert calls[0].kwargs["messages"] is not calls[1].kwargs["messages"]

        # Every pass is a non-tool-calling streamed request to the same model.
        for call in calls:
            assert call.kwargs["tool_choice"] == "none"
            assert call.kwargs["stream"] is True
            assert call.kwargs["model"] == "test-model"

        # And the session's own history was never mutated to build them.
        assert len(session.messages) == 41  # system + 20 user/assistant pairs
        assert all(COMPACTION_PROMPT not in str(m) for m in session.messages)

    @pytest.mark.asyncio
    async def test_compact_writes_analysis_globally_and_ideas_into_the_project(
        self, setup_session, mock_llm, compact_config
    ):
        """Analysis -> <config_dir>/analysis/<agent-id>.md (it is about crow-cli, so
        it has to outlive the repo). Ideas -> <cwd>/.agents/crow/ideas/<agent-id>.md
        (they are about this repo, so they belong in its tree).

        Both are named for the generation being COMPACTED — that is the history
        they read, and the id a reader joins them back to.
        """
        session = setup_session
        await compact(session, mock_llm, compact_config, logger=MagicMock())

        analysis = analysis_path(compact_config.config_dir, session.agent_id)
        ideas = ideas_path(session.cwd, session.agent_id)
        assert analysis == compact_config.config_dir / "analysis" / f"{session.agent_id}.md"
        assert ideas.read_text().endswith("IDEAS BODY\n")
        assert "ANALYSIS BODY" in analysis.read_text()
        assert "IDEAS BODY" not in analysis.read_text()
        assert "ANALYSIS BODY" not in ideas.read_text()

    @pytest.mark.asyncio
    async def test_reflection_files_carry_provenance_written_by_code(
        self, setup_session, mock_llm, compact_config
    ):
        """The frontmatter is written by crow, not asked of the model — a block
        the model has to reproduce is a block the model gets subtly wrong."""
        session = setup_session
        await compact(session, mock_llm, compact_config, logger=MagicMock())

        text = analysis_path(compact_config.config_dir, session.agent_id).read_text()
        head, body = text.split("---\n\n", 1)
        for expected in (
            "kind: analysis",
            f"session: {session.session_id}",
            f"agent: {session.agent_id}",
            "model: test-model",
            f"cwd: {session.cwd}",
            "generated: ",
        ):
            assert expected in head
        assert body.startswith("## What worked well")

        ideas = ideas_path(session.cwd, session.agent_id).read_text()
        assert "kind: ideas" in ideas.split("---\n\n", 1)[0]

    @pytest.mark.asyncio
    async def test_reflections_never_enter_the_new_session(
        self, setup_session, mock_llm, compact_config
    ):
        """The new agent's history is still exactly [system, summary]. The
        analysis and the ideas are files, not context — the next generation
        does not inherit its predecessor's self-criticism."""
        session = setup_session
        result = await compact(session, mock_llm, compact_config, logger=MagicMock())

        assert len(result.messages) == 2
        assert "ANALYSIS BODY" not in result.messages[1]["content"]
        assert "IDEAS BODY" not in result.messages[1]["content"]

    @pytest.mark.asyncio
    async def test_a_failing_reflection_pass_does_not_break_compaction(
        self, setup_session, mock_llm, compact_config
    ):
        """Compaction has already succeeded and the db is already authoritative
        by the time the reflections run. Losing a critique to a provider timeout
        must not cost the user their summary — so each pass fails alone."""
        session = setup_session
        logger = MagicMock()

        def explode_on_analysis(**kwargs):
            if kwargs["messages"][-1]["content"] == ANALYSIS_PROMPT:
                raise RuntimeError("provider exploded")
            return _fake_stream(kwargs["messages"])

        mock_llm.chat.completions.create = AsyncMock(side_effect=explode_on_analysis)

        result = await compact(session, mock_llm, compact_config, logger=logger)

        # The summary still landed, and the ideas pass still ran.
        assert "COMPACTED SUMMARY" in result.messages[1]["content"]
        assert not analysis_path(compact_config.config_dir, session.agent_id).exists()
        assert "IDEAS BODY" in ideas_path(session.cwd, session.agent_id).read_text()
        assert logger.warning.called

    @pytest.mark.asyncio
    async def test_an_empty_reflection_response_writes_no_file(
        self, setup_session, mock_llm, compact_config
    ):
        """A pass that streams nothing back is a failed pass, not an empty note.
        Writing a frontmatter-only file would look like a result and read like
        nothing."""
        session = setup_session
        logger = MagicMock()

        def empty_on_analysis(**kwargs):
            if kwargs["messages"][-1]["content"] == ANALYSIS_PROMPT:
                return _stream([_usage_chunk()])
            return _fake_stream(kwargs["messages"])

        mock_llm.chat.completions.create = AsyncMock(side_effect=empty_on_analysis)

        result = await compact(session, mock_llm, compact_config, logger=logger)

        assert "COMPACTED SUMMARY" in result.messages[1]["content"]
        assert not analysis_path(compact_config.config_dir, session.agent_id).exists()
        assert ideas_path(session.cwd, session.agent_id).exists()

    @pytest.mark.asyncio
    async def test_an_unwritable_reflection_path_does_not_break_compaction(
        self, setup_session, mock_llm, compact_config, tmp_path
    ):
        """A read-only checkout, a file where a directory should be, a project
        scope that cannot be created — all of those are the user's problem to
        fix later, not a reason to throw away a compaction."""
        session = setup_session
        # config_dir is a FILE, so <config_dir>/analysis/ cannot be created.
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory")
        compact_config.config_dir = blocker

        result = await compact(session, mock_llm, compact_config, logger=MagicMock())

        assert "COMPACTED SUMMARY" in result.messages[1]["content"]
        # The ideas pass is independent and still wrote.
        assert "IDEAS BODY" in ideas_path(session.cwd, session.agent_id).read_text()

    @pytest.mark.asyncio
    async def test_write_reflections_returns_what_it_wrote(
        self, setup_session, mock_llm, compact_config
    ):
        """The return value is the caller's only view into a function that
        swallows its own errors: kind -> path, or kind -> None."""
        session = setup_session
        written = await write_reflections(
            session, mock_llm, compact_config, logger=MagicMock()
        )

        assert written == {
            "analysis": analysis_path(compact_config.config_dir, session.agent_id),
            "ideas": ideas_path(session.cwd, session.agent_id),
        }
        assert all(p.exists() for p in written.values())

    @pytest.mark.asyncio
    async def test_write_reflections_overwrites_a_previous_note_for_the_same_agent(
        self, setup_session, mock_llm, compact_config
    ):
        """Same agent_id, same filename — a re-run replaces the note rather than
        appending a second copy of the same critique to it."""
        session = setup_session
        path = analysis_path(compact_config.config_dir, session.agent_id)
        path.parent.mkdir(parents=True)
        path.write_text("STALE\n")

        await write_reflections(session, mock_llm, compact_config, logger=MagicMock())

        assert "STALE" not in path.read_text()
        assert "ANALYSIS BODY" in path.read_text()

    @pytest.mark.asyncio
    async def test_a_session_rooted_at_home_keeps_analysis_and_ideas_separate(
        self, setup_session, mock_llm, compact_config
    ):
        """Global analysis and project ideas use separate directories even when
        the session runs from the config directory itself.
        """
        session = setup_session
        compact_config.config_dir = Path(session.cwd) / ".agents" / "crow"
        assert analysis_path(compact_config.config_dir, session.agent_id) != ideas_path(
            session.cwd, session.agent_id
        )

        written = await write_reflections(
            session, mock_llm, compact_config, logger=MagicMock()
        )

        assert written["analysis"] != written["ideas"]
        assert written["analysis"] == compact_config.config_dir / "analysis" / (
            f"{session.agent_id}.md"
        )
        assert written["ideas"].name == f"{session.agent_id}.md"
        assert "ANALYSIS BODY" in written["analysis"].read_text()
        assert "IDEAS BODY" in written["ideas"].read_text()


    # ---------------------------------------------------------------------
    # Degenerate fast path: a model that has gone insane must not be
    # asked to summarize itself. The real failure this encodes: a local
    # llama.cpp model started emitting nothing but "/" in its
    # reasoning_content until the context filled, crow hit the compaction
    # threshold, and compaction then asked THAT broken model to summarize
    # the session. Skips every LLM call and hands the next generation a
    # pointer instead.
    # ---------------------------------------------------------------------
    @pytest.fixture
    async def degenerate_session(self, setup_session):
        """A healthy 20-turn conversation that ends in the failure shape: an
        assistant turn whose reasoning is one character on repeat (content empty,
        exactly like the persisted rows crow.db holds for that session), then a
        user nudge."""
        session = setup_session
        await session.add_message(
            {"role": "assistant", "content": "", "reasoning_content": "/" * 400}
        )
        await session.add_message({"role": "user", "content": "welp"})
        return session

    def test_degenerate_repeat_reads_reasoning_and_content(self, degenerate_session):
        """The slash wall lives in reasoning_content — content AND reasoning are
        both scanned."""
        assert degenerate_repeat(degenerate_session) == "'/' repeated 400 times in a row"

    def test_degenerate_repeat_detects_a_content_wall(self, setup_session):
        """Same detector, wall in plain content."""
        session = setup_session
        session.messages[-1]["content"] = chr(92) * 200
        assert degenerate_repeat(session) == "'\\\\' repeated 200 times in a row"

    @pytest.mark.asyncio
    async def test_degenerate_repeat_ignores_legitimate_runs(self, setup_session):
        """Rulers, separators and fences live inside real text and never dominate
        a message; short runs are not loops at all."""
        session = setup_session
        ruler = "=" * (DEGENERATE_RUN + 16)
        await session.add_message(
            {
                "role": "assistant",
                "content": f"Here is the section divider\n\n{ruler}\n\nNow the real analysis "
                           "of the streaming bug we were chasing.",
            }
        )
        assert degenerate_repeat(session) is None

        await session.add_message({"role": "assistant", "content": "/" * 8})
        assert degenerate_repeat(session) is None

    @pytest.mark.asyncio
    async def test_degenerate_compaction_skips_every_llm_call(
        self, degenerate_session, mock_llm, compact_config, tmp_path
    ):
        """Zero LLM calls, zero reflection files: the model that would answer is
        the broken one."""
        session = degenerate_session
        result = await compact(session, mock_llm, compact_config, logger=MagicMock())

        mock_llm.chat.completions.create.assert_not_called()
        assert not analysis_path(compact_config.config_dir, session.agent_id).exists()
        assert not ideas_path(session.cwd, session.agent_id).exists()

        # The new generation still exists, same session and fork, next index.
        assert result.agent_idx == session.agent_idx + 1
        assert result.session_id == session.session_id

    @pytest.mark.asyncio
    async def test_degenerate_handoff_points_at_the_previous_session(
        self, degenerate_session, mock_llm, compact_config
    ):
        """The handoff is the whole point: no summary, just the pointer thomas
        would type by hand — which session to read, that the failure is not the
        reader's fault, and the last user message for orientation."""
        session = degenerate_session
        calls = []

        def on_compact(old_agent_id, new_session):
            calls.append((old_agent_id, new_session))

        result = await compact(
            session, mock_llm, compact_config, on_compact=on_compact, logger=MagicMock()
        )

        assert len(calls) == 1 and calls[0][1] is result  # callback still fires
        assert len(result.messages) == 2
        handoff = result.messages[1]["content"]
        assert f"previous session '{session.session_id}'" in handoff
        assert "'/' repeated 400 times in a row" in handoff
        assert "not anything you did" in handoff
        assert "welp" in handoff  # the last user message survives as orientation
        assert "COMPACTED SUMMARY" not in handoff

    @pytest.mark.asyncio
    async def test_degenerate_detection_looks_past_the_last_turn(
        self, setup_session, mock_llm, compact_config
    ):
        """The loop can be interrupted mid-wall: a short degenerate blip after the
        big one must not hide it. The detector scans recent assistant turns, so a
        tiny '////////' trailing the slash wall still trips it."""
        session = setup_session
        await session.add_message(
            {"role": "assistant", "content": "", "reasoning_content": "/" * 400}
        )
        await session.add_message({"role": "user", "content": "what the fuck dude"})
        await session.add_message(
            {"role": "assistant", "content": "", "reasoning_content": "/" * 8}
        )

        result = await compact(session, mock_llm, compact_config, logger=MagicMock())
        mock_llm.chat.completions.create.assert_not_called()
        assert "'/' repeated 400 times in a row" in result.messages[1]["content"]



class TestReflectionPaths:
    """The two output locations, without a session or an LLM in sight."""

    def test_analysis_path_is_global(self, tmp_path):
        assert analysis_path(tmp_path / "crow", "sess-2-1") == (
            tmp_path / "crow" / "analysis" / "sess-2-1.md"
        )

    def test_ideas_path_is_project_scoped(self, tmp_path):
        assert ideas_path(tmp_path / "repo", "sess-2-1") == (
            tmp_path / "repo" / ".agents" / "crow" / "ideas" / "sess-2-1.md"
        )

    def test_paths_accept_strings(self):
        """config_dir is a Path but session.cwd is a str — both have to work."""
        assert analysis_path("/cfg", "a-1-1").name == "a-1-1.md"
        assert ideas_path("/proj", "a-1-1").parts[-4:] == (
            ".agents",
            "crow",
            "ideas",
            "a-1-1.md",
        )
