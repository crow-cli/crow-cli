"""crow_cli.tools.edit — the Python-shaped contract: EditResult on success,
raised EditError on failure (never "Error: ..." strings), and register
entries carrying the three-fold split (args, ACP payload, LLM image refs,
cell identity stamped at call time).
"""

import pytest

from crow_cli.tools import edit, register
from crow_cli.tools.results import EditError, EditResult

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _clean_register():
    register.clear()
    yield
    register.clear()


async def test_success_returns_edit_result(tmp_path):
    f = tmp_path / "f.py"
    f.write_text("x = 1\n")
    r = await edit(str(f), "x = 1", "x = 2")
    assert isinstance(r, EditResult)
    assert r  # truthy on success
    assert (r.added, r.removed) == (1, 1)
    assert f.read_text() == "x = 2\n"
    assert r.added == 1 and r.removed == 1


async def test_fuzzy_indentation_match(tmp_path):
    """The engine's level-5 matcher: wrong indentation in old_string still lands."""
    f = tmp_path / "f.py"
    f.write_text("def g():\n    return 1\n")
    await edit(str(f), "def g():\n        return 1", "def g():\n    return 2")
    assert "return 2" in f.read_text()


async def test_missing_file_raises(tmp_path):
    with pytest.raises(EditError, match="does not exist"):
        await edit(str(tmp_path / "nope.py"), "a", "b")


async def test_no_match_raises(tmp_path):
    f = tmp_path / "f.py"
    f.write_text("hello\n")
    with pytest.raises(EditError, match="not found"):
        await edit(str(f), "absent", "b")


async def test_multiple_matches_raises(tmp_path):
    f = tmp_path / "f.py"
    f.write_text("dup\ndup\ndup\n")
    with pytest.raises(EditError, match="found 3 times"):
        await edit(str(f), "dup", "one")


async def test_replace_all(tmp_path):
    f = tmp_path / "f.py"
    f.write_text("dup\ndup\n")
    r = await edit(str(f), "dup", "one", replace_all=True)
    assert f.read_text() == "one\none\n"
    assert r.added == 2


async def test_register_entry_completed(tmp_path):
    f = tmp_path / "f.py"
    f.write_text("a\n")
    register.begin_cell(
        session_id="s-1", parent_tool_call_id="tcid-9", cell_seq=3
    )
    await edit(str(f), "a", "b")
    [e] = register.drain()
    assert (e.tool, e.status, e.result_kind) == ("edit", "completed", "diff")
    assert (e.session_id, e.parent_tool_call_id, e.cell_seq) == (
        "s-1",
        "tcid-9",
        3,
    )
    assert e.acp_payload == {
        "content": "diff",
        "path": e.acp_payload["path"],
        "old_text": "a\n",
        "new_text": "b\n",
    }
    assert e.args["old_string"] == "a" and e.args["replace_all"] is False
    assert e.llm_images == [] and e.error is None
    assert register.pending() == []  # drain removed it


async def test_register_entry_failed(tmp_path):
    register.begin_cell(
        session_id="s-1", parent_tool_call_id="tcid-9", cell_seq=4
    )
    with pytest.raises(EditError):
        await edit(str(tmp_path / "ghost.py"), "a", "b")
    [e] = register.drain()
    assert (e.status, e.result_kind) == ("failed", "error")
    assert "does not exist" in e.error
    assert e.parent_tool_call_id == "tcid-9" and e.cell_seq == 4
    assert e.acp_payload is None


async def test_usable_without_cell_context(tmp_path):
    """Plain Python, no execute identity — the tools work anywhere."""
    f = tmp_path / "f.py"
    f.write_text("a\n")
    r = await edit(str(f), "a", "b")
    assert isinstance(r, EditResult)
    [e] = register.drain()
    assert e.session_id is None and e.parent_tool_call_id is None


async def test_a_crlf_file_keeps_its_line_endings(tmp_path):
    """The read used the default newline= translation and the write handed the
    result back, so ONE edit to a CRLF file silently reformatted all of it —
    with a diff showing a single changed line, because unified_diff is fed
    splitlines(), which strips \\r from both sides. The model's old_string
    arrives with bare \\n (it saw the file through read, which normalizes for
    display), so the match and the replacement are translated into the file's
    own endings rather than the file being translated into theirs."""
    f = tmp_path / "f.toml"
    f.write_bytes(b'x = "OLD"\r\ny = 2\r\nz = 3\r\n')

    r = await edit(str(f), 'x = "OLD"', 'x = "NEW"')

    assert f.read_bytes() == b'x = "NEW"\r\ny = 2\r\nz = 3\r\n'
    assert r.old_text == 'x = "OLD"\r\ny = 2\r\nz = 3\r\n'
    assert r.new_text == 'x = "NEW"\r\ny = 2\r\nz = 3\r\n'


async def test_a_multiline_crlf_edit_inserts_crlf_lines(tmp_path):
    """The replacement needs the same translation as the match, or the edit
    splices LF lines into a CRLF file and leaves it mixed."""
    f = tmp_path / "f.toml"
    f.write_bytes(b"x = 1\r\ny = 2\r\nz = 3\r\n")

    await edit(str(f), "x = 1\ny = 2", "x = 9\ny = 8\nw = 7")

    assert f.read_bytes() == b"x = 9\r\ny = 8\r\nw = 7\r\nz = 3\r\n"


async def test_a_mixed_ending_replacement_does_not_double_up(tmp_path):
    """The translation normalizes before it converts, so a new_string that
    already carries some CRLF cannot come out as \\r\\r\\n."""
    f = tmp_path / "f.toml"
    f.write_bytes(b"x = 1\r\ny = 2\r\n")

    await edit(str(f), "x = 1", "a = 1\r\nb = 2")

    assert f.read_bytes() == b"a = 1\r\nb = 2\r\ny = 2\r\n"


async def test_an_lf_file_is_untouched_by_the_ending_translation(tmp_path):
    f = tmp_path / "f.toml"
    f.write_bytes(b"a = OLD\nb = 2\n")

    r = await edit(str(f), "a = OLD", "a = NEW", replace_all=True)

    assert f.read_bytes() == b"a = NEW\nb = 2\n"
    assert r.old_text == "a = OLD\nb = 2\n"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
