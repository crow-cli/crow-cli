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
    """The prelude ran: bare `edit` resolves with no import in the cell.
    print() is the channel now — no Out[n] reprs in execute's output."""
    out = await _call(mcp_app, "print(edit.__module__)")
    assert out.strip() == "crow_cli.tools.edit"


async def test_vision_is_ambient_on_start(mcp_app):
    out = await _call(mcp_app, "print(vision.__module__)")
    assert out.strip() == "crow_cli.tools.vision"


async def test_write_is_ambient_on_start(mcp_app):
    out = await _call(mcp_app, "print(write.__module__)")
    assert out.strip() == "crow_cli.tools.write"


async def test_edit_runs_and_registers(mcp_app, tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("one\ntwo\n")
    out = await _call(
        mcp_app, f"r = await edit({str(f)!r}, 'one', 'ONE')\nprint(r.added, r.removed)"
    )
    assert out.strip() == "1 1"
    assert f.read_text().startswith("ONE")

    # The entry sits in kernel memory, stamped and drainable. Identity is
    # None until the per-cell prologue (begin_cell) is wired into execute.
    out2 = await _call(
        mcp_app,
        "from crow_cli.tools.register import drain\n"
        "print([(e.tool, e.status, e.result_kind, e.parent_tool_call_id)"
        " for e in drain()])",
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
        "print([(e.tool, e.status) for e in drain()])",
    )
    assert "('edit', 'failed')" in out2


async def test_edit_ambient_after_reset(mcp_app):
    """Reset goes through get_kernel too — the prelude reruns."""
    await _call(mcp_app, "", reset=True)
    out = await _call(mcp_app, "print(edit.__module__)")
    assert out.strip() == "crow_cli.tools.edit"


async def test_vision_writes_through_from_kernel(mcp_app, tmp_path):
    """vision inside a real kernel: bytes land in the injected images_dir,
    the row holds refs, and the cell's print is all the LLM sees."""

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

    code = (
        f"r = await vision(mode='file', path={str(src)!r})\n"
        "print(r.mime, r.width, r.height)"
    )
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
    assert text.strip() == "image/png 64 48"

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


async def test_reload_is_ambient_on_start(mcp_app):
    """PRELUDE calls reload(): the name is bound, and the tools came from
    it — reload re-resolves them into the kernel's namespace."""
    out = await _call(mcp_app, "print(reload.__module__, edit.__module__)")
    assert out.strip() == "crow_cli.tools crow_cli.tools.edit"


async def test_reload_re_executes_and_purges_the_facade_cache(mcp_app):
    """The trap reload() exists for: importlib.reload re-executes a module
    in its EXISTING dict, so the facade's cached function survives it and
    callers keep running the old code forever."""
    code = (
        "import sys\n"
        "import crow_cli.tools as T\n"
        "before = sys.modules['crow_cli.tools.edit'].edit\n"
        "T.__dict__['edit'] = 'STALE'\n"
        "reload()\n"
        "after = sys.modules['crow_cli.tools.edit'].edit\n"
        "print(before is after, T.__dict__.get('edit') == 'STALE')\n"
        "print(T.edit.__module__, edit is after)"
    )
    out = await _call(mcp_app, code)
    assert out.strip().splitlines() == [
        "False False",
        "crow_cli.tools.edit True",
    ]


async def test_reload_preserves_the_identity_rail(mcp_app, tmp_path):
    """Reloading register re-creates its identity contextvar and drops the
    sink and images_dir the per-cell prologue just set. Without capture-and-
    reapply, a mid-cell reload would silently stop write-through for the
    rest of the cell — no rows, no diffs, no error anywhere."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from crow_cli.memory.db import create_database
    from crow_cli.memory.models import SubtoolCall

    db_uri = f"sqlite:///{tmp_path}/crow.db"
    create_database(db_uri)
    images_dir = tmp_path / "images"
    target = tmp_path / "f.txt"
    target.write_text("one\n")

    code = (
        "from crow_cli.tools import register\n"
        "before = register.current_cell()\n"
        "reload()\n"  # mid-cell: the prologue already stamped identity
        "after = register.current_cell()\n"
        # Not `before == after`: reload re-creates the CellContext class, so
        # dataclass eq fails on class identity. The values are the contract.
        "fields = lambda c: (c.session_id, c.parent_tool_call_id, c.cell_seq,"
        " c.agent_id)\n"
        "print(fields(before) == fields(after), after.parent_tool_call_id,"
        " register._sink_uri is not None, register._images_dir)\n"
        f"r = await edit({str(target)!r}, 'one', 'ONE')\n"
        "print(r.added)"
    )
    async with Client(mcp_app) as client:
        result = await client.call_tool(
            "execute",
            {"code": code},
            meta={
                "cwd": str(tmp_path),
                "session_id": "sess-reload-rail",
                "tool_call_id": "turn-9/call_r",
                "db_uri": db_uri,
                "images_dir": str(images_dir),
            },
        )
    assert result.is_error is False, result.content
    lines = result.content[0].text.strip().splitlines()
    assert lines[0] == f"True turn-9/call_r True {images_dir}"
    assert lines[1] == "1"

    # The edit made AFTER the reload still wrote its row through: the rail
    # survived, which is the whole point of re-applying identity.
    engine = create_engine(db_uri)
    with sessionmaker(engine)() as session:
        rows = session.execute(select(SubtoolCall)).scalars().all()
        session.expunge_all()
    engine.dispose()
    assert len(rows) == 1
    assert rows[0].parent_tool_call_id == "turn-9/call_r"
    assert rows[0].tool == "edit" and rows[0].status == "completed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
