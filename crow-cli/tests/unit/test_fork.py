"""Unit tests for session fork (schema v5) — no live LLM.

Fork relies on message-id POSITION anchors and fork-aware loading, which only
the real sqlite store provides (FakeMemoryClient has neither), so these tests
run against a real tmp DB via the MemoryClient ``memory_path`` override.

Fork semantics under test (see notes/dev/crow-fork-design.md):
- fork = new agent ROW sharing (session_id, agent_idx), next fork_idx
- NO prefix copying — fork view = trunk rows with id <= forked_at + own rows
- turnIdx snaps to user-message boundaries (tool pairs never split)
- trunk stays unpolluted
"""

import pytest

from crow_cli.agent.session import AgentSession, lookup_or_create_prompt, snap_turn_cut
from crow_cli.memory import build_agent_id


# ---- snap_turn_cut: pure boundary logic ----


def _turny_messages():
    return [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "turn 0"},  # turn 0 starts (idx 1)
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "result"},
        {"role": "assistant", "content": "turn 0 done"},
        {"role": "user", "content": "turn 1"},  # turn 1 starts (idx 5)
        {"role": "assistant", "content": "turn 1 done"},
        {"role": "user", "content": "turn 2"},  # turn 2 starts (idx 7), last
        {"role": "assistant", "content": "turn 2 done"},
    ]


def test_snap_turn_cut_none_keeps_head():
    assert snap_turn_cut(_turny_messages(), None) is None


def test_snap_turn_cut_lands_on_user_boundaries():
    msgs = _turny_messages()
    # "include through the END of turn 0" -> cut at the start of turn 1,
    # so the tool_calls group stays with its tool result
    assert snap_turn_cut(msgs, 0) == 5
    assert snap_turn_cut(msgs, 1) == 7


def test_snap_turn_cut_last_turn_and_overflow_are_head():
    msgs = _turny_messages()
    assert snap_turn_cut(msgs, 2) is None
    assert snap_turn_cut(msgs, 99) is None


def test_snap_turn_cut_negative_clamps_and_no_user_msgs():
    assert snap_turn_cut(_turny_messages(), -3) == 5
    assert snap_turn_cut([{"role": "system", "content": "x"}], 0) is None


# ---- AgentSession.fork against a real sqlite tmp db ----


@pytest.fixture
async def fork_env(tmp_path):
    """Trunk session with two turns; turn 0 contains a full tool roundtrip."""
    memory_path = f"sqlite:///{tmp_path / 'fork.db'}"
    prompt_id = await lookup_or_create_prompt(
        "You are {{name}}.", name="fork-test", memory_path=memory_path
    )
    session = await AgentSession.create(
        prompt_id=prompt_id,
        prompt_args={"name": "Crow"},
        tool_definitions=[{"type": "function", "function": {"name": "t"}}],
        request_params={"temperature": 0.2},
        model_identifier="test-model",
        memory_path=memory_path,
        cwd="/tmp",
        session_id="forky-session",
    )
    await session.add_message({"role": "user", "content": "turn zero"})
    await session.add_message(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "t", "arguments": "{}"}}
            ],
        }
    )
    await session.add_message({"role": "tool", "tool_call_id": "c1", "content": "tool result"})
    await session.add_message({"role": "assistant", "content": "turn zero done"})
    await session.add_message({"role": "user", "content": "turn one"})
    await session.add_message({"role": "assistant", "content": "turn one done"})
    await session.close()
    return session, memory_path


@pytest.mark.asyncio
async def test_fork_at_head(fork_env):
    session, memory_path = fork_env
    fork = await AgentSession.fork(session.session_id, memory_path=memory_path)

    assert fork.fork_idx == 2
    assert fork.agent_idx == session.agent_idx
    assert fork.session_id == session.session_id
    assert fork.agent_id == build_agent_id(session.session_id, session.agent_idx, 2)
    assert fork.forked_at is not None  # anchored at the trunk's last message
    # fork at HEAD sees the trunk's full history
    assert [m.get("content") for m in fork.messages] == [
        m.get("content") for m in session.messages
    ]
    await fork.close()


@pytest.mark.asyncio
async def test_fork_at_turn_keeps_tool_pairs_intact(fork_env):
    session, memory_path = fork_env
    fork = await AgentSession.fork(session.session_id, memory_path=memory_path, turn_idx=0)

    contents = [m.get("content") for m in fork.messages]
    # system + ALL of turn 0 (user, tool_calls, tool result, assistant);
    # turn 1 is excluded and the tool_calls group was not split
    assert contents[1:] == ["turn zero", None, "tool result", "turn zero done"]
    roles = [m["role"] for m in fork.messages]
    assert roles == ["system", "user", "assistant", "tool", "assistant"]
    await fork.close()


@pytest.mark.asyncio
async def test_fork_view_is_prefix_plus_own_and_trunk_unpolluted(fork_env):
    session, memory_path = fork_env
    fork = await AgentSession.fork(session.session_id, memory_path=memory_path, turn_idx=0)
    await fork.add_message({"role": "user", "content": "fork question"})
    await fork.add_message({"role": "assistant", "content": "fork answer"})
    await fork.close()

    reloaded = await AgentSession.load(fork.agent_id, memory_path=memory_path)
    contents = [m.get("content") for m in reloaded.messages]
    assert contents[-2:] == ["fork question", "fork answer"]
    assert "turn zero" in contents  # shared prefix still there
    assert "turn one" not in contents  # post-anchor trunk rows invisible
    await reloaded.close()

    trunk = await AgentSession.load(session.agent_id, memory_path=memory_path)
    trunk_contents = [m.get("content") for m in trunk.messages]
    assert "fork question" not in trunk_contents
    assert trunk_contents[-1] == "turn one done"
    await trunk.close()


@pytest.mark.asyncio
async def test_second_fork_gets_fork_idx_3(fork_env):
    session, memory_path = fork_env
    f2 = await AgentSession.fork(session.session_id, memory_path=memory_path)
    f3 = await AgentSession.fork(session.session_id, memory_path=memory_path)
    assert (f2.fork_idx, f3.fork_idx) == (2, 3)
    assert f3.agent_id == build_agent_id(session.session_id, session.agent_idx, 3)
    await f2.close()
    await f3.close()


@pytest.mark.asyncio
async def test_fork_inherits_source_config(fork_env):
    session, memory_path = fork_env
    fork = await AgentSession.fork(session.session_id, memory_path=memory_path)
    assert fork.model_identifier == "test-model"
    assert fork.tools == session.tools
    assert fork.request_params == session.request_params
    assert fork.prompt_id == session.prompt_id
    await fork.close()


@pytest.mark.asyncio
async def test_fork_follows_trunk_head_agent_idx(fork_env):
    """After a compaction (new trunk row at agent_idx+1), fork() targets the
    trunk HEAD agent, not the stale agent_idx=1 row."""
    session, memory_path = fork_env
    compacted = await AgentSession.create(
        prompt_id=session.prompt_id,
        prompt_args={"name": "Crow"},
        tool_definitions=[],
        request_params={},
        model_identifier="test-model",
        memory_path=memory_path,
        session_id=session.session_id,
        agent_idx=2,
    )
    await compacted.add_message({"role": "user", "content": "post-compact"})
    await compacted.close()

    fork = await AgentSession.fork(session.session_id, memory_path=memory_path)
    assert fork.agent_idx == 2
    assert fork.agent_id == build_agent_id(session.session_id, 2, 2)
    assert [m.get("content") for m in fork.messages][-1] == "post-compact"
    await fork.close()


@pytest.mark.asyncio
async def test_fork_explicit_agent_idx(fork_env):
    """agentIdx lets a client fork an older trunk agent explicitly."""
    session, memory_path = fork_env
    # first move the trunk head forward so agent_idx=1 is no longer HEAD
    compacted = await AgentSession.create(
        prompt_id=session.prompt_id,
        prompt_args={"name": "Crow"},
        tool_definitions=[],
        request_params={},
        model_identifier="test-model",
        memory_path=memory_path,
        session_id=session.session_id,
        agent_idx=2,
    )
    await compacted.close()

    fork = await AgentSession.fork(session.session_id, memory_path=memory_path, agent_idx=1)
    assert fork.agent_id == build_agent_id(session.session_id, 1, 2)
    assert [m.get("content") for m in fork.messages][-1] == "turn one done"
    await fork.close()
