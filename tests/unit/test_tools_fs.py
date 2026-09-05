"""fs — read/glob/search, Python-shaped: real result objects, FsError raised
on failure, register + write-through like every subtool.

No mocks: real files on disk and the real ripgrep binary, which is the only
way the gitignore and cwd-relative-glob behaviour gets tested at all.
"""

import subprocess

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from crow_cli.memory.db import create_database
from crow_cli.memory.models import SubtoolCall
from crow_cli.tools import fs
from crow_cli.tools.register import begin_cell, clear, pending
from crow_cli.tools.results import (
    FileResult,
    FsError,
    GlobResult,
    SearchMatch,
    SearchResult,
)


@pytest.fixture(autouse=True)
def _clean():
    clear()
    yield
    clear()


def _tree(root):
    """src/a.py, src/b.txt, tests/c.py, plus noise that must never match."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "a.py").write_text("def alpha():\n    return 1\n")
    (root / "src" / "b.txt").write_text("beta\n")
    (root / "tests" / "c.py").write_text("def gamma():\n    return 3\n")
    return root


# --- read ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_returns_numbered_window(tmp_path):
    target = tmp_path / "f.py"
    target.write_text("one\ntwo\nthree\n")
    r = await fs("read", str(target))

    assert isinstance(r, FileResult) and r
    assert r.content == "one\ntwo\nthree"
    assert r.text.splitlines() == ["1→one", "2→two", "3→three"]
    assert (r.lines, r.offset, r.shown, r.truncated) == (3, 1, 3, False)
    assert r.result_kind == "read"
    assert r.acp_payload() == {
        "content": "read",
        "path": str(target),
        "text": r.text,
    }
    assert r.llm_images() == []


@pytest.mark.asyncio
async def test_read_offset_and_limit_page(tmp_path):
    target = tmp_path / "f.txt"
    target.write_text("\n".join(str(i) for i in range(1, 11)) + "\n")
    r = await fs("read", str(target), offset=3, limit=4)

    assert r.content == "3\n4\n5\n6"
    assert (r.offset, r.shown, r.lines, r.truncated) == (3, 4, 10, True)
    assert r.text.splitlines()[0] == "3→3"
    assert "showing lines 3-6 of 10 total" in r.text


@pytest.mark.asyncio
async def test_read_past_eof_is_empty_not_truncated(tmp_path):
    target = tmp_path / "f.txt"
    target.write_text("one\ntwo\n")
    r = await fs("read", str(target), offset=99)
    assert (r.content, r.shown) == ("", 0)
    assert r.offset == 3  # clamped to one past the last line
    assert r.truncated is False


@pytest.mark.asyncio
async def test_read_image_points_at_vision(tmp_path):
    png = tmp_path / "shot.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    with pytest.raises(FsError, match=r"vision\(mode='file'"):
        await fs("read", str(png))


@pytest.mark.asyncio
async def test_read_directory_points_at_glob(tmp_path):
    with pytest.raises(FsError, match=r"fs\(mode='glob'"):
        await fs("read", str(tmp_path))


@pytest.mark.asyncio
async def test_read_missing_and_binary_raise(tmp_path):
    with pytest.raises(FsError, match="does not exist"):
        await fs("read", str(tmp_path / "nope.py"))
    binary = tmp_path / "blob.bin"
    binary.write_bytes(bytes(range(1, 32)) * 40)
    with pytest.raises(FsError, match="binary"):
        await fs("read", str(binary))


@pytest.mark.asyncio
async def test_read_records_entry(tmp_path):
    begin_cell(session_id="s1", parent_tool_call_id="t/c")
    target = tmp_path / "f.txt"
    target.write_text("x\n")
    await fs("read", str(target))
    assert [(e.tool, e.mode, e.status, e.result_kind) for e in pending()] == [
        ("fs", "read", "completed", "read")
    ]
    assert pending()[0].args["mode"] == "read"
    assert pending()[0].args["path"] == str(target)


@pytest.mark.asyncio
async def test_read_failure_records_failed(tmp_path):
    begin_cell(session_id="s1", parent_tool_call_id="t/c")
    with pytest.raises(FsError):
        await fs("read", str(tmp_path / "nope.py"))
    assert [(e.tool, e.mode, e.status) for e in pending()] == [
        ("fs", "read", "failed")
    ]
    assert "does not exist" in pending()[0].error


@pytest.mark.asyncio
async def test_read_writes_through_its_row(tmp_path):
    db_uri = f"sqlite:///{tmp_path}/crow.db"
    create_database(db_uri)
    begin_cell(session_id="s1", parent_tool_call_id="turn-3/call_r", db_uri=db_uri)

    target = tmp_path / "f.txt"
    target.write_text("hello\n")
    await fs("read", str(target))

    engine = create_engine(db_uri)
    with sessionmaker(engine)() as session:
        rows = session.execute(select(SubtoolCall)).scalars().all()
        session.expunge_all()
    engine.dispose()
    assert len(rows) == 1
    row = rows[0]
    assert (row.tool, row.mode, row.status) == ("fs", "read", "completed")
    assert row.result_kind == "read"
    assert row.parent_tool_call_id == "turn-3/call_r"
    assert row.acp_payload["path"] == str(target)
    assert row.acp_payload["text"] == "1→hello"
    assert row.emitted == 0


# --- glob ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_glob_patterns_are_root_relative_not_cwd_relative(tmp_path, monkeypatch):
    """The landmine: rg matches a -g pattern containing a slash against the
    path relative to the PROCESS cwd, not the search root. fs runs rg in the
    root, so a slash pattern works from anywhere — here the cwd is a
    different tree entirely."""
    root = _tree(tmp_path / "proj")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    r = await fs("glob", str(root), "src/*.py")

    assert isinstance(r, GlobResult) and r
    assert r.paths == [str(root / "src" / "a.py")]
    assert r.root == str(root)
    assert r.truncated is False
    assert r.result_kind == "search"
    assert r.acp_payload() == {"content": "text", "text": str(root / "src" / "a.py")}


@pytest.mark.asyncio
async def test_glob_defaults_to_the_kernel_cwd(tmp_path, monkeypatch):
    root = _tree(tmp_path / "proj")
    monkeypatch.chdir(root)
    r = await fs("glob", pattern="**/*.py")
    assert sorted(r.paths) == [str(root / "src" / "a.py"), str(root / "tests" / "c.py")]
    assert r.root == str(root)


@pytest.mark.asyncio
async def test_glob_is_gitignore_aware_and_always_skips_venv(tmp_path):
    root = _tree(tmp_path / "proj")
    (root / ".gitignore").write_text("ignored/\n")
    (root / "ignored").mkdir()
    (root / "ignored" / "gen.py").write_text("x = 1\n")
    (root / ".venv" / "lib").mkdir(parents=True)
    (root / ".venv" / "lib" / "dep.py").write_text("y = 2\n")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "cached.py").write_text("z = 3\n")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)

    r = await fs("glob", str(root), "**/*.py")

    assert sorted(r.paths) == [str(root / "src" / "a.py"), str(root / "tests" / "c.py")]


@pytest.mark.asyncio
async def test_glob_limit_truncates(tmp_path):
    root = _tree(tmp_path / "proj")
    r = await fs("glob", str(root), "**/*.py", limit=1)
    assert len(r.paths) == 1 and r.truncated is True


@pytest.mark.asyncio
async def test_glob_no_match_is_empty_and_truthy(tmp_path):
    root = _tree(tmp_path / "proj")
    r = await fs("glob", str(root), "**/*.rs")
    assert r.paths == [] and r.truncated is False and r
    assert r.acp_payload()["text"] == "no files match **/*.rs"


# --- search ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_returns_structured_matches(tmp_path):
    root = _tree(tmp_path / "proj")
    r = await fs("search", str(root), r"def \w+\(")

    assert isinstance(r, SearchResult) and r
    assert r.matches == [
        SearchMatch(str(root / "src" / "a.py"), 1, "def alpha():"),
        SearchMatch(str(root / "tests" / "c.py"), 1, "def gamma():"),
    ]
    assert r.paths == [str(root / "src" / "a.py"), str(root / "tests" / "c.py")]
    assert r.text.splitlines()[0] == f"{root / 'src' / 'a.py'}:1: def alpha():"
    assert r.result_kind == "search"
    assert r.acp_payload() == {"content": "text", "text": r.text}


@pytest.mark.asyncio
async def test_search_paths_dedupe_in_hit_order(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "many.py").write_text("hit\nhit\nhit\n")
    (root / "one.py").write_text("hit\n")
    r = await fs("search", str(root), "hit")
    assert len(r.matches) == 4
    assert r.paths == [str(root / "many.py"), str(root / "one.py")]


@pytest.mark.asyncio
async def test_search_file_pattern_filters(tmp_path):
    root = _tree(tmp_path / "proj")
    r = await fs("search", str(root), "return", file_pattern="*.py")
    assert len(r.matches) == 2
    r = await fs("search", str(root), "beta", file_pattern="*.py")
    assert r.matches == []  # b.txt filtered out


@pytest.mark.asyncio
async def test_search_limit_truncates(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "f.txt").write_text("x\n" * 10)
    r = await fs("search", str(root), "x", limit=3)
    assert len(r.matches) == 3 and r.truncated is True


@pytest.mark.asyncio
async def test_search_no_matches_payload(tmp_path):
    root = _tree(tmp_path / "proj")
    r = await fs("search", str(root), "nothing matches this")
    assert r.matches == [] and r.text == "" and r
    assert r.acp_payload()["text"] == "no matches for nothing matches this"


@pytest.mark.asyncio
async def test_search_bad_regex_raises(tmp_path):
    root = _tree(tmp_path / "proj")
    with pytest.raises(FsError, match="ripgrep failed"):
        await fs("search", str(root), "def (unclosed")


@pytest.mark.asyncio
async def test_search_records_mode_and_kind(tmp_path):
    begin_cell(session_id="s1", parent_tool_call_id="t/c")
    root = _tree(tmp_path / "proj")
    await fs("search", str(root), "alpha")
    assert [(e.tool, e.mode, e.status, e.result_kind) for e in pending()] == [
        ("fs", "search", "completed", "search")
    ]


# --- dispatch --------------------------------------------------------------


@pytest.mark.asyncio
async def test_mode_dispatch_errors(tmp_path):
    with pytest.raises(FsError, match="unknown fs mode"):
        await fs("stat", str(tmp_path))
    with pytest.raises(FsError, match="requires path"):
        await fs("read")
    with pytest.raises(FsError, match="requires pattern"):
        await fs("glob", str(tmp_path))
    with pytest.raises(FsError, match="requires pattern"):
        await fs("search", str(tmp_path))
    with pytest.raises(FsError, match="not a directory"):
        await fs("search", str(tmp_path / "f.txt"), "x")
