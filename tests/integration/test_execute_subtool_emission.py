"""Integration: tool calls made INSIDE an execute cell are re-emitted to the
ACP client as sibling tool calls under execute's window.

Two levels, both with REAL persistence (sqlite) and the real drain
(_emit_subtool_calls):
- focused: seed subtool_calls rows as the kernel's write-through would, run
  the drain against a real TurnCtx + FakeConn, assert the wire updates and
  the emitted flip (idempotent — a second drain emits nothing);
- e2e: scripted LLM calls execute with `await edit(...)` code through the
  real MCP tool and a real kernel subprocess — the kernel writes the row,
  the react loop drains it, the client sees an edit tool call with a diff.
"""

import json
import logging

import pytest
from fastmcp import Client

from crow_cli.agent.react import react_loop
from crow_cli.agent.session import AgentSession

from tests.integration.test_react_loop_cancel_integrity import (
    AGENT_ID,
    SESSION_ID,
    FakeConn,
    content_chunk,
    drive_react_loop,
    make_test_session,
    tool_call_chunk,
    usage_chunk,
)
from tests.integration.test_react_loop_tool_round import MultiTurnLLM

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _cleanup_kernels():
    yield
    from crow_cli.mcp.execute.main import shutdown_all

    shutdown_all()


def _seed_row(db_uri, **overrides):
    """Insert a subtool_calls row the way the kernel's write-through does."""
    from crow_cli.memory.db import create_database, get_engine
    from crow_cli.memory.models import SubtoolCall

    create_database(db_uri)
    values = {
        "session_id": SESSION_ID,
        "agent_id": AGENT_ID,
        "parent_tool_call_id": "turn-1/call_x",
        "cell_seq": 3,
        "tool": "edit",
        "mode": None,
        "args": {"file_path": "/tmp/f.py", "old_string": "a", "new_string": "b"},
        "status": "completed",
        "result_kind": "diff",
        "acp_payload": {
            "content": "diff",
            "path": "/tmp/f.py",
            "old_text": "a\n",
            "new_text": "b\n",
            "diff": "--- \n+++ \n-a\n+b\n",
        },
        "llm_images": [],
        "error": None,
        "emitted": 0,
    }
    values.update(overrides)
    engine = get_engine(db_uri)
    try:
        with engine.begin() as conn:
            row_id = conn.execute(
                SubtoolCall.__table__.insert().values(**values)
            ).inserted_primary_key[0]
    finally:
        engine.dispose()
    return row_id


def _fetch_row(db_uri, row_id):
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker

    from crow_cli.memory.db import get_engine
    from crow_cli.memory.models import SubtoolCall

    engine = get_engine(db_uri)
    try:
        with sessionmaker(engine)() as session:
            row = session.execute(
                select(SubtoolCall).where(SubtoolCall.id == row_id)
            ).scalar_one()
            session.expunge(row)  # keep attributes readable after close
            return row
    finally:
        engine.dispose()


async def _make_ctx(config, session, conn, turn_id="turn-1"):
    from crow_cli.agent.context import TurnCtx

    return TurnCtx(
        conn=conn, config=config, session=session, turn_id=turn_id, logger=logger
    )


async def test_drain_emits_diff_subtool_and_flips(tmp_path):
    config, session = await make_test_session(tmp_path)
    row_id = _seed_row(config.db_uri)
    conn = FakeConn()
    ctx = await _make_ctx(config, session, conn)

    from crow_cli.agent.tools import _emit_subtool_calls

    await _emit_subtool_calls(ctx, "turn-1/call_x")

    # Two updates: sibling tool_call start, then completion with the diff.
    assert len(conn.updates) == 2, conn.updates
    start, done = conn.updates
    sub_id = f"turn-1/call_x/sub:{row_id}"
    assert start.session_update == "tool_call"
    assert start.tool_call_id == sub_id
    assert start.kind == "edit"
    assert start.title == "edit: /tmp/f.py"
    assert start.status == "in_progress"
    assert done.tool_call_id == sub_id
    assert done.status == "completed"
    assert len(done.content) == 1
    block = done.content[0]
    assert block.type == "diff"
    assert block.path == "/tmp/f.py"
    assert block.old_text == "a\n"
    assert block.new_text == "b\n"

    # Emitted flipped — a second drain is a no-op.
    assert _fetch_row(config.db_uri, row_id).emitted == 1
    conn.updates.clear()
    await _emit_subtool_calls(ctx, "turn-1/call_x")
    assert conn.updates == []
    await session.close()


async def test_drain_emits_failed_and_non_diff_rows(tmp_path):
    config, session = await make_test_session(tmp_path)
    ok_id = _seed_row(
        config.db_uri,
        parent_tool_call_id="turn-1/call_y",
        tool="web",
        mode="fetch",
        result_kind="text",
        acp_payload=None,
    )
    bad_id = _seed_row(
        config.db_uri,
        parent_tool_call_id="turn-1/call_y",
        status="failed",
        result_kind="text",
        acp_payload=None,
        error="EditError: no match",
    )
    conn = FakeConn()
    ctx = await _make_ctx(config, session, conn)

    from crow_cli.agent.tools import _emit_subtool_calls

    await _emit_subtool_calls(ctx, "turn-1/call_y")

    assert len(conn.updates) == 4
    s1, d1, s2, d2 = conn.updates
    assert s1.tool_call_id == f"turn-1/call_y/sub:{ok_id}"
    assert s1.title == "web/fetch"
    assert s1.kind == "fetch"
    assert d1.status == "completed"
    assert d1.content == []
    assert s2.tool_call_id == f"turn-1/call_y/sub:{bad_id}"
    assert d2.status == "failed"
    await session.close()


async def test_drain_ignores_other_parents(tmp_path):
    config, session = await make_test_session(tmp_path)
    _seed_row(config.db_uri, parent_tool_call_id="turn-1/call_other")
    conn = FakeConn()
    ctx = await _make_ctx(config, session, conn)

    from crow_cli.agent.tools import _emit_subtool_calls

    await _emit_subtool_calls(ctx, "turn-1/call_x")

    assert conn.updates == []
    await session.close()


async def test_execute_e2e_kernel_writes_and_loop_emits(tmp_path):
    """Full circle: LLM calls execute -> real kernel runs `await edit(...)`
    -> kernel writes the row through -> react loop drains it -> FakeConn saw
    a sibling edit tool call with a real diff, and the LLM's tool message
    carries the EditResult repr."""
    from crow_cli.mcp.server.app import mcp

    import crow_cli.mcp.execute.main  # noqa: F401 — registers the tool

    config, session = await make_test_session(tmp_path)
    await session.add_message({"role": "user", "content": "fix the file"})

    target = tmp_path / "f.py"
    target.write_text("x = 1\n")
    code = f"await edit({str(target)!r}, 'x = 1', 'x = 2')"
    turn1 = [
        tool_call_chunk(
            0, id="call_e1", name="execute", args=json.dumps({"code": code})
        ),
        usage_chunk(30),
    ]
    turn2 = [content_chunk("Fixed it."), usage_chunk(10)]
    llm = MultiTurnLLM([turn1, turn2])
    conn = FakeConn()

    async with Client(mcp) as mcp_client:
        gen = react_loop(
            conn=conn,
            config=config,
            client_capabilities=None,
            turn_id="turn-1",
            mcp_clients={SESSION_ID: mcp_client},
            llm=llm,
            tools=[],
            sessions={AGENT_ID: session},
            agent_id=AGENT_ID,
            state_accumulators={},
            logger=logger,
            hooks=[],
        )
        events, stop = await drive_react_loop(gen)

    assert stop == "done", events
    assert target.read_text() == "x = 2\n"

    # The sibling edit tool call rode execute's window, BEFORE execute's
    # own completion update.
    parent = "turn-1/call_e1"
    subs = [u for u in conn.updates if getattr(u, "tool_call_id", "").startswith(parent + "/sub:")]
    assert len(subs) == 2, conn.updates
    start, done = subs
    assert start.session_update == "tool_call"
    assert start.kind == "edit"
    assert start.title == f"edit: {target}"
    assert done.status == "completed"
    block = done.content[0]
    assert block.type == "diff"
    assert block.new_text == "x = 2\n"
    exec_updates = [u for u in conn.updates if getattr(u, "tool_call_id", None) == parent]
    assert conn.updates.index(done) < conn.updates.index(exec_updates[-1])

    # The row was written by the KERNEL process and flipped by the drain.
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker

    from crow_cli.memory.db import get_engine
    from crow_cli.memory.models import SubtoolCall

    engine = get_engine(config.db_uri)
    with sessionmaker(engine)() as dbsession:
        rows = dbsession.execute(select(SubtoolCall)).scalars().all()
        dbsession.expunge_all()
    engine.dispose()
    assert len(rows) == 1
    assert rows[0].parent_tool_call_id == parent
    assert rows[0].session_id == SESSION_ID
    assert rows[0].emitted == 1

    # The LLM saw the EditResult in its tool message.
    await session.close()
    loaded = await AgentSession.load(AGENT_ID, memory_path=config.db_uri)
    tool_msgs = [m for m in loaded.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert "EditResult" in str(tool_msgs[0]["content"])
