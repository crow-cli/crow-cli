"""``session/delete``: forgetting a session takes its whole footprint.

The schema has no foreign keys and no cascades, so every table a session
touches is named explicitly in :func:`crow_cli.memory.writes.delete_session`
— which is exactly the kind of list that goes stale silently. These tests run
against a real sqlite db and assert both halves: what is gone, and what a
neighbouring session still has.
"""

import pytest
from sqlalchemy import func

from crow_cli.agent.session import AgentSession, lookup_or_create_prompt
from crow_cli.memory import (
    create_database,
    delete_session,
    get_engine,
    list_session_infos,
    search_messages,
)
from crow_cli.memory.models import (
    Agent,
    Goal,
    Message,
    Prompt,
    SessionTab,
    SubtoolCall,
    Task,
    TaskDelivery,
)


@pytest.fixture
async def store(tmp_path):
    """Two sessions in one real db: ``doomed`` (with a fork, a compaction row
    and a row in every side table) and ``keeper``, which must survive
    untouched. Returns ``(db_uri, doomed_session_id)``.
    """
    uri = f"sqlite:///{tmp_path / 'crow.db'}"
    create_database(uri)
    prompt_id = await lookup_or_create_prompt(
        "You are {{name}}.", name="delete-test", memory_path=uri
    )
    sessions = {}
    for sid in ("doomed", "keeper"):
        s = await AgentSession.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Crow"},
            tool_definitions=[],
            request_params={},
            model_identifier="test-model",
            memory_path=uri,
            cwd="/tmp",
            session_id=sid,
        )
        await s.add_message({"role": "user", "content": f"hello from {sid} zzzqq"})
        await s.add_message({"role": "assistant", "content": f"hi from {sid}"})
        sessions[sid] = s
    doomed = sessions["doomed"]

    engine = get_engine(uri)
    with engine.begin() as conn:
        # a compaction row and a fork of the doomed session: same session_id,
        # other agent_idx / fork_idx
        conn.execute(
            Agent.__table__.insert().values(
                agent_id="doomed-2-1", session_id="doomed", agent_idx=2, fork_idx=1,
                prompt_id=prompt_id, cwd="/tmp", created_at="2026-01-01T00:00:00+00:00",
            )
        )
        conn.execute(
            Agent.__table__.insert().values(
                agent_id="doomed-1-2", session_id="doomed", agent_idx=1, fork_idx=2,
                prompt_id=prompt_id, cwd="/tmp", created_at="2026-01-01T00:00:00+00:00",
            )
        )
        conn.execute(
            Message.__table__.insert().values(
                agent_id="doomed-1-2", fork_idx=2, role="user",
                data={"role": "user", "content": "fork only"},
                created_at="2026-01-01T00:00:00+00:00",
            )
        )
        for table, values in (
            (Goal, [
                dict(session_id="doomed", goal_id="g1", objective="keep going"),
                dict(session_id="doomed-1-2", goal_id="g2", objective="fork goal"),
                dict(session_id="keeper", goal_id="g3", objective="survivor"),
            ]),
            (TaskDelivery, [
                dict(session_id="doomed", task_id="t1", content="done"),
                dict(session_id="keeper", task_id="t2", content="done"),
            ]),
            (Task, [
                # owned by the doomed session
                dict(task_id="t1", owner_session="doomed", sub_session="child-1", prompt="p"),
                # owned by the keeper, merely POINTING at the doomed one
                dict(task_id="t2", owner_session="keeper", sub_session="doomed", prompt="p"),
            ]),
            (SessionTab, [
                dict(agent="crow", agent_identity="i", agent_session_id="doomed", title="D"),
                dict(agent="crow", agent_identity="i", agent_session_id="keeper", title="K"),
            ]),
            (SubtoolCall, [
                dict(session_id="doomed", parent_tool_call_id="turn/call_1",
                     tool="write", status="completed", result_kind="diff", emitted=1),
                dict(session_id="keeper", parent_tool_call_id="turn/call_2",
                     tool="write", status="completed", result_kind="diff", emitted=1),
            ]),
        ):
            for row in values:
                conn.execute(table.__table__.insert().values(**row))
    engine.dispose()

    for s in sessions.values():
        await s.close()
    return uri, "doomed"


def _count(uri, model, **where) -> int:
    engine = get_engine(uri)
    try:
        with engine.connect() as conn:
            from sqlalchemy import select

            return conn.execute(
                select(func.count()).select_from(model).filter_by(**where)
            ).scalar()
    finally:
        engine.dispose()


def _listed(engine) -> set[str]:
    """The session ids ``session/list`` would hand a client, via the same
    reader that builds the wire shape."""
    infos, _ = list_session_infos(engine)
    return {i["session_id"] for i in infos}


def test_delete_removes_the_session_from_the_list(store):
    uri, sid = store
    engine = get_engine(uri)
    try:
        assert _listed(engine) == {"doomed", "keeper"}
        assert delete_session(engine, sid) is True
        assert _listed(engine) == {"keeper"}
    finally:
        engine.dispose()


def test_delete_takes_every_agent_row_and_their_messages(store):
    uri, sid = store
    keeper_messages = _count(uri, Message, agent_id="keeper-1-1")
    engine = get_engine(uri)
    try:
        delete_session(engine, sid)
        assert _count(uri, Agent, session_id="doomed") == 0
        for agent_id in ("doomed-1-1", "doomed-2-1", "doomed-1-2"):
            assert _count(uri, Message, agent_id=agent_id) == 0
        # the neighbour is untouched, down to the message count it had before
        assert _count(uri, Agent, session_id="keeper") == 1
        assert _count(uri, Message, agent_id="keeper-1-1") == keeper_messages
    finally:
        engine.dispose()


def test_delete_takes_the_side_tables_keyed_on_either_wire_id(store):
    """Goals, mailboxes, tabs and register rows are keyed on the WIRE id, and
    a fork has one of its own — matching only the id the caller passed would
    leave the fork's rows behind."""
    uri, sid = store
    engine = get_engine(uri)
    try:
        delete_session(engine, sid)
        assert _count(uri, Goal, session_id="doomed") == 0
        assert _count(uri, Goal, session_id="doomed-1-2") == 0
        assert _count(uri, Goal, session_id="keeper") == 1
        assert _count(uri, TaskDelivery, session_id="doomed") == 0
        assert _count(uri, TaskDelivery, session_id="keeper") == 1
        assert _count(uri, SessionTab, agent_session_id="doomed") == 0
        assert _count(uri, SessionTab, agent_session_id="keeper") == 1
        assert _count(uri, SubtoolCall, session_id="doomed") == 0
        assert _count(uri, SubtoolCall, session_id="keeper") == 1
    finally:
        engine.dispose()


def test_delete_takes_tasks_it_owned_but_not_someone_elses_record_of_it(store):
    """``t2`` belongs to the keeper and merely names the doomed session as its
    child. Deleting it would erase work the survivor delegated; leaving it
    costs a dangling ``sub_session``, which ``task_by_sub_session`` answers as
    "no such child" — the same answer it gives for a subagent that never ran.
    """
    uri, sid = store
    engine = get_engine(uri)
    try:
        delete_session(engine, sid)
        assert _count(uri, Task, task_id="t1") == 0
        assert _count(uri, Task, task_id="t2") == 1
    finally:
        engine.dispose()


def test_delete_leaves_the_shared_prompt(store):
    """Prompts are deduplicated by content and shared across sessions; one
    outliving a reader is the point of deduplicating."""
    uri, sid = store
    before = _count(uri, Prompt)
    engine = get_engine(uri)
    try:
        delete_session(engine, sid)
    finally:
        engine.dispose()
    assert _count(uri, Prompt) == before


def test_delete_drops_the_keyword_index_too(store):
    """The FTS table is its own table on both backends, so nothing cascades to
    it. Left behind, its rowids rank in ``search_fts`` and the join in
    ``search_rows`` throws them away — a search that silently comes up short.
    """
    uri, sid = store
    engine = get_engine(uri)
    try:
        assert search_messages(engine, "zzzqq") != []
        delete_session(engine, sid)
        hits = search_messages(engine, "zzzqq")
        assert all(h["session_id"] != "doomed" for h in hits)
        # the keeper's message carried the same token and still ranks
        assert hits
    finally:
        engine.dispose()


def test_delete_of_an_unknown_session_is_false_not_silent_success(store):
    uri, _ = store
    engine = get_engine(uri)
    try:
        assert delete_session(engine, "never-existed") is False
        # and it took nothing with it
        assert _count(uri, Agent, session_id="keeper") == 1
    finally:
        engine.dispose()


def test_a_fork_id_deletes_the_whole_session(store):
    """``session/list`` never hands out a fork id, so arriving with one means
    the caller thinks a branch is a session. Deleting only the branch would
    leave a trunk with a hole in its own history."""
    uri, _ = store
    engine = get_engine(uri)
    try:
        assert delete_session(engine, "doomed-1-2") is True
        assert _count(uri, Agent, session_id="doomed") == 0
        assert _listed(engine) == {"keeper"}
    finally:
        engine.dispose()
