"""Write-through sink: subtool_calls rows land at CALL time, in the kernel
process, keyed by the identity execute injected — they survive a wedged
kernel because the server-side drain reads the table, not the kernel."""

import pytest

from crow_cli.memory.db import create_database
from crow_cli.memory.models import SubtoolCall
from crow_cli.tools import edit, register
from crow_cli.tools.register import begin_cell, clear, drain, pending
from crow_cli.tools.results import EditError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


@pytest.fixture(autouse=True)
def _clean():
    clear()
    yield
    clear()


@pytest.fixture
def db(tmp_path):
    uri = f"sqlite:///{tmp_path}/crow.db"
    create_database(uri)
    return uri


def _rows(uri):
    engine = create_engine(uri)
    with sessionmaker(engine)() as session:
        rows = session.execute(select(SubtoolCall)).scalars().all()
    engine.dispose()
    return rows


@pytest.mark.asyncio
async def test_completed_edit_writes_row(tmp_path, db):
    target = tmp_path / "f.py"
    target.write_text("x = 1\n")
    begin_cell(session_id="s1", parent_tool_call_id="turn-1/call_a", db_uri=db)

    result = await edit(str(target), "x = 1", "x = 2")

    rows = _rows(db)
    assert len(rows) == 1
    row = rows[0]
    assert row.session_id == "s1"
    assert row.parent_tool_call_id == "turn-1/call_a"
    assert row.tool == "edit"
    assert row.status == "completed"
    assert row.result_kind == "diff"
    assert row.args["file_path"] == str(target)
    assert row.args["old_string"] == "x = 1"
    assert row.acp_payload["path"] == str(target)
    assert row.acp_payload["old_text"] == "x = 1\n"
    assert row.acp_payload["new_text"] == "x = 2\n"
    assert row.emitted == 0
    # in-memory mirror still stands
    assert [e.status for e in pending()] == ["completed"]
    assert result.added == 1


@pytest.mark.asyncio
async def test_failed_edit_writes_failed_row(tmp_path, db):
    target = tmp_path / "f.py"
    target.write_text("x = 1\n")
    begin_cell(session_id="s1", parent_tool_call_id="turn-1/call_a", db_uri=db)

    with pytest.raises(EditError):
        await edit(str(target), "nope", "x = 2")

    rows = _rows(db)
    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert "not found in file" in rows[0].error
    assert rows[0].acp_payload is None


@pytest.mark.asyncio
async def test_no_db_uri_stays_in_memory(tmp_path):
    target = tmp_path / "f.py"
    target.write_text("x = 1\n")
    begin_cell(session_id="s1", parent_tool_call_id="turn-1/call_a")

    await edit(str(target), "x = 1", "x = 2")

    assert len(pending()) == 1


@pytest.mark.asyncio
async def test_bad_db_uri_fails_open(tmp_path):
    """Unwritable DB must not break the tool — warning only."""
    target = tmp_path / "f.py"
    target.write_text("x = 1\n")
    begin_cell(
        session_id="s1",
        parent_tool_call_id="turn-1/call_a",
        db_uri="sqlite:////nonexistent-dir-xyz/crow.db",
    )

    result = await edit(str(target), "x = 1", "x = 2")  # no raise

    assert result.added == 1
    assert len(pending()) == 1


@pytest.mark.asyncio
async def test_cell_seq_captured_when_available(tmp_path, db, monkeypatch):
    target = tmp_path / "f.py"
    target.write_text("x = 1\n")
    monkeypatch.setattr(register, "_ipython_execution_count", lambda: 42)
    begin_cell(session_id="s1", parent_tool_call_id="t/c", db_uri=db)

    await edit(str(target), "x = 1", "x = 2")

    assert _rows(db)[0].cell_seq == 42


@pytest.mark.asyncio
async def test_drain_clears_memory_but_rows_persist(tmp_path, db):
    target = tmp_path / "f.py"
    target.write_text("x = 1\n")
    begin_cell(session_id="s1", parent_tool_call_id="t/c", db_uri=db)
    await edit(str(target), "x = 1", "x = 2")

    entries = drain()

    assert len(entries) == 1
    assert pending() == []
    assert len(_rows(db)) == 1  # rows are the server's queue, not ours
