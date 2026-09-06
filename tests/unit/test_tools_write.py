"""write — create/overwrite, Python-shaped: EditResult (a write IS a diff),
WriteError raised on failure, register + write-through like every subtool."""

import pytest

from crow_cli.memory.db import create_database
from crow_cli.memory.models import SubtoolCall
from crow_cli.tools import write
from crow_cli.tools.register import begin_cell, clear, pending
from crow_cli.tools.results import EditResult
from crow_cli.tools.write import WriteError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


@pytest.fixture(autouse=True)
def _clean():
    clear()
    yield
    clear()


@pytest.mark.asyncio
async def test_write_new_file(tmp_path):
    target = tmp_path / "sub" / "new.txt"
    result = await write(str(target), "hello\nworld\n")

    assert isinstance(result, EditResult)
    assert result
    assert target.read_text() == "hello\nworld\n"
    assert result.old_text == ""
    assert result.new_text == "hello\nworld\n"
    assert result.added == 2 and result.removed == 0
    assert result.result_kind == "diff"
    assert "+hello" in result.diff
    # parent dirs created
    assert target.parent.is_dir()


@pytest.mark.asyncio
async def test_write_overwrite_diffs_against_old(tmp_path):
    target = tmp_path / "f.txt"
    target.write_text("one\ntwo\n")
    result = await write(str(target), "one\nTWO\nthree\n")

    assert target.read_text() == "one\nTWO\nthree\n"
    assert result.old_text == "one\ntwo\n"
    assert result.added == 2 and result.removed == 1
    assert "-two" in result.diff and "+TWO" in result.diff


@pytest.mark.asyncio
async def test_write_acp_payload(tmp_path):
    target = tmp_path / "f.txt"
    target.write_text("old\n")
    result = await write(str(target), "new\n")
    assert result.acp_payload() == {
        "content": "diff",
        "path": str(target),
        "old_text": "old\n",
        "new_text": "new\n",
    }
    assert result.llm_images() == []


@pytest.mark.asyncio
async def test_write_directory_raises(tmp_path):
    with pytest.raises(WriteError, match="directory"):
        await write(str(tmp_path), "content")


@pytest.mark.asyncio
async def test_write_records_entry(tmp_path):
    begin_cell(session_id="s1", parent_tool_call_id="t/c")
    await write(str(tmp_path / "f.txt"), "x")
    entries = pending()
    assert [(e.tool, e.mode, e.status, e.result_kind) for e in entries] == [
        ("write", None, "completed", "diff")
    ]


@pytest.mark.asyncio
async def test_write_failure_records_failed(tmp_path):
    begin_cell(session_id="s1", parent_tool_call_id="t/c")
    with pytest.raises(WriteError):
        await write(str(tmp_path), "x")
    assert [(e.tool, e.status) for e in pending()] == [("write", "failed")]
    assert "directory" in pending()[0].error


@pytest.mark.asyncio
async def test_write_through_row(tmp_path):
    db_uri = f"sqlite:///{tmp_path}/crow.db"
    create_database(db_uri)
    begin_cell(session_id="s1", parent_tool_call_id="turn-2/call_w", db_uri=db_uri)

    target = tmp_path / "f.txt"
    await write(str(target), "content\n")

    engine = create_engine(db_uri)
    with sessionmaker(engine)() as session:
        rows = session.execute(select(SubtoolCall)).scalars().all()
        session.expunge_all()
    engine.dispose()
    assert len(rows) == 1
    row = rows[0]
    assert row.tool == "write"
    assert row.status == "completed"
    assert row.result_kind == "diff"
    assert row.parent_tool_call_id == "turn-2/call_w"
    assert row.acp_payload["new_text"] == "content\n"
    assert row.emitted == 0


@pytest.mark.asyncio
async def test_write_preserves_crlf_and_records_a_faithful_preimage(tmp_path):
    """newline="" both ways. The write used to translate every \\n to
    os.linesep (which on Windows turns a CRLF file's endings into \\r\\r\\n),
    and the preimage read used the default translation, so crow.db's undo log
    held an LF-normalized copy of a CRLF file — restoring it would reformat
    the very file it claims to undo."""
    target = tmp_path / "f.toml"
    target.write_bytes(b'x = "OLD"\r\ny = 2\r\n')

    r = await write(str(target), 'x = "NEW"\r\ny = 2\r\n')

    assert target.read_bytes() == b'x = "NEW"\r\ny = 2\r\n'
    assert r.old_text == 'x = "OLD"\r\ny = 2\r\n'
    assert r.new_text == 'x = "NEW"\r\ny = 2\r\n'
    # The diff renders identically either way — splitlines() strips the \r —
    # so the diff was never going to catch this.
    assert r.diff.splitlines() == [
        "--- a/f.toml",
        "+++ b/f.toml",
        "@@ -1,2 +1,2 @@",
        '-x = "OLD"',
        '+x = "NEW"',
        " y = 2",
    ]
