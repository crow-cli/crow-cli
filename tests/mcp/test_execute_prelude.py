"""Zero-day imports: fresh kernels (start AND reset) come up with
crow_cli.tools ambient via the prelude, and the in-kernel subtool register
captures calls made inside cells for the server-side drain.
"""

import pytest
from fastmcp import Client

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mcp_app():
    from crow_cli.mcp.server.app import mcp
    import crow_cli.mcp.execute.main  # noqa: F401 — registers the tool

    return mcp


@pytest.fixture(autouse=True)
def _cleanup_kernels():
    yield
    from crow_cli.mcp.execute.main import shutdown_all

    shutdown_all()


async def _call(mcp_app, code, session_id="prelude-test", reset=False):
    async with Client(mcp_app) as client:
        meta = {"session_id": session_id}
        args = {"code": code}
        if reset:
            args["reset"] = True
        result = await client.call_tool("execute", args, meta=meta)
    return result.content[0].text


async def test_edit_is_ambient_on_start(mcp_app):
    """The prelude ran: bare `edit` resolves with no import in the cell."""
    out = await _call(mcp_app, "edit")
    assert "crow_cli.tools.edit.edit" in out and "EditResult" in out


async def test_vision_is_ambient_on_start(mcp_app):
    out = await _call(mcp_app, "vision")
    assert "crow_cli.tools.vision.vision" in out and "VisionResult" in out


async def test_edit_runs_and_registers(mcp_app, tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("one\ntwo\n")
    out = await _call(mcp_app, f"r = await edit({str(f)!r}, 'one', 'ONE')\nr")
    assert "EditResult" in out and "+1/-1" in out
    assert f.read_text().startswith("ONE")

    # The entry sits in kernel memory, stamped and drainable. Identity is
    # None until the per-cell prologue (begin_cell) is wired into execute.
    out2 = await _call(
        mcp_app,
        "from crow_cli.tools.register import drain\n"
        "[(e.tool, e.status, e.result_kind, e.parent_tool_call_id) for e in drain()]",
    )
    assert "('edit', 'completed', 'diff', None)" in out2


async def test_edit_failure_traceback_and_failed_entry(mcp_app, tmp_path):
    out = await _call(
        mcp_app, f"await edit({str(tmp_path / 'ghost.txt')!r}, 'a', 'b')"
    )
    assert "EditError" in out and "does not exist" in out
    out2 = await _call(
        mcp_app,
        "from crow_cli.tools.register import drain\n"
        "[(e.tool, e.status) for e in drain()]",
    )
    assert "('edit', 'failed')" in out2


async def test_edit_ambient_after_reset(mcp_app):
    """Reset goes through get_kernel too — the prelude reruns."""
    await _call(mcp_app, "", reset=True)
    out = await _call(mcp_app, "edit")
    assert "crow_cli.tools.edit.edit" in out and "EditResult" in out


async def test_identity_rail_writes_through_from_kernel(mcp_app, tmp_path):
    """The kernel process writes a subtool_calls row stamped with the
    identity execute injected via meta; this test process reads it back."""
    from crow_cli.memory.db import create_database
    from crow_cli.memory.models import SubtoolCall
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    db_uri = f"sqlite:///{tmp_path}/crow.db"
    create_database(db_uri)

    target = tmp_path / "f.py"
    target.write_text("x = 1\n")
    code = f"await edit({str(target)!r}, 'x = 1', 'x = 2')"
    async with Client(mcp_app) as client:
        result = await client.call_tool(
            "execute",
            {"code": code},
            meta={
                "cwd": str(tmp_path),
                "session_id": "sess-rail",
                "tool_call_id": "turn-7/call_z",
                "db_uri": db_uri,
            },
        )
    assert result.is_error is False

    engine = create_engine(db_uri)
    with sessionmaker(engine)() as session:
        rows = session.execute(select(SubtoolCall)).scalars().all()
    engine.dispose()

    assert len(rows) == 1
    row = rows[0]
    assert row.session_id == "sess-rail"
    assert row.parent_tool_call_id == "turn-7/call_z"
    assert row.tool == "edit"
    assert row.status == "completed"
    assert row.result_kind == "diff"
    assert row.emitted == 0
    assert target.read_text() == "x = 2\n"


async def test_vision_writes_through_from_kernel(mcp_app, tmp_path):
    """vision inside a real kernel: bytes land in the injected images_dir,
    the row holds refs, and Out[n] shows the plain VisionResult repr."""
    import cv2
    import numpy as np
    from crow_cli.memory.db import create_database
    from crow_cli.memory.models import SubtoolCall
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    db_uri = f"sqlite:///{tmp_path}/crow.db"
    create_database(db_uri)
    images_dir = tmp_path / "images"

    src = tmp_path / "shot.png"
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    frame[:, :] = (255, 0, 0)
    assert cv2.imwrite(str(src), frame)

    code = f"await vision(mode='file', path={str(src)!r})"
    async with Client(mcp_app) as client:
        result = await client.call_tool(
            "execute",
            {"code": code},
            meta={
                "cwd": str(tmp_path),
                "session_id": "sess-vision",
                "tool_call_id": "turn-8/call_v",
                "db_uri": db_uri,
                "images_dir": str(images_dir),
            },
        )
    assert result.is_error is False
    text = result.content[0].text
    assert "VisionResult(image/png, 48x64" in text or "VisionResult" in text

    blobs = list(images_dir.iterdir())
    assert len(blobs) == 1

    engine = create_engine(db_uri)
    with sessionmaker(engine)() as session:
        rows = session.execute(select(SubtoolCall)).scalars().all()
        session.expunge_all()
    engine.dispose()
    assert len(rows) == 1
    row = rows[0]
    assert row.tool == "vision" and row.mode == "file"
    assert row.parent_tool_call_id == "turn-8/call_v"
    assert row.result_kind == "image"
    assert row.llm_images == [{"key": blobs[0].name, "mime": "image/png"}]


async def test_output_capped(mcp_app):
    async with Client(mcp_app) as client:
        result = await client.call_tool(
            "execute",
            {"code": "print('A' * 100_000)"},
            meta={"session_id": "prelude-test"},
        )
    assert result.is_error is False
    text = result.content[0].text
    assert len(text) < 30_000
    assert "chars elided" in text
    assert text.startswith("AAAA")
    assert text.rstrip().endswith("AAAA")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
