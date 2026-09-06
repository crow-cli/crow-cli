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

from crow_cli.agent.session import (
    AgentSession,
    lookup_or_create_prompt,
    snap_offset_cut,
    snap_turn_cut,
)
from crow_cli.memory import build_agent_id, delegation_tool_call_ids, get_engine
from crow_cli.memory.models import SubtoolCall


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


# ---- snap_offset_cut: message-granular, and it snaps ----


def _delegating_messages():
    """A trunk whose TAIL is a delegation group: an execute call whose id the
    subtool register recorded as an rlm call, then its result. This is the
    shape rlm forks from when the parent has already delegated once."""
    return [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "is F relevant?"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_exec1",
                    "type": "function",
                    "function": {"name": "execute", "arguments": '{"code": "await rlm(...)"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_exec1", "content": "the delegate said: yes"},
    ]


def test_snap_offset_cut_zero_keeps_head_when_the_tail_is_complete():
    msgs = _turny_messages()
    assert snap_offset_cut(msgs, 0) == len(msgs)


def test_snap_offset_cut_reaches_cuts_a_turn_boundary_cannot():
    """turn_idx only lands on 5, 7 or None for this history; the offset is
    the finer instrument, which is the reason it exists."""
    msgs = _turny_messages()
    assert snap_offset_cut(msgs, 1) == 8
    assert snap_offset_cut(msgs, 2) == 7
    assert snap_offset_cut(msgs, 3) == 6
    assert set(snap_turn_cut(msgs, i) for i in range(9)) == {5, 7, None}


def test_snap_offset_cut_steps_over_a_dangling_tool_calls_group():
    """Cutting between an assistant tool_calls message and its results leaves
    a group with nothing answering it — not ugly, rejected: every
    tool_call_id must be followed by a tool message."""
    msgs = _turny_messages()
    # offset 5 lands on the tool result (a complete group, kept)...
    assert snap_offset_cut(msgs, 5) == 4
    # ...offset 6 lands on the assistant tool_calls itself, and snaps back
    assert snap_offset_cut(msgs, 6) == 2


def test_snap_offset_cut_steps_over_a_delegation_at_the_boundary():
    """A fork whose history ENDS in "I delegated this and here is what came
    back" is a fork that delegates instead of answering — the infinity
    mirror. The result goes, then the assistant message above it, so the
    whole group goes."""
    msgs = _delegating_messages()
    assert snap_offset_cut(msgs, 0, {"call_exec1"}) == 2
    # without the register's ids there is nothing to distinguish it from any
    # other tool roundtrip, and the group survives
    assert snap_offset_cut(msgs, 0) == 4
    assert snap_offset_cut(msgs, 0, {"some_other_call"}) == 4


def test_snap_offset_cut_keeps_an_ordinary_tool_group_at_the_boundary():
    """Only a DELEGATION is stepped over. A read at the tail is a complete
    group and legitimate context; dropping it would be throwing history
    away for nothing."""
    msgs = _turny_messages()
    assert snap_offset_cut(msgs, 5, {"unrelated"}) == 4
    # ...but name c1 a delegation and the same cut snaps past it
    assert snap_offset_cut(msgs, 5, {"c1"}) == 2


def test_snap_offset_cut_leaves_a_delegation_deeper_in_the_prefix():
    """The snap is a BOUNDARY rule. Removing a delegation from the middle of
    the kept prefix would mean rewriting rows the fork shares with its trunk
    (they are never copied) or discarding everything since the first one —
    see EXECUTE_TODO 10e(i)."""
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "d1"}]},
        {"role": "tool", "tool_call_id": "d1", "content": "delegate said yes"},
        {"role": "assistant", "content": "noted"},
        {"role": "user", "content": "next"},
    ]
    assert snap_offset_cut(msgs, 0, {"d1"}) == 6


def test_snap_offset_cut_clamps_and_can_reach_zero():
    msgs = _turny_messages()
    assert snap_offset_cut(msgs, -3) == len(msgs)
    assert snap_offset_cut(msgs, len(msgs)) == 0
    assert snap_offset_cut(msgs, 999) == 0
    assert snap_offset_cut([], 0) == 0


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


# ---- the offset path against a real sqlite db, with a real register row ----


@pytest.fixture
async def delegating_env(tmp_path):
    """A trunk whose HEAD is a delegation group, plus the subtool_calls row
    that makes it identifiable — the shape rlm forks from.

    The register row is written the way the kernel's write-through writes it:
    parent_tool_call_id is TurnCtx.tcid's "<turn_id>/<llm id>", and the
    message history carries only the bare llm id. That gap is the whole
    reason delegation_tool_call_ids exists.
    """
    memory_path = f"sqlite:///{tmp_path / 'delegating.db'}"
    prompt_id = await lookup_or_create_prompt(
        "You are {{name}}.", name="fork-test", memory_path=memory_path
    )
    session = await AgentSession.create(
        prompt_id=prompt_id,
        prompt_args={"name": "Crow"},
        tool_definitions=[{"type": "function", "function": {"name": "execute"}}],
        request_params={"temperature": 0.2},
        model_identifier="test-model",
        memory_path=memory_path,
        cwd="/tmp",
        session_id="delegating-session",
    )
    await session.add_message({"role": "user", "content": "is F relevant?"})
    await session.add_message(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_exec1",
                    "type": "function",
                    "function": {
                        "name": "execute",
                        "arguments": '{"code": "print(await rlm(\'is F relevant?\'))"}',
                    },
                }
            ],
        }
    )
    await session.add_message(
        {"role": "tool", "tool_call_id": "call_exec1", "content": "the delegate said: yes"}
    )
    await session.close()

    engine = get_engine(memory_path)
    with engine.begin() as conn:
        conn.execute(
            SubtoolCall.__table__.insert().values(
                session_id=session.session_id,
                agent_id=session.agent_id,
                parent_tool_call_id="turn-1/call_exec1",
                cell_seq=3,
                tool="rlm",
                args={"prompt": "is F relevant?"},
                status="completed",
            )
        )
    engine.dispose()
    return session, memory_path


def test_delegation_tool_call_ids_strips_the_turn_prefix(delegating_env):
    """The register stores "<turn_id>/<llm id>"; the history stores the bare
    llm id. Without the strip the two never meet and the snap never fires."""
    session, memory_path = delegating_env
    engine = get_engine(memory_path)
    try:
        assert delegation_tool_call_ids(engine, session.session_id) == {"call_exec1"}
        # a fork's wire id is its agent_id, and the row carries the trunk's
        # bare session id — both have to resolve to the same set
        assert delegation_tool_call_ids(engine, session.agent_id) == {"call_exec1"}
        # only delegations: an edit or a read in the same cell is not one
        assert delegation_tool_call_ids(engine, session.session_id, tools=("nope",)) == set()
        assert delegation_tool_call_ids(engine, "some-other-session") == set()
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_fork_at_offset_zero_keeps_the_whole_trunk(delegating_env):
    """No ids, no snap: offset 0 is HEAD, same as forking without an offset."""
    session, memory_path = delegating_env
    fork = await AgentSession.fork(
        session.session_id, memory_path=memory_path, message_offset=0
    )
    assert [m.get("content") for m in fork.messages] == [
        m.get("content") for m in session.messages
    ]
    await fork.close()


@pytest.mark.asyncio
async def test_fork_snaps_the_delegation_group_out_of_the_forks_history(delegating_env):
    """The point of the whole step: the delegate must not inherit a history
    that ends in the parent delegating."""
    session, memory_path = delegating_env
    engine = get_engine(memory_path)
    try:
        ids = delegation_tool_call_ids(engine, session.session_id)
    finally:
        engine.dispose()
    fork = await AgentSession.fork(
        session.session_id,
        memory_path=memory_path,
        message_offset=0,
        delegation_ids=ids,
    )
    contents = [m.get("content") for m in fork.messages]
    assert contents == ["You are Crow.", "is F relevant?"]
    assert "the delegate said: yes" not in contents
    assert all("tool_calls" not in m for m in fork.messages)

    # and the trunk is untouched — the rows are shared, never rewritten
    trunk = await AgentSession.load(session.agent_id, memory_path=memory_path)
    assert [m.get("content") for m in trunk.messages][-1] == "the delegate said: yes"
    await trunk.close()
    await fork.close()


@pytest.mark.asyncio
async def test_fork_offset_counts_back_a_single_message(delegating_env):
    session, memory_path = delegating_env
    fork = await AgentSession.fork(
        session.session_id, memory_path=memory_path, message_offset=1
    )
    # drops the tool result; the assistant tool_calls above it is then
    # dangling, so the snap takes that too
    assert [m.get("content") for m in fork.messages] == ["You are Crow.", "is F relevant?"]
    await fork.close()


@pytest.mark.asyncio
async def test_fork_offset_that_leaves_nothing_raises(delegating_env):
    """cut == 0 used to index records[-1] — "keep nothing" silently became
    "fork at HEAD", the one outcome the offset exists to prevent."""
    session, memory_path = delegating_env
    with pytest.raises(ValueError, match="leaves no history to fork"):
        await AgentSession.fork(
            session.session_id, memory_path=memory_path, message_offset=99
        )


@pytest.mark.asyncio
async def test_fork_refuses_both_policies_at_once(delegating_env):
    session, memory_path = delegating_env
    with pytest.raises(ValueError, match="not both"):
        await AgentSession.fork(
            session.session_id,
            memory_path=memory_path,
            turn_idx=0,
            message_offset=1,
        )


# ---- the depth budget: durable, because a delegate that forgets its depth
#      is the infinity mirror again ----


def test_rlm_depth_reads_prompt_args_and_refuses_garbage():
    """prompt_args is JSON out of a db column, so it is not trusted: a
    string, a negative, or a missing key all mean depth 0."""
    session = AgentSession(agent_id="s-1-1", session_id="s")
    assert session.rlm_depth == 0  # never set at all
    session.prompt_args = {"rlm_depth": 2}
    assert session.rlm_depth == 2
    session.prompt_args = {"rlm_depth": "3"}
    assert session.rlm_depth == 0
    session.prompt_args = {"rlm_depth": -1}
    assert session.rlm_depth == 0
    session.prompt_args = {}
    assert session.rlm_depth == 0


@pytest.mark.asyncio
async def test_fork_records_the_delegation_depth(fork_env):
    session, memory_path = fork_env
    assert session.rlm_depth == 0  # a trunk is depth 0
    fork = await AgentSession.fork(
        session.session_id, memory_path=memory_path, rlm_depth=1
    )
    assert fork.rlm_depth == 1
    await fork.close()


@pytest.mark.asyncio
async def test_depth_survives_a_load_in_another_process(fork_env):
    """The budget lives on the agent row, not in the process that set it: a
    delegate re-prompted by a fresh agent process must still know it is a
    delegate, or the budget is decorative."""
    session, memory_path = fork_env
    fork = await AgentSession.fork(
        session.session_id, memory_path=memory_path, rlm_depth=1
    )
    fork_id = fork.agent_id
    await fork.close()

    reloaded = await AgentSession.load(fork_id, memory_path=memory_path)
    assert reloaded.rlm_depth == 1
    await reloaded.close()


@pytest.mark.asyncio
async def test_a_plain_fork_carries_no_depth(fork_env):
    """The CLI's --fork and every interrogation fork pass no depth, and must
    not grow the key: their prompt_args render a system prompt, and a
    surprise key in there is a surprise in every template."""
    session, memory_path = fork_env
    fork = await AgentSession.fork(session.session_id, memory_path=memory_path)
    assert fork.rlm_depth == 0
    assert "rlm_depth" not in (fork.prompt_args or {})
    assert fork.prompt_args == session.prompt_args
    await fork.close()


@pytest.mark.asyncio
async def test_depth_does_not_disturb_the_rendered_system_prompt(fork_env):
    """fork() copies the source's system_prompt verbatim rather than
    re-rendering, so the extra prompt_args key cannot change what the
    delegate is told — but the fork's own args must still render if anything
    ever does re-render them."""
    from crow_cli.agent.prompt import render_template

    session, memory_path = fork_env
    fork = await AgentSession.fork(
        session.session_id, memory_path=memory_path, rlm_depth=1
    )
    assert fork.messages[0]["content"] == session.messages[0]["content"]
    assert render_template("You are {{name}}.", **fork.prompt_args) == "You are Crow."
    await fork.close()

