"""Integration: tool calls made INSIDE an execute cell are re-emitted to the
ACP client as their OWN tool calls — one synthetic call per subtool row, in
call-record order, shaped exactly like a call the LLM made (kind, title,
locations, rawInput = the args the code passed, content = the diff / image /
error text). The client sees every file the code touched; the LLM sees none
of it, only execute's printed output plus image blocks prepended iff vision
ran.

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
import re

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


def _fetch_rows(db_uri):
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker

    from crow_cli.memory.db import get_engine
    from crow_cli.memory.models import SubtoolCall

    engine = get_engine(db_uri)
    try:
        with sessionmaker(engine)() as session:
            rows = session.execute(select(SubtoolCall)).scalars().all()
            session.expunge_all()
            return rows
    finally:
        engine.dispose()


async def _make_ctx(config, session, conn, turn_id="turn-1"):
    from crow_cli.agent.context import TurnCtx

    return TurnCtx(
        conn=conn, config=config, session=session, turn_id=turn_id, logger=logger
    )


def _tool_call_updates(conn):
    return [
        u
        for u in conn.updates
        if getattr(u, "session_update", None) in ("tool_call", "tool_call_update")
    ]


def _by_id(conn, tool_call_id):
    return [u for u in _tool_call_updates(conn) if u.tool_call_id == tool_call_id]


def _sub_ids_in_order(conn):
    """Synthetic subtool ids, in first-appearance (call-record) order."""
    seen = []
    for u in _tool_call_updates(conn):
        if u.tool_call_id not in seen:
            seen.append(u.tool_call_id)
    return seen


async def test_drain_emits_diff_subtool_and_flips(tmp_path):
    config, session = await make_test_session(tmp_path)
    row_id = _seed_row(config.db_uri)
    conn = FakeConn()
    ctx = await _make_ctx(config, session, conn)

    from crow_cli.agent.tools import _emit_subtool_calls

    llm_blocks = await _emit_subtool_calls(ctx, "turn-1/call_x")

    assert llm_blocks == []

    # The subtool got its OWN call on the wire, shaped like a real edit:
    # pending start (kind, title, location, the args as rawInput) ->
    # in_progress carrying the diff -> completed.
    sub_id = f"turn-1/call_sub{row_id}"
    start, progress, done = _by_id(conn, sub_id)
    assert start.session_update == "tool_call"
    assert start.kind == "edit"
    assert start.status == "pending"
    assert start.title == "edit: /tmp/f.py"
    assert [loc.path for loc in start.locations] == ["/tmp/f.py"]
    assert start.raw_input == {
        "file_path": "/tmp/f.py",
        "old_string": "a",
        "new_string": "b",
    }

    assert progress.session_update == "tool_call_update"
    assert progress.status == "in_progress"
    block = progress.content[0]
    assert block.type == "diff"
    assert block.path == "/tmp/f.py"
    assert block.old_text == "a\n"
    assert block.new_text == "b\n"

    assert done.status == "completed"
    assert done.content is None

    # Nothing rode execute's own id — the diff is the subtool's call.
    assert _by_id(conn, "turn-1/call_x") == []

    # Emitted flipped — a second drain is a no-op.
    assert _fetch_row(config.db_uri, row_id).emitted == 1
    again = await _emit_subtool_calls(ctx, "turn-1/call_x")
    assert again == []
    assert len(_tool_call_updates(conn)) == 3
    await session.close()


async def test_drain_renders_text_and_failed_rows(tmp_path):
    config, session = await make_test_session(tmp_path)
    text_id = _seed_row(
        config.db_uri,
        parent_tool_call_id="turn-1/call_y",
        tool="web",
        mode="fetch",
        result_kind="text",
        acp_payload={"text": "fetched 123 bytes"},
    )
    failed_id = _seed_row(
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

    assert _sub_ids_in_order(conn) == [
        f"turn-1/call_sub{text_id}",
        f"turn-1/call_sub{failed_id}",
    ]

    start, progress, done = _by_id(conn, f"turn-1/call_sub{text_id}")
    assert start.title == "web/fetch"
    assert progress.content[0].type == "content"
    assert progress.content[0].content.type == "text"
    assert progress.content[0].content.text == "fetched 123 bytes"
    assert done.status == "completed"

    start, progress, done = _by_id(conn, f"turn-1/call_sub{failed_id}")
    assert start.kind == "edit"
    assert progress.content[0].content.text == "edit failed: EditError: no match"
    assert done.status == "failed"
    await session.close()


async def test_drain_emits_parallel_subtools_in_row_order(tmp_path):
    """A cell that gathered three subtools wrote three rows (completion
    order, ids assigned at insert); the wire keeps call-record order — one
    synthetic call per row, diffs and images interleaved as the code ran
    them."""
    import base64

    from crow_cli.memory.image_store import FsImageStore
    from crow_cli.memory.messages import image_key

    config, session = await make_test_session(tmp_path)
    raw = b"png-bytes-for-parallel"
    key = image_key(raw, "image/png")
    FsImageStore(tmp_path / "images").put(key, raw)

    row_ids = []
    for i, kind in enumerate(["diff", "image", "diff"]):
        row_ids.append(
            _seed_row(
                config.db_uri,
                parent_tool_call_id="turn-5/call_g",
                tool="vision" if kind == "image" else "edit",
                mode="file",
                result_kind=kind,
                acp_payload=(
                    {"content": "image", "key": key, "mime": "image/png"}
                    if kind == "image"
                    else {
                        "content": "diff",
                        "path": f"/tmp/p{i}.py",
                        "old_text": "a\n",
                        "new_text": "b\n",
                    }
                ),
                llm_images=(
                    [{"key": key, "mime": "image/png"}] if kind == "image" else []
                ),
            )
        )

    conn = FakeConn()
    ctx = await _make_ctx(config, session, conn, turn_id="turn-5")

    from crow_cli.agent.tools import _emit_subtool_calls

    llm_blocks = await _emit_subtool_calls(ctx, "turn-5/call_g")

    assert _sub_ids_in_order(conn) == [f"turn-5/call_sub{r}" for r in row_ids]
    assert len(_tool_call_updates(conn)) == 9  # three beats per call

    # The middle call is the vision one: an image block, kind from the tool.
    start, progress, done = _by_id(conn, f"turn-5/call_sub{row_ids[1]}")
    assert start.title == "vision/file"
    assert progress.content[0].content.type == "image"
    assert done.status == "completed"

    # The two edits carry their diffs.
    for rid, i in ((row_ids[0], 0), (row_ids[2], 2)):
        progress = _by_id(conn, f"turn-5/call_sub{rid}")[1]
        assert progress.content[0].type == "diff"
        assert progress.content[0].path == f"/tmp/p{i}.py"

    # exactly one image block hydrated for the LLM, from the middle row
    assert len(llm_blocks) == 1
    assert base64.b64decode(
        llm_blocks[0]["image_url"]["url"].split(";base64,")[1]
    ) == raw
    await session.close()


async def test_parallel_gather_e2e_kernel_to_client(tmp_path):
    """One cell, asyncio.gather over two edits and a vision: the kernel
    wrote three rows under one parent tcid, the drain put three synthetic
    tool calls on the wire (two edit diffs, one image) while execute's own
    call carried only its printed output, and the image block was prepended
    to the LLM's view — the whole pipeline holds up under parallel calls."""
    import cv2
    import numpy as np

    from crow_cli.mcp.server.app import mcp

    import crow_cli.mcp.execute.main  # noqa: F401 — registers the tool

    config, session = await make_test_session(tmp_path)
    await session.add_message({"role": "user", "content": "do three things"})

    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("one\n")
    b.write_text("two\n")
    src = tmp_path / "shot.png"
    frame = np.zeros((24, 32, 3), dtype=np.uint8)
    frame[:, :] = (1, 2, 3)
    assert cv2.imwrite(str(src), frame)

    code = (
        "import asyncio\n"
        f"ra, rb, rv = await asyncio.gather(\n"
        f"    edit({str(a)!r}, 'one', 'ONE'),\n"
        f"    edit({str(b)!r}, 'two', 'TWO'),\n"
        f"    vision(mode='file', path={str(src)!r}),\n"
        ")\n"
        "print(ra.added + rb.added, rv.width)"
    )
    turn1 = [
        tool_call_chunk(
            0, id="call_g1", name="execute", args=json.dumps({"code": code})
        ),
        usage_chunk(30),
    ]
    turn2 = [content_chunk("Done, three things."), usage_chunk(10)]
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

    parent = "turn-1/call_g1"
    exec_updates = _by_id(conn, parent)
    assert len(exec_updates) == 3  # pending, in_progress, completed
    done = exec_updates[-1]
    assert done.status == "completed"
    # execute's own completion carries ONLY its printed output — the diffs
    # went out as their own tool calls.
    assert [c.type for c in done.content] == ["content"]
    assert done.content[0].content.type == "text"
    assert "2 32" in done.content[0].content.text

    sub_ids = [i for i in _sub_ids_in_order(conn) if i != parent]
    assert len(sub_ids) == 3
    assert all(re.fullmatch(r"turn-1/call_sub\d+", i) for i in sub_ids), sub_ids
    subs = [u for u in _tool_call_updates(conn) if u.tool_call_id in sub_ids]
    assert len(subs) == 9

    for tid in sub_ids:
        start, progress, final = _by_id(conn, tid)
        assert [start.status, progress.status, final.status] == [
            "pending",
            "in_progress",
            "completed",
        ]
        assert start.raw_input, "the args the code passed must ride rawInput"

    starts = [_by_id(conn, tid)[0] for tid in sub_ids]
    assert sorted(s.kind for s in starts) == ["edit", "edit", "other"]

    diffs = [
        c
        for tid in sub_ids
        for c in (_by_id(conn, tid)[1].content or [])
        if c.type == "diff"
    ]
    assert sorted(d.path for d in diffs) == sorted([str(a), str(b)])
    assert {d.new_text for d in diffs} == {"ONE\n", "TWO\n"}

    images = [
        c.content
        for tid in sub_ids
        for c in (_by_id(conn, tid)[1].content or [])
        if c.type == "content" and c.content.type == "image"
    ]
    assert len(images) == 1

    # The edit calls carry the code's own arguments.
    edit_inputs = sorted(
        (s.raw_input["file_path"], s.raw_input["new_string"])
        for s in starts
        if s.kind == "edit"
    )
    assert edit_inputs == [(str(a), "ONE"), (str(b), "TWO")]

    # The row set: three, one parent, all emitted.
    rows = _fetch_rows(config.db_uri)
    assert len(rows) == 3
    assert {r.parent_tool_call_id for r in rows} == {parent}
    assert all(r.emitted == 1 for r in rows)
    assert sorted(r.tool for r in rows) == ["edit", "edit", "vision"]

    # LLM: image block prepended to what the cell printed ("2 32").
    await session.close()
    loaded = await AgentSession.load(AGENT_ID, memory_path=config.db_uri)
    tool_msgs = [m for m in loaded.messages if m["role"] == "tool"]
    content = tool_msgs[0]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "image_url"
    text = "".join(bl.get("text", "") for bl in content if bl["type"] == "text")
    assert "2 32" in text


async def test_drain_ignores_other_parents(tmp_path):
    config, session = await make_test_session(tmp_path)
    _seed_row(config.db_uri, parent_tool_call_id="turn-1/call_other")
    conn = FakeConn()
    ctx = await _make_ctx(config, session, conn)

    from crow_cli.agent.tools import _emit_subtool_calls

    await _emit_subtool_calls(ctx, "turn-1/call_x")

    assert conn.updates == []
    await session.close()


async def test_drain_emits_image_block_and_hydrates_llm(tmp_path):
    """Image rows: the client gets its own tool call wrapping a real ACP
    image block (bytes hydrated from the ImageStore by ref), the caller gets
    OpenAI image_url blocks for the LLM — the row itself never carried
    bytes."""
    import base64

    from crow_cli.memory.image_store import FsImageStore
    from crow_cli.memory.messages import image_key

    config, session = await make_test_session(tmp_path)
    store = FsImageStore(tmp_path / "images")
    raw = b"\x89PNG-fake-but-real-bytes"
    key = image_key(raw, "image/png")
    store.put(key, raw)

    row_id = _seed_row(
        config.db_uri,
        tool="vision",
        mode="file",
        args={"mode": "file", "path": "/tmp/shot.png"},
        result_kind="image",
        acp_payload={"content": "image", "key": key, "mime": "image/png"},
        llm_images=[{"key": key, "mime": "image/png"}],
    )
    conn = FakeConn()
    ctx = await _make_ctx(config, session, conn)

    from crow_cli.agent.tools import _emit_subtool_calls

    llm_blocks = await _emit_subtool_calls(ctx, "turn-1/call_x")

    start, progress, done = _by_id(conn, f"turn-1/call_sub{row_id}")
    assert start.title == "vision/file"
    assert start.raw_input == {"mode": "file", "path": "/tmp/shot.png"}
    wrapper = progress.content[0]
    assert wrapper.type == "content"
    block = wrapper.content
    assert block.type == "image"
    assert block.mime_type == "image/png"
    assert base64.b64decode(block.data) == raw
    assert done.status == "completed"

    # LLM channel: hydrated image_url block, data URL and all.
    assert llm_blocks == [
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{base64.b64encode(raw).decode()}"
            },
        }
    ]
    await session.close()


async def test_drain_image_missing_blob_warns_not_raises(tmp_path):
    """A dead ref must not take the drain down: the call still goes out
    (status completed, no content) and the LLM gets no image block."""
    config, session = await make_test_session(tmp_path)
    row_id = _seed_row(
        config.db_uri,
        tool="vision",
        mode="file",
        result_kind="image",
        acp_payload={"content": "image", "key": "deadbeef.png", "mime": "image/png"},
        llm_images=[{"key": "deadbeef.png", "mime": "image/png"}],
    )
    conn = FakeConn()
    ctx = await _make_ctx(config, session, conn)

    from crow_cli.agent.tools import _emit_subtool_calls

    llm_blocks = await _emit_subtool_calls(ctx, "turn-1/call_x")

    assert llm_blocks == []
    start, progress, done = _by_id(conn, f"turn-1/call_sub{row_id}")
    assert start.status == "pending"
    assert progress.content is None
    assert done.status == "completed"
    await session.close()


async def test_execute_e2e_kernel_writes_and_loop_emits(tmp_path):
    """Full circle: LLM calls execute -> real kernel runs `await edit(...)`
    -> kernel writes the row through -> react loop drains it -> the client
    saw an edit tool call with the diff and the code's own args, while the
    LLM's tool message carries only what the cell printed."""
    from crow_cli.mcp.server.app import mcp

    import crow_cli.mcp.execute.main  # noqa: F401 — registers the tool

    config, session = await make_test_session(tmp_path)
    await session.add_message({"role": "user", "content": "fix the file"})

    target = tmp_path / "f.py"
    target.write_text("x = 1\n")
    code = (
        f"r = await edit({str(target)!r}, 'x = 1', 'x = 2')\n"
        "print(r.added, r.removed)"
    )
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

    parent = "turn-1/call_e1"
    exec_updates = _by_id(conn, parent)
    assert len(exec_updates) == 3  # pending, in_progress, completed
    done = exec_updates[-1]
    assert done.status == "completed"
    assert [c.type for c in done.content] == ["content"]
    assert "1 1" in done.content[0].content.text

    # The in-cell edit is its own call on the wire — a real edit tool call
    # as far as the client is concerned.
    rows = _fetch_rows(config.db_uri)
    assert len(rows) == 1
    assert rows[0].parent_tool_call_id == parent
    assert rows[0].session_id == SESSION_ID
    assert rows[0].emitted == 1

    sub_id = f"turn-1/call_sub{rows[0].id}"
    start, progress, final = _by_id(conn, sub_id)
    assert start.session_update == "tool_call"
    assert start.kind == "edit"
    assert start.title == f"edit: {target}"
    assert [loc.path for loc in start.locations] == [str(target)]
    assert start.raw_input == {
        "file_path": str(target),
        "old_string": "x = 1",
        "new_string": "x = 2",
        "replace_all": False,
    }
    block = progress.content[0]
    assert block.type == "diff"
    assert block.path == str(target)
    assert block.old_text == "x = 1\n"
    assert block.new_text == "x = 2\n"
    assert final.status == "completed"

    # Nothing else on the wire but execute and its one subtool.
    assert _sub_ids_in_order(conn) == [parent, sub_id]

    # The LLM saw the edit's numbers in its tool message — because the
    # CELL PRINTED them, not because a repr rode along.
    await session.close()
    loaded = await AgentSession.load(AGENT_ID, memory_path=config.db_uri)
    tool_msgs = [m for m in loaded.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert "1 1" in str(tool_msgs[0]["content"])


async def test_vision_e2e_kernel_stores_and_loop_hydrates(tmp_path):
    """Full circle for the image channel: LLM calls execute -> real kernel
    runs `await vision(mode='file')` -> bytes land in the session
    ImageStore, row holds refs -> drain emits the vision call with an ACP
    image block AND prepends a hydrated image_url block to the LLM's tool
    message."""
    import cv2
    import numpy as np

    from crow_cli.mcp.server.app import mcp

    import crow_cli.mcp.execute.main  # noqa: F401 — registers the tool

    config, session = await make_test_session(tmp_path)
    await session.add_message({"role": "user", "content": "look at this"})

    src = tmp_path / "shot.png"
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    frame[:, :] = (0, 255, 0)
    assert cv2.imwrite(str(src), frame)

    code = (
        f"r = await vision(mode='file', path={str(src)!r})\n"
        "print(r.mime, r.width, r.height)"
    )
    turn1 = [
        tool_call_chunk(
            0, id="call_v1", name="execute", args=json.dumps({"code": code})
        ),
        usage_chunk(30),
    ]
    turn2 = [content_chunk("It is green."), usage_chunk(10)]
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

    parent = "turn-1/call_v1"
    exec_updates = _by_id(conn, parent)
    assert len(exec_updates) == 3
    done = exec_updates[-1]
    assert done.status == "completed"
    # execute's own content is just the printed text — the image went out
    # on the vision call.
    assert [c.type for c in done.content] == ["content"]
    assert done.content[0].content.type == "text"
    assert "image/png 64 48" in done.content[0].content.text

    rows = _fetch_rows(config.db_uri)
    assert len(rows) == 1
    assert rows[0].result_kind == "image"
    assert rows[0].emitted == 1

    start, progress, final = _by_id(conn, f"turn-1/call_sub{rows[0].id}")
    assert start.title == "vision/file"
    # rawInput is the bound call — what the code passed, plus signature
    # defaults the register applied.
    assert start.raw_input["mode"] == "file"
    assert start.raw_input["path"] == str(src)
    block = progress.content[0].content
    assert block.type == "image"
    assert block.mime_type == "image/png"
    assert final.status == "completed"

    # The blob is in the session ImageStore under the content-addressed key.
    images_dir = tmp_path / "images"
    blobs = list(images_dir.iterdir())
    assert len(blobs) == 1
    from crow_cli.memory.messages import image_key

    raw = blobs[0].read_bytes()
    assert blobs[0].name == image_key(raw, "image/png")
    assert rows[0].llm_images == [{"key": blobs[0].name, "mime": "image/png"}]

    # The LLM's tool message: execute's output UNMODIFIED, except the
    # hydrated image_url block PREPENDED because vision ran — the one and
    # only LLM-side modification.
    await session.close()
    loaded = await AgentSession.load(AGENT_ID, memory_path=config.db_uri)
    tool_msgs = [m for m in loaded.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    content = tool_msgs[0]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "image_url"
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
    text = "".join(b.get("text", "") for b in content if b["type"] == "text")
    assert "image/png 64 48" in text
