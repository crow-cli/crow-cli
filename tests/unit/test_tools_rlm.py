"""rlm: the delegation tool.

The budget refusal and the identity rail are real code paths that stop
BEFORE any subprocess — a refused delegate spawns nothing. The answer reader
is exercised against a real sqlite fork chain (trunk prefix + the fork's own
rows), which is the read task/_child_answer gets wrong for delegates.
"""

import pytest

from crow_cli.memory import (
    add_message,
    create_agent,
    create_database,
    get_engine,
    get_ro_engine,
)
from crow_cli.tools.register import begin_cell, clear
from crow_cli.tools.results import RlmResult, RlmToolError
from crow_cli.tools.rlm import (
    MAX_RLM_DEPTH,
    _delegate_answer,
    _delegate_prompt,
    _dispose,
    _engine,
    _identity,
    _state,
    rlm,
)


@pytest.fixture(autouse=True)
def _clean():
    clear()
    yield
    clear()
    _dispose()


@pytest.mark.asyncio
async def test_outside_a_cell_there_is_nothing_to_fork():
    with pytest.raises(RlmToolError, match="no session identity"):
        await rlm("is src/x.py relevant?")


@pytest.mark.asyncio
async def test_the_rail_without_a_database_raises(tmp_path):
    begin_cell(session_id="s1", db_uri=f"sqlite:///{tmp_path}/crow.db")
    with pytest.raises(RlmToolError, match="no database at"):
        await rlm("is src/x.py relevant?")


@pytest.mark.asyncio
async def test_a_delegate_cannot_delegate(tmp_path):
    """The refusal fires BEFORE any I/O: the db file does not even exist,
    and no subprocess is ever spawned — that is 10d's business."""
    begin_cell(
        session_id="s1",
        db_uri=f"sqlite:///{tmp_path}/never-created.db",
        rlm_depth=MAX_RLM_DEPTH,
    )
    with pytest.raises(RlmToolError) as exc:
        await rlm("is src/x.py relevant?")
    assert "MAX_RLM_DEPTH" in str(exc.value)
    assert "delegate cannot delegate" in str(exc.value)


@pytest.mark.asyncio
async def test_identity_reads_the_rail(tmp_path):
    uri = f"sqlite:///{tmp_path}/crow.db"
    create_database(uri)
    begin_cell(session_id="s1", db_uri=uri, rlm_depth=0)
    assert _identity() == ("s1", 0)


def test_the_delegates_prompt_carries_its_depth_and_the_rule():
    p = _delegate_prompt("Is src/x.py relevant?", 1)
    assert f"delegation 1 of a maximum {MAX_RLM_DEPTH}" in p
    assert "rlm() will refuse you" in p
    assert "Do not start new work" in p
    assert "change nothing" in p
    assert p.endswith("Is src/x.py relevant?")


def test_the_delegates_answer_is_its_own_last_word(tmp_path):
    """A delegate IS a fork: its transcript is the trunk prefix followed by
    its own rows, and the answer is the last assistant word in THAT."""
    uri = f"sqlite:///{tmp_path}/crow.db"
    create_database(uri)
    engine = get_engine(uri)
    try:
        create_agent(
            engine, agent_id="s1-1-1", session_id="s1", agent_idx=1,
            fork_idx=1, system_prompt="", cwd="/tmp",
        )
        anchor = add_message(
            engine, "s1-1-1", {"role": "user", "content": "is x.py relevant?"},
        )
        create_agent(
            engine, agent_id="s1-1-2", session_id="s1", agent_idx=1,
            fork_idx=2, forked_at=str(anchor), system_prompt="", cwd="/tmp",
        )
        add_message(
            engine, "s1-1-2",
            {"role": "assistant", "content": [{"type": "text", "text": "yes — it defines the rail"}]},
        )
        # A second fork with NO rows of its own: its history is the trunk
        # PREFIX, so its last assistant word is the trunk's — reading only a
        # fork's own rows would call that "(no final answer)".
        anchor2 = add_message(
            engine, "s1-1-1",
            {"role": "assistant", "content": [{"type": "text", "text": "the trunk said: read the rail doc"}]},
        )
        create_agent(
            engine, agent_id="s1-1-3", session_id="s1", agent_idx=1,
            fork_idx=2, forked_at=str(anchor2), system_prompt="", cwd="/tmp",
        )
    finally:
        engine.dispose()

    ro = get_ro_engine(uri)
    try:
        assert _delegate_answer(ro, "s1-1-2") == "yes — it defines the rail"
        assert (
            _delegate_answer(ro, "s1-1-3")
            == "the trunk said: read the rail doc"
        )
        assert _delegate_answer(ro, "s1-9-2") == "(the delegate produced no transcript)"
    finally:
        ro.dispose()


def test_a_delegate_that_never_spoke_says_so(tmp_path):
    uri = f"sqlite:///{tmp_path}/crow.db"
    create_database(uri)
    engine = get_engine(uri)
    try:
        create_agent(
            engine, agent_id="s1-1-2", session_id="s1", agent_idx=1,
            fork_idx=2, system_prompt="", cwd="/tmp",
        )
        add_message(engine, "s1-1-2", {"role": "user", "content": "answer me"})
    finally:
        engine.dispose()

    ro = get_ro_engine(uri)
    try:
        assert _delegate_answer(ro, "s1-1-2") == "(the delegate produced no final answer)"
    finally:
        ro.dispose()


@pytest.mark.asyncio
async def test_the_engine_is_cached_per_uri_and_disposable(tmp_path):
    u1 = f"sqlite:///{tmp_path}/a.db"
    u2 = f"sqlite:///{tmp_path}/b.db"
    create_database(u1)
    create_database(u2)

    begin_cell(session_id="s1", db_uri=u1)
    e1 = _engine()
    assert _engine() is e1

    begin_cell(session_id="s1", db_uri=u2)
    e2 = _engine()
    assert e2 is not e1

    _dispose()
    assert _state["engine"] is None
    assert _state["uri"] is None


def test_the_answer_is_windowed_in_text_not_in_the_object():
    r = RlmResult(session_id="s1-1-2", answer="x" * 6000, prompt="q?", depth=1)
    assert "6,000 chars" in r.text
    assert "answer[5000:]" in r.text
    assert len(r.answer) == 6000


def test_an_async_delegation_reads_like_a_handle():
    r = RlmResult(session_id="s1-1-2", answer="", prompt="q?", waited=False, depth=1)
    assert "memory(" in r.text
    assert 'session_id="s1-1-2"' in r.text
    assert r.acp_payload()["subject"] == "s1-1-2"


def test_a_stopped_delegate_says_why():
    r = RlmResult(
        session_id="s1-1-2", answer="partial", prompt="q?", depth=1,
        stop_reason="cancelled",
    )
    assert "stopped: cancelled" in r.text
