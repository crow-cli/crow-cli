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


async def test_fs_is_ambient_on_start(mcp_app):
    out = await _call(mcp_app, "print(fs.__module__)")
    assert out.strip() == "crow_cli.tools.fs"


async def test_fs_runs_in_the_kernel(mcp_app, tmp_path):
    """All three modes in a real kernel subprocess (read is to_thread'd,
    glob/search spawn ripgrep) — and the cell's print is all the LLM sees."""
    (tmp_path / "f.py").write_text("def alpha():\n    return 1\n")
    out = await _call(
        mcp_app,
        f"r = await fs('read', {str(tmp_path / 'f.py')!r})\n"
        "print(r.lines, r.shown, r.truncated)\n"
        f"g = await fs('glob', {str(tmp_path)!r}, '*.py')\n"
        f"s = await fs('search', {str(tmp_path)!r}, 'alpha')\n"
        "print(len(g.paths), s.matches[0].line, s.paths == g.paths)",
    )
    assert out.strip().splitlines() == ["2 2 False", "1 1 True"]


async def test_fs_ast_runs_in_the_kernel(mcp_app, tmp_path):
    """ast-grep is a native extension, imported lazily inside the kernel
    subprocess — this tier is the only one that proves it loads there at all
    (a packaging/PyInstaller-shaped failure is invisible in-process)."""
    target = tmp_path / "f.py"
    target.write_text("import os\nos.path.join(a, b)\n")
    out = await _call(
        mcp_app,
        f"s = await fs('ast', {str(tmp_path)!r}, 'os.path.join($A, $B)')\n"
        "print(len(s.matches), s.matches[0].line)\n"
        f"w = await fs('rewrite', {str(tmp_path)!r}, 'os.path.join($A, $B)',"
        " rewrite='Path($A) / $B')\n"
        "print(w.summary)",
    )
    assert out.strip().splitlines() == [
        "1 2",
        "rewrote 1 of 1 parsed file(s), 1 match(es):"
        " os.path.join($A, $B) -> Path($A) / $B",
    ]
    assert target.read_text() == "import os\nPath(a) / b\n"


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


async def test_reload_purges_a_tool_that_is_new_to_the_facade(mcp_app):
    """The purge has to run AFTER the names are bound, not before.

    A tool just added to _LAZY is invisible to the import-if-absent loop at
    the top of reload() — that one reads the RUNNING module's _LAZY — so the
    binding loop at the bottom, which reads the freshly reloaded one, is what
    imports it for the first time. And a first import makes importlib
    setattr(parent, child, module), repopulating the package dict with the
    MODULE object, which shadows __getattr__: pkg.web handed back something
    uncallable while the bare name worked, so only attribute access broke.
    """
    code = (
        "import sys\n"
        "import crow_cli.tools as T\n"
        "del sys.modules['crow_cli.tools.web']\n"
        "T.__dict__.pop('web', None)\n"
        "T._LAZY = {k: v for k, v in T._LAZY.items() if k != 'web'}\n"
        "reload()\n"
        "print('web' in T.__dict__, type(T.web).__name__)\n"
        "print(callable(T.web), getattr(T.web, '__module__', None),"
        " web is T.web)\n"
    )
    out = await _call(mcp_app, code)
    assert out.strip().splitlines() == [
        "False function",
        "True crow_cli.tools.web True",
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


async def test_memory_is_ambient_and_reads_the_injected_database(mcp_app, tmp_path):
    """The kernel reads NO config: crow.db arrives on the identity rail
    execute's prologue sets, and memory() is the tool that consumes it — the
    same database its own call records are written through to, on a second
    (read-write) engine, without the read-only one noticing.

    The engine is cached in a mutable CELL (globals().setdefault) because
    importlib.reload re-executes the source in the existing module dict: a
    module-level `_engine = None` would drop the handle on every mid-cell
    reload() and leak its pool.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from crow_cli.memory import add_message, create_agent, create_database, get_engine
    from crow_cli.memory.models import SubtoolCall

    db_uri = f"sqlite:///{tmp_path}/crow.db"
    create_database(db_uri)
    engine = get_engine(db_uri)
    create_agent(
        engine,
        agent_id="sess-mem-1-1",
        session_id="sess-mem",
        agent_idx=1,
        cwd=str(tmp_path),
        model_identifier="m",
        tool_definitions=[],
        request_params={},
    )
    add_message(engine, "sess-mem-1-1", {"role": "user", "content": "polars in the kernel"})
    engine.dispose()

    code = (
        "print(memory.__module__)\n"
        "import sys\n"
        "M = sys.modules['crow_cli.tools.memory']\n"
        "r = await memory('list')\n"
        "print(r.subject, r.rows, r.total, r.df['session_id'].to_list())\n"
        "engine = M._engine()\n"
        "reload()\n"  # mid-cell: the cached handle must survive it
        "print(M._engine() is engine, M._state['uri'] is not None)\n"
        "s = await memory('search', 'polars')\n"
        "print(s.rows, s.df['role'].to_list(), s.df['excerpt'].to_list())\n"
        "q = await memory('sql', 'select count(*) n from messages')\n"
        "print(q.df['n'].to_list())\n"
        "print(repr(q.df['n'].dtype))"
    )
    async with Client(mcp_app) as client:
        result = await client.call_tool(
            "execute",
            {"code": code},
            meta={
                "cwd": str(tmp_path),
                "session_id": "sess-mem",
                "tool_call_id": "turn-1/call_mem",
                "db_uri": db_uri,
            },
        )
    assert result.is_error is False, result.content
    assert result.content[0].text.strip().splitlines() == [
        "crow_cli.tools.memory",
        "sessions 1 1 ['sess-mem']",
        "True True",
        "1 ['user'] ['polars in the kernel']",
        "[1]",
        "Int64",
    ]

    # Three calls, three rows, in the database the tool was reading: the
    # read-only engine and the write-through sink coexist on one file.
    engine = create_engine(db_uri)
    with sessionmaker(engine)() as session:
        rows = session.execute(select(SubtoolCall)).scalars().all()
        session.expunge_all()
    engine.dispose()
    assert [r.mode for r in rows] == ["list", "search", "sql"]
    assert all(r.tool == "memory" and r.status == "completed" for r in rows)
    assert all(r.parent_tool_call_id == "turn-1/call_mem" for r in rows)
    assert rows[0].result_kind == "memory"
    assert rows[1].acp_payload["subject"] == "polars"


async def test_rlm_depth_rides_the_prologue_and_survives_a_reload(mcp_app, tmp_path):
    """The depth is INJECTED, not derived: the kernel reads no config and the
    model supplies no argument, so this rail is the only way an in-cell rlm
    can know whether it is allowed to delegate. And it has to survive
    reload(), which re-creates the register's identity contextvar."""
    from crow_cli.memory.db import create_database

    db_uri = f"sqlite:///{tmp_path}/crow.db"
    create_database(db_uri)

    code = (
        "from crow_cli.tools import register\n"
        "before = register.rlm_depth()\n"
        "reload()\n"  # mid-cell: the prologue already stamped identity
        "print(before, register.rlm_depth(), register.current_cell().rlm_depth)\n"
    )
    async with Client(mcp_app) as client:
        result = await client.call_tool(
            "execute",
            {"code": code},
            meta={
                "cwd": str(tmp_path),
                "session_id": "sess-depth",
                "tool_call_id": "turn-1/call_d",
                "db_uri": db_uri,
                "rlm_depth": 1,
            },
        )
    assert result.is_error is False, result.content
    assert result.content[0].text.strip() == "1 1 1"


async def test_a_caller_that_sends_no_depth_is_depth_zero(mcp_app):
    """No rlm_depth in _meta — a trunk, or a script driving the server
    directly. Zero is the only safe default: it means "may delegate"."""
    out = await _call(
        mcp_app,
        "from crow_cli.tools import register\nprint(register.rlm_depth())",
    )
    assert out.strip() == "0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
