"""fs — read/glob/search/ast/rewrite/sub, Python-shaped: real result objects,
FsError raised on failure, register + write-through like every subtool.

No mocks: real files on disk, the real ripgrep binary and the real ast-grep
binding, which is the only way the gitignore, cwd-relative-glob and
metavar-expansion behaviour gets tested at all.
"""

import asyncio
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from crow_cli.memory.db import create_database
from crow_cli.memory.models import SubtoolCall
from crow_cli.tools import fs

# from-import, NOT `import crow_cli.tools.fs as m`: the facade caches the
# resolved FUNCTION into the package dict, so the import-as form binds fs().
from crow_cli.tools.fs import _rg_stream
from crow_cli.tools.register import begin_cell, clear, pending
from crow_cli.tools.results import (
    FileResult,
    FsError,
    GlobResult,
    RewriteResult,
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


# --- ast -------------------------------------------------------------------


def _ast_tree(root):
    """Two python files with os.path.join calls, one clean python file, a JS
    file (same call, plus a template literal whose $ must survive), a
    markdown file (a mapped extension that simply does not match) and a
    binary (skipped, not an error)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "pkg").mkdir()
    (root / "pkg" / "one.py").write_text(
        'import os\n\n\ndef a(x):\n    return os.path.join(x, "a")\n'
    )
    (root / "pkg" / "two.py").write_text('import os\n\np = os.path.join("etc", "d")\n')
    (root / "pkg" / "clean.py").write_text("x = 1\n")
    (root / "app.js").write_text("const t = `${name}/x`;\nconst j = os.path.join(a, b);\n")
    (root / "notes.md").write_text("os.path.join(a, b) is prose, not code\n")
    (root / "blob.bin").write_bytes(bytes(range(1, 32)) * 40)
    return root


JOIN = "os.path.join($A, $B)"


@pytest.mark.asyncio
async def test_ast_finds_structural_matches_across_languages(tmp_path):
    root = _ast_tree(tmp_path / "proj")
    r = await fs("ast", str(root), JOIN)

    assert isinstance(r, SearchResult) and r
    assert [(m.path, m.line, m.text) for m in r.matches] == [
        (str(root / "app.js"), 2, "os.path.join(a, b)"),
        (str(root / "pkg" / "one.py"), 5, 'os.path.join(x, "a")'),
        (str(root / "pkg" / "two.py"), 3, 'os.path.join("etc", "d")'),
    ]
    assert r.result_kind == "search"
    assert r.truncated is False
    # The markdown file parsed and did not match; the binary was skipped.
    assert r.paths == [
        str(root / "app.js"),
        str(root / "pkg" / "one.py"),
        str(root / "pkg" / "two.py"),
    ]


@pytest.mark.asyncio
async def test_ast_matches_span_lines_are_collapsed_and_capped(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "f.py").write_text("def alpha(x):\n    return x + 1\n")
    r = await fs("ast", str(root), "def $F($$$A): $$$B")
    assert len(r.matches) == 1
    assert r.matches[0].line == 1
    assert r.matches[0].text == "def alpha(x): return x + 1"  # whitespace collapsed


@pytest.mark.asyncio
async def test_ast_lang_and_file_pattern_narrow_the_walk(tmp_path):
    root = _ast_tree(tmp_path / "proj")
    r = await fs("ast", str(root), JOIN, lang="python")
    assert r.paths == [str(root / "pkg" / "one.py"), str(root / "pkg" / "two.py")]

    r = await fs("ast", str(root), JOIN, file_pattern="one.py")
    assert r.paths == [str(root / "pkg" / "one.py")]


@pytest.mark.asyncio
async def test_ast_limit_truncates(tmp_path):
    root = _ast_tree(tmp_path / "proj")
    r = await fs("ast", str(root), JOIN, limit=2)
    assert len(r.matches) == 2 and r.truncated is True


@pytest.mark.asyncio
async def test_ast_unsupported_language_raises_before_the_binding_panics(tmp_path):
    """ast-grep's binding PANICS (a pyo3 PanicException, which is a
    BaseException) on a language it has no grammar for — fs refuses those
    first, so the panic is unreachable."""
    root = _ast_tree(tmp_path / "proj")
    for lang in ("sql", "toml", "vue", "zig", "r", "python3"):
        with pytest.raises(FsError, match="unsupported ast language"):
            await fs("ast", str(root), JOIN, lang=lang)
    with pytest.raises(FsError) as info:
        await fs("ast", str(root), JOIN, lang="sql")
    assert "python" in str(info.value) and "javascript" in str(info.value)


@pytest.mark.asyncio
async def test_ast_bad_pattern_raises(tmp_path):
    root = _ast_tree(tmp_path / "proj")
    with pytest.raises(FsError, match=r"cannot match pattern '\$\$\$'"):
        await fs("ast", str(root), "$$$")


@pytest.mark.asyncio
async def test_ast_records_mode_and_kind(tmp_path):
    begin_cell(session_id="s1", parent_tool_call_id="t/c")
    root = _ast_tree(tmp_path / "proj")
    await fs("ast", str(root), JOIN)
    assert [(e.tool, e.mode, e.status, e.result_kind) for e in pending()] == [
        ("fs", "ast", "completed", "search")
    ]


# --- rewrite ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_rewrite_transforms_every_matching_file(tmp_path):
    root = _ast_tree(tmp_path / "proj")
    before_one = (root / "pkg" / "one.py").read_text()

    r = await fs("rewrite", str(root), JOIN, rewrite="Path($A) / $B", lang="python")

    assert isinstance(r, RewriteResult) and r
    assert (r.changed, r.scanned, r.matches) == (2, 3, 2)
    assert r.paths == [str(root / "pkg" / "one.py"), str(root / "pkg" / "two.py")]
    assert (root / "pkg" / "one.py").read_text() == before_one.replace(
        'os.path.join(x, "a")', 'Path(x) / "a"'
    )
    assert (root / "pkg" / "two.py").read_text() == 'import os\n\np = Path("etc") / "d"\n'
    # The JS file was not in the walk (lang=python) and is untouched.
    assert "${name}" in (root / "app.js").read_text()
    assert "os.path.join(a, b)" in (root / "app.js").read_text()

    assert r.result_kind == "rewrite"
    assert r.acp_payload() == {"content": "text", "text": r.summary}
    assert "rewrote 2 of 3 parsed file(s), 2 match(es)" in r.summary
    assert f"{JOIN} -> Path($A) / $B" in r.summary


@pytest.mark.asyncio
async def test_rewrite_expands_multi_metavars_as_source_not_joined(tmp_path):
    """$$$REST captures the punctuation nodes too ([b, ",", c]), so joining
    the captures gives "b, ,, c". The expansion is the SOURCE SPAN."""
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "f.py"
    target.write_text("import os\nos.path.join(a, b, c, d)\n")

    r = await fs("rewrite", str(root), "os.path.join($A, $$$REST)", rewrite="Path($A, $$$REST)")

    assert target.read_text() == "import os\nPath(a, b, c, d)\n"
    assert r.matches == 1


@pytest.mark.asyncio
async def test_rewrite_leaves_uncaptured_dollars_alone(tmp_path):
    """Only metavars the pattern captured expand — a $ belonging to the
    target language (a JS template literal) survives in source AND rewrite."""
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "app.js"
    target.write_text("const t = `${name}/x`;\nfoo(a, b);\n")

    await fs(
        "rewrite",
        str(root),
        "foo($A, $B)",
        rewrite="bar($A, $B, `${extra}`)",
        lang="javascript",
    )

    assert target.read_text() == "const t = `${name}/x`;\nbar(a, b, `${extra}`);\n"


@pytest.mark.asyncio
async def test_rewrite_no_match_changes_nothing(tmp_path):
    root = _ast_tree(tmp_path / "proj")
    before = {p: p.read_text() for p in sorted(root.rglob("*.py"))}

    r = await fs("rewrite", str(root), "requests.get($URL)", rewrite="httpx.get($URL)")

    assert r.changed == 0 and r.files == [] and r.paths == [] and r
    # No lang=, so every mapped extension was parsed: 3 .py + app.js + notes.md.
    assert r.scanned == 5 and r.matches == 0
    assert {p: p.read_text() for p in sorted(root.rglob("*.py"))} == before


@pytest.mark.asyncio
async def test_rewrite_records_one_write_row_per_file_plus_the_operation(tmp_path):
    """Each changed file went through write(), so each is its own row (and
    its own diff on the client); the rewrite's row is the operation."""
    begin_cell(session_id="s1", parent_tool_call_id="t/c")
    root = _ast_tree(tmp_path / "proj")

    await fs("rewrite", str(root), JOIN, rewrite="Path($A) / $B", lang="python")

    assert [(e.tool, e.mode, e.status, e.result_kind) for e in pending()] == [
        ("write", None, "completed", "diff"),
        ("write", None, "completed", "diff"),
        ("fs", "rewrite", "completed", "rewrite"),
    ]


@pytest.mark.asyncio
async def test_rewrite_preimages_ride_the_edit_results(tmp_path):
    """The undo log claim: every EditResult carries whole old_text, so the
    preimage of a rewritten tree is in crow.db — no shadow store needed."""
    root = _ast_tree(tmp_path / "proj")
    before = (root / "pkg" / "one.py").read_text()

    r = await fs("rewrite", str(root), JOIN, rewrite="Path($A) / $B", lang="python")

    by_path = {f.path: f for f in r.files}
    assert by_path[str(root / "pkg" / "one.py")].old_text == before
    assert by_path[str(root / "pkg" / "one.py")].new_text == (
        root / "pkg" / "one.py"
    ).read_text()
    assert all(f.result_kind == "diff" for f in r.files)


@pytest.mark.asyncio
async def test_rewrite_bad_pattern_writes_nothing(tmp_path):
    """Every (path, old, new) is planned BEFORE anything is written, so a
    pattern that cannot match at all leaves the whole tree alone."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("os.path.join(a, b)\n")
    (root / "b.py").write_text("x = 1\n")
    with pytest.raises(FsError, match="cannot match pattern"):
        await fs("rewrite", str(root), "$$$", rewrite="y")
    assert (root / "a.py").read_text() == "os.path.join(a, b)\n"


# --- sub -------------------------------------------------------------------


def _grammarless_tree(root):
    """The quadrant ast cannot reach: toml, sql and ini have no tree-sitter
    grammar, so rewrite= cannot parse them and edit= is one file at a time.
    Plus a lowercase near-miss (re is case-sensitive) and a binary carrying
    the same bytes (skipped, not scanned)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir()
    (root / "config" / "prod.toml").write_text(
        '[server]\nenv_name = "OLD_ENV"\nfallback = "OLD_ENV_local"\n'
    )
    (root / "config" / "dev.toml").write_text('env_name = "OLD_ENV"\n')
    (root / "schema.sql").write_text("CREATE TABLE t (env TEXT DEFAULT 'OLD_ENV');\n")
    (root / "notes.ini").write_text("[a]\nkey = old_env\n")
    (root / "blob.bin").write_bytes(b"OLD_ENV\x00\xff" * 40)
    return root


@pytest.mark.asyncio
async def test_sub_replaces_across_files_ast_cannot_parse(tmp_path):
    root = _grammarless_tree(tmp_path / "proj")

    r = await fs("sub", str(root), pattern="OLD_ENV", rewrite="NEW_ENV")

    assert isinstance(r, RewriteResult) and r
    assert (r.changed, r.scanned, r.matches) == (3, 4, 4)
    assert (root / "config" / "prod.toml").read_text() == (
        '[server]\nenv_name = "NEW_ENV"\nfallback = "NEW_ENV_local"\n'
    )
    assert "DEFAULT 'NEW_ENV'" in (root / "schema.sql").read_text()
    # Case-sensitive: the lowercase near-miss is scanned and left alone.
    assert (root / "notes.ini").read_text() == "[a]\nkey = old_env\n"
    assert r.syntax == "regex" and r.dry_run is False and r.skipped == 0
    assert r.result_kind == "rewrite"
    assert r.acp_payload() == {"content": "text", "text": r.summary}
    # "scanned", not "parsed" — nothing was parsed.
    assert "rewrote 3 of 4 scanned file(s), 4 match(es)" in r.summary
    assert "OLD_ENV -> NEW_ENV" in r.summary


@pytest.mark.asyncio
async def test_sub_respects_gitignore_and_file_pattern(tmp_path):
    root = _grammarless_tree(tmp_path / "proj")
    (root / ".gitignore").write_text("ignored/\n")
    (root / "ignored").mkdir()
    (root / "ignored" / "skip.toml").write_text('env_name = "OLD_ENV"\n')
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)

    r = await fs(
        "sub", str(root), "OLD_ENV", rewrite="NEW_ENV", file_pattern="*.toml"
    )

    assert sorted(Path(p).name for p in r.paths) == ["dev.toml", "prod.toml"]
    assert (root / "ignored" / "skip.toml").read_text() == 'env_name = "OLD_ENV"\n'
    assert "OLD_ENV" in (root / "schema.sql").read_text()


@pytest.mark.asyncio
async def test_sub_expands_python_replacement_templates(tmp_path):
    """sub's replacement is re's, not ast-grep's — inventing a second metavar
    syntax next to $A would be one more thing to remember and one more way to
    be wrong."""
    root = tmp_path / "proj"
    root.mkdir()
    numeric, named = root / "a.toml", root / "b.toml"
    numeric.write_text('who = "OLD_ENV"\n')
    named.write_text('who = "OLD_ENV"\n')

    await fs("sub", str(root), r"(\w+) = \"(OLD_ENV)\"", rewrite=r"\2 for \1",
             file_pattern="a.toml")
    await fs("sub", str(root), r"(?P<k>\w+) = \"(?P<v>OLD_ENV)\"",
             rewrite=r"\g<v>/\g<k>", file_pattern="b.toml")

    assert numeric.read_text() == 'OLD_ENV for who\n'
    assert named.read_text() == 'OLD_ENV/who\n'


@pytest.mark.asyncio
async def test_sub_records_one_write_row_per_file_plus_the_operation(tmp_path):
    begin_cell(session_id="s1", parent_tool_call_id="t/c")
    root = _grammarless_tree(tmp_path / "proj")

    await fs("sub", str(root), "OLD_ENV", rewrite="NEW_ENV")

    assert [(e.tool, e.mode, e.status, e.result_kind) for e in pending()] == [
        ("write", None, "completed", "diff"),
        ("write", None, "completed", "diff"),
        ("write", None, "completed", "diff"),
        ("fs", "sub", "completed", "rewrite"),
    ]


@pytest.mark.asyncio
async def test_sub_no_match_changes_nothing_but_still_reports(tmp_path):
    root = _grammarless_tree(tmp_path / "proj")

    r = await fs("sub", str(root), "NOT_PRESENT", rewrite="x")

    assert (r.changed, r.matches, r.scanned) == (0, 0, 4)
    assert r.files == [] and r.diff == "" and r
    assert [(e.tool, e.status) for e in pending()] == [("fs", "completed")]


@pytest.mark.asyncio
async def test_sub_bad_regex_raises_and_writes_nothing(tmp_path):
    root = _grammarless_tree(tmp_path / "proj")

    with pytest.raises(FsError, match="cannot compile pattern"):
        await fs("sub", str(root), "OLD_ENV[", rewrite="x")

    assert 'env_name = "OLD_ENV"' in (root / "config" / "dev.toml").read_text()


@pytest.mark.asyncio
async def test_sub_bad_replacement_template_is_an_fserror(tmp_path):
    """re raises PatternError for \\9 and a bare IndexError for \\g<nope> —
    from inside a thread, deep in a loop over the caller's tree. The template
    is parsed even when nothing matches, so one probe on "" validates it
    before a single file is read."""
    root = _grammarless_tree(tmp_path / "proj")

    with pytest.raises(FsError, match=r"cannot apply replacement.*group reference 9"):
        await fs("sub", str(root), r"(OLD)_ENV", rewrite=r"\9")
    with pytest.raises(FsError, match=r"cannot apply replacement.*unknown group name"):
        await fs("sub", str(root), r"(OLD)_ENV", rewrite=r"\g<nope>")
    assert 'env_name = "OLD_ENV"' in (root / "config" / "dev.toml").read_text()


@pytest.mark.asyncio
async def test_sub_refuses_a_grammar(tmp_path):
    root = _grammarless_tree(tmp_path / "proj")

    with pytest.raises(FsError, match="takes a regex, not a grammar"):
        await fs("sub", str(root), "OLD_ENV", rewrite="x", lang="python")


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
@pytest.mark.asyncio
async def test_sub_refuses_an_unwritable_file_before_writing_any(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    a, b = root / "a.toml", root / "b.toml"
    a.write_text('x = "OLD"\n')
    b.write_text('y = "OLD"\n')
    b.chmod(0o444)
    try:
        with pytest.raises(FsError, match="permission denied.*nothing was written"):
            await fs("sub", str(root), "OLD", rewrite="NEW")
        assert a.read_text() == 'x = "OLD"\n'
        # The plan failed, so no write() ran: one failed row and nothing else.
        assert [(e.tool, e.status) for e in pending()] == [("fs", "failed")]
    finally:
        b.chmod(0o644)


# --- dry_run ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_plans_a_sub_and_writes_nothing(tmp_path):
    root = _grammarless_tree(tmp_path / "proj")
    before = {p: p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}

    r = await fs("sub", str(root), "OLD_ENV", rewrite="NEW_ENV", dry_run=True)

    assert r.dry_run is True and (r.changed, r.matches, r.scanned) == (3, 4, 4)
    assert r.summary.startswith("[DRY RUN] would rewrite")
    assert '-env_name = "OLD_ENV"' in r.diff and '+env_name = "NEW_ENV"' in r.diff
    assert all(f.result_kind == "diff" for f in r.files)
    assert {p: p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()} == before
    # Nothing changed, so no diff goes to the client — a diff view over an
    # untouched file is a lie. Only the operation's own row exists.
    assert [(e.tool, e.mode, e.status) for e in pending()] == [
        ("fs", "sub", "completed")
    ]


@pytest.mark.asyncio
async def test_dry_run_plans_a_rewrite_and_writes_nothing(tmp_path):
    root = _ast_tree(tmp_path / "proj")
    before = (root / "pkg" / "one.py").read_text()

    r = await fs(
        "rewrite", str(root), JOIN, rewrite="Path($A) / $B", lang="python",
        dry_run=True,
    )

    assert r.dry_run is True and r.syntax == "ast" and (r.changed, r.matches) == (2, 2)
    assert r.summary.startswith("[DRY RUN] would rewrite 2 of 3 parsed file(s)")
    assert '-    return os.path.join(x, "a")' in r.diff
    assert (root / "pkg" / "one.py").read_text() == before
    assert [(e.tool, e.mode, e.status) for e in pending()] == [
        ("fs", "rewrite", "completed")
    ]


@pytest.mark.asyncio
async def test_a_dry_run_diff_is_the_diff_the_real_run_produces(tmp_path):
    """_planned_edit renders exactly what write() renders — same difflib call,
    same a/ b/ prefixes — so dry_run is a preview, not an approximation."""
    root = _grammarless_tree(tmp_path / "proj")

    dry = await fs("sub", str(root), "OLD_ENV", rewrite="NEW_ENV", dry_run=True)
    real = await fs("sub", str(root), "OLD_ENV", rewrite="NEW_ENV")

    assert dry.diff == real.diff
    assert [f.path for f in dry.files] == [f.path for f in real.files]
    assert dry.summary.removeprefix("[DRY RUN] would rewrite") == (
        real.summary.removeprefix("rewrote")
    )


@pytest.mark.asyncio
async def test_dry_run_is_refused_by_the_modes_that_do_not_write(tmp_path):
    """Checked before any mode runs, so read cannot quietly ignore it: the
    guard used to live inside the walk branch and mode='read' never saw it."""
    root = _grammarless_tree(tmp_path / "proj")

    with pytest.raises(FsError, match=r"dry_run= is for the modes that write, not 'read'"):
        await fs("read", str(root / "notes.ini"), dry_run=True)
    with pytest.raises(FsError, match=r"not 'glob'"):
        await fs("glob", str(root), "**/*.toml", dry_run=True)
    with pytest.raises(FsError, match=r"not 'search'"):
        await fs("search", str(root), "OLD", dry_run=True)
    with pytest.raises(FsError, match=r"not 'ast'"):
        await fs("ast", str(root), JOIN, dry_run=True)


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
    with pytest.raises(FsError, match="requires pattern"):
        await fs("ast", str(tmp_path))
    with pytest.raises(FsError, match="requires pattern"):
        await fs("sub", str(tmp_path))
    with pytest.raises(FsError, match="requires rewrite"):
        await fs("rewrite", str(tmp_path), "os.path.join($A, $B)")
    with pytest.raises(FsError, match="requires rewrite"):
        await fs("sub", str(tmp_path), "OLD")
    with pytest.raises(FsError, match="not a directory"):
        await fs("search", str(tmp_path / "f.txt"), "x")
    with pytest.raises(FsError, match="unknown fs mode 'stat'"):
        await fs("stat", str(tmp_path), dry_run=True)


# --- edge cases found by probing a live kernel ------------------------------
#
# Every test below is a bug that shipped, not a shape that was merely
# untested: the assertions are what used to come back wrong.


@pytest.mark.asyncio
async def test_read_newline_only_file_counts_its_one_empty_line(tmp_path):
    """shown is a FIELD, not len(content.splitlines()): a window holding a
    single empty line has content "", which splitlines() counts as zero — so
    a newline-only file reported lines=1 shown=0 truncated=True while .text
    still rendered "1→"."""
    target = tmp_path / "nl.txt"
    target.write_text("\n")
    r = await fs("read", str(target))
    assert (r.lines, r.offset, r.shown, r.truncated) == (1, 1, 1, False)
    assert r.content == ""
    assert r.text == "1→"


@pytest.mark.asyncio
async def test_read_limit_zero_is_an_empty_window_with_no_notice(tmp_path):
    """"showing lines 1-0 of 1 total" is noise: an empty window renders
    nothing and .truncated says it in code."""
    target = tmp_path / "f.txt"
    target.write_text("one\n")
    r = await fs("read", str(target), limit=0)
    assert (r.content, r.text, r.shown) == ("", "", 0)
    assert r.truncated is True


@pytest.mark.asyncio
async def test_read_empty_file(tmp_path):
    target = tmp_path / "empty.py"
    target.write_text("")
    r = await fs("read", str(target))
    assert (r.lines, r.shown, r.content, r.text, r.truncated) == (0, 0, "", "", False)


@pytest.mark.asyncio
async def test_read_normalizes_line_endings(tmp_path):
    """.content is the window joined with \\n, so a CRLF file comes back LF —
    pinned because writing .content straight back would re-write every line
    ending in the file."""
    target = tmp_path / "dos.txt"
    target.write_bytes(b"one\r\ntwo\r\n")
    r = await fs("read", str(target))
    assert r.content == "one\ntwo"
    assert r.text == "1→one\n2→two"
    assert (r.lines, r.shown) == (2, 2)


@pytest.mark.asyncio
async def test_read_caps_a_long_line_in_text_but_not_in_content(tmp_path):
    target = tmp_path / "long.txt"
    target.write_text("x" * 5000 + "\n")
    r = await fs("read", str(target))
    assert r.text == "1→" + "x" * 2000 + "... [line truncated]"
    assert r.content == "x" * 5000


@pytest.mark.asyncio
async def test_rewrite_drops_nested_matches_instead_of_splicing_garbage(tmp_path):
    """$CALL matches NINE nodes in "f(g(x))" — module [0:8],
    expression_statement [0:7], call [0:7], identifier [0:1],
    argument_list [1:7], call [2:6], and three more inside that — and
    commit_edits on overlapping ranges does not complain: it splices.
    Outermost wins, left to right, and the drops are counted in .skipped.

    The output is NOT corruption, which is what made this hard to see: the
    outermost match is the `module` node, whose text is the whole file
    INCLUDING the trailing newline, so wrapping it is the faithful expansion
    of the one match that was applied."""
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "nest.py"
    target.write_text("f(g(x))\n")

    r = await fs("rewrite", str(root), "$CALL", rewrite="wrapped($CALL)", lang="python")

    assert (r.changed, r.matches, r.skipped) == (1, 1, 8)
    assert target.read_text() == "wrapped(f(g(x))\n)"
    assert "8 overlapping skipped" in r.summary


@pytest.mark.asyncio
async def test_rewrite_keeps_adjacent_matches_that_do_not_overlap(tmp_path):
    """De-overlapping must not over-drop: two sibling calls on one line are
    both applied."""
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "two.py"
    target.write_text("x = f(1) + f(2)\n")

    r = await fs("rewrite", str(root), "f($N)", rewrite="g($N)", lang="python")

    assert (r.matches, r.skipped) == (2, 0)
    assert target.read_text() == "x = g(1) + g(2)\n"


@pytest.mark.asyncio
async def test_search_decodes_a_non_utf8_line_from_rg_base64(tmp_path):
    """rg --json emits the matched line as {"bytes": <base64>} when it is not
    valid UTF-8; reading only .text made every such match render EMPTY."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "latin.txt").write_bytes(b"caf\xe9 na\xefve\n")

    r = await fs("search", str(root), "caf")

    assert len(r.matches) == 1
    assert (r.matches[0].line, r.matches[0].text) == (1, "caf\ufffd na\ufffdve")


def _weird_py(root):
    """A .py file whose NAME is not valid UTF-8 — made through the bytes API,
    because no str can name it. Returns the fsdecode'd path, which is real
    and openable (surrogateescape) where a replace-decoded one is not."""
    root.mkdir(parents=True, exist_ok=True)
    raw = os.path.join(os.fsencode(root), b"weird_\xff\xfe.py")
    with open(raw, "wb") as f:
        f.write(b"os.path.join(a, b)\n")
    return os.fsdecode(raw)


@pytest.mark.asyncio
async def test_search_blames_the_file_not_the_root_for_a_non_utf8_name(tmp_path):
    """rg --json base64s a path it cannot emit as text, and "" joined onto
    the root blamed the ROOT DIRECTORY for a match inside it. The decode is
    os.fsdecode, not errors="replace": a replacement character makes a path
    that looks fine and does not exist."""
    root = tmp_path / "proj"
    weird = _weird_py(root)

    r = await fs("search", str(root), "os.path.join")

    assert len(r.matches) == 1
    assert r.matches[0].path == weird != str(root)
    with open(r.matches[0].path, "rb") as f:
        assert f.read() == b"os.path.join(a, b)\n"


@pytest.mark.asyncio
async def test_glob_and_ast_reach_a_non_utf8_filename(tmp_path):
    """`rg --files` output goes through the same decode: replace-decoding
    made glob hand back paths that do not exist, and an ast walk skip the
    file without a word."""
    root = tmp_path / "proj"
    weird = _weird_py(root)

    g = await fs("glob", str(root), "**/*.py")
    assert g.paths == [weird] and os.path.exists(g.paths[0])

    a = await fs("ast", str(root), JOIN)
    assert [m.path for m in a.matches] == [weird]


@pytest.mark.asyncio
async def test_rg_stream_stops_at_the_cap_and_kills_an_endless_producer(tmp_path):
    """The cap is what keeps a broad search from buffering a tree in the
    kernel, so the stream has to stop reading and KILL the producer.

    The kill must be followed by communicate(), not wait(): breaking out
    early leaves the StreamReader over its high-water mark, which PAUSES the
    pipe transport — it comes off the selector, EOF is never observed, and
    wait() blocks forever. `yes` wedged a live kernel permanently; the
    timeout here turns a regression into a failure instead of a hang."""
    async with asyncio.timeout(30):
        items, truncated = await _rg_stream(
            ["yes", "hit"], tmp_path, lambda raw: raw.decode().strip() or None, 5
        )
    assert len(items) == 6 and truncated is True  # one past cap = truncated


@pytest.mark.asyncio
async def test_rg_stream_does_not_deadlock_on_a_full_stderr(tmp_path):
    """stderr goes to a temporary file, not a pipe: nothing drains it while
    stdout is being read, so a child writing more than the 64KB pipe buffer
    blocks forever and takes the kernel's loop with it. 20000 lines is
    ~120KB."""
    noise = "for i in $(seq 1 20000); do echo noise >&2; done; echo hit"
    async with asyncio.timeout(30):
        items, truncated = await _rg_stream(
            ["sh", "-c", noise], tmp_path, lambda raw: raw.decode().strip() or None, 5
        )
    assert items == ["hit"] and truncated is False


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
@pytest.mark.asyncio
async def test_rewrite_refuses_an_unwritable_file_before_writing_any(tmp_path):
    """All-or-nothing. The writability check is in the PLAN, so one read-only
    file fails the whole rewrite: the earlier shape transformed a.py and then
    raised WriteError on b.py, leaving a half-rewritten tree behind."""
    root = tmp_path / "proj"
    root.mkdir()
    a, b = root / "a.py", root / "b.py"
    a.write_text("os.path.join(a, b)\n")
    b.write_text("os.path.join(c, d)\n")
    b.chmod(0o444)
    try:
        with pytest.raises(FsError, match="permission denied.*nothing was written"):
            await fs("rewrite", str(root), JOIN, rewrite="Path($A) / $B")
        assert a.read_text() == "os.path.join(a, b)\n"
        assert b.read_text() == "os.path.join(c, d)\n"
    finally:
        b.chmod(0o644)


@pytest.mark.asyncio
async def test_a_non_utf8_path_still_lands_its_row(tmp_path):
    """os.fsdecode keeps a non-UTF8 filename a real path in the kernel, but a
    lone surrogate cannot cross the wire: json.dumps escapes it to ``\\udcff``,
    which is invalid JSON to a Rust/serde client, and the write-through
    (which catches and logs) would have dropped the row SILENTLY. _wire_safe
    replaces it at the row choke point — the row lands, the kernel keeps the
    truth."""
    db_uri = f"sqlite:///{tmp_path}/crow.db"
    create_database(db_uri)
    begin_cell(session_id="s1", parent_tool_call_id="turn-9/call_w", db_uri=db_uri)
    root = tmp_path / "proj"
    weird = _weird_py(root)

    r = await fs("search", str(root), "os.path.join")
    assert r.matches[0].path == weird  # kernel-side truth, surrogates intact
    assert "\udcff" in pending()[0].acp_payload["text"]

    engine = create_engine(db_uri)
    with sessionmaker(engine)() as session:
        rows = session.execute(select(SubtoolCall)).scalars().all()
        session.expunge_all()
    engine.dispose()

    assert len(rows) == 1  # not silently dropped
    text = rows[0].acp_payload["text"]
    assert "\udcff" not in text
    assert "weird_" in text and ":1: os.path.join(a, b)" in text
    text.encode("utf-8")  # a lone surrogate would raise UnicodeEncodeError


def _living(marker: str) -> int:
    """Processes still carrying marker in their command line. pgrep excludes
    itself and the marker is random per run, so nothing else can match —
    which is the whole point: `pgrep -f 'sleep 30'` from a shell matches the
    shell that ran it."""
    probe = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True)
    return len(probe.stdout.split())


@pytest.mark.asyncio
async def test_a_negative_limit_is_refused_not_sliced(tmp_path):
    """limit is a COUNT, not a slice end. It flowed straight into
    ``window[:limit]``, so limit=-1 handed back the window minus its last
    line, and a search came back EMPTY while still claiming truncated
    (cap=-1 trips `len(items) > cap` on the very first match)."""
    root = _tree(tmp_path / "proj")
    for coro in (
        fs("read", str(root / "src" / "a.py"), limit=-1),
        fs("glob", str(root), "**/*.py", limit=-1),
        fs("search", str(root), "alpha", limit=-1),
        fs("ast", str(root), JOIN, limit=-1),
    ):
        with pytest.raises(FsError, match="limit must be >= 0"):
            await coro
    r = await fs("read", str(root / "src" / "a.py"), limit=0)  # 0 is legal
    assert (r.shown, r.content) == (0, "")


@pytest.mark.asyncio
async def test_read_refuses_a_pipe_instead_of_blocking_forever(tmp_path):
    """open() on a FIFO with no writer BLOCKS, and it blocks in a worker
    thread that cannot be cancelled — a hung cell, not a slow one. is_file()
    is False for pipes, sockets and devices, and still True for a symlink to
    a regular file. The wait_for turns a regression into a failure."""
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    with pytest.raises(FsError, match="Not a regular file"):
        await asyncio.wait_for(fs("read", str(fifo)), 5)

    real = tmp_path / "real.txt"
    real.write_text("through a symlink\n")
    link = tmp_path / "link.txt"
    link.symlink_to(real)
    assert (await fs("read", str(link))).content == "through a symlink"


@pytest.mark.asyncio
async def test_rg_stream_timeout_kills_the_whole_process_group(tmp_path, monkeypatch):
    """The timeout has to leave nothing behind. Killing only the direct child
    lets a grandchild keep stdout open, and the drain then waits for an EOF
    that will not come: `sh -c 'echo hit; sleep 30'` cost a full 30s before
    its FsError. start_new_session + killpg reaches the group."""
    monkeypatch.setattr(sys.modules["crow_cli.tools.fs"], "_RG_TIMEOUT", 1.0)
    nap = f"37.{random.randint(100, 999)}"

    with pytest.raises(FsError, match="timed out"):
        await _rg_stream(
            ["sh", "-c", f"echo hit; sleep {nap}"],
            tmp_path,
            lambda raw: raw.decode().strip() or None,
            5,
        )

    await asyncio.sleep(0.2)
    assert _living(f"sleep {nap}") == 0


@pytest.mark.asyncio
async def test_rg_stream_cancellation_kills_the_child_and_propagates(tmp_path):
    """A cancelled cell (escape pressed, react loop gave up) must not leave
    the producer running, and must not swallow the CancelledError — the loop
    above depends on it arriving."""
    marker = f"fs-cancel-{random.randint(100000, 999999)}"
    task = asyncio.create_task(
        _rg_stream(
            ["yes", marker], tmp_path, lambda raw: raw.decode().strip() or None, None
        )
    )
    await asyncio.sleep(0.3)
    assert _living(marker) > 0  # it really was running

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    await asyncio.sleep(0.2)
    assert _living(marker) == 0


@pytest.mark.asyncio
async def test_read_expands_a_leading_tilde(tmp_path, monkeypatch):
    """``~`` has to expand BEFORE the absolute check:
    ``Path("~/x").is_absolute()`` is False, so it became ``<cwd>/~/x`` and
    failed with a path that reads like a bug report. Fixed in _resolve_path,
    which edit and write share."""
    monkeypatch.setenv("HOME", str(tmp_path))
    target = tmp_path / "f.txt"
    target.write_text("home\n")

    r = await fs("read", "~/f.txt")

    assert r.path == str(target.resolve())
    assert r.content == "home"


@pytest.mark.asyncio
async def test_rewrite_expands_metavars_by_character_not_byte_offset(tmp_path):
    """_expand slices a Python str with ast-grep's range indices. Were those
    BYTE offsets, every non-ASCII file would come back mangled — silently,
    and only for files with accents or CJK in them. The prefix here is 35
    bytes and 27 characters."""
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "u.py"
    src = 'GREETING = "café naïve 日本語"\n\n\np = os.path.join(a, b, c)\n'
    target.write_text(src, encoding="utf-8")
    first = src.splitlines()[0]
    assert len(first.encode()) != len(first)  # the whole point of the fixture

    r = await fs(
        "rewrite", str(root), "os.path.join($A, $$$REST)", rewrite="Path($A, $$$REST)"
    )

    assert r.matches == 1
    assert target.read_text(encoding="utf-8") == src.replace(
        "os.path.join(a, b, c)", "Path(a, b, c)"
    )


@pytest.mark.asyncio
async def test_ast_and_rewrite_survive_a_syntax_error(tmp_path):
    """A tree containing a broken file is the COMMON case, not the exotic
    one: tree-sitter parses partially, ast-grep still finds the call inside
    the broken file, and nothing panics (a pyo3 panic is a BaseException —
    it would take the kernel with it)."""
    root = tmp_path / "proj"
    root.mkdir()
    broken = root / "broken.py"
    broken.write_text("def f(:\n    os.path.join(a, b)\n")
    fine = root / "fine.py"
    fine.write_text("os.path.join(c, d)\n")

    r = await fs("ast", str(root), JOIN)
    assert [(Path(m.path).name, m.line) for m in r.matches] == [
        ("broken.py", 2),
        ("fine.py", 1),
    ]

    w = await fs("rewrite", str(root), JOIN, rewrite="Path($A) / $B")
    assert (w.changed, w.matches) == (2, 2)
    assert broken.read_text() == "def f(:\n    Path(a) / b\n"


# --- edge cases found by probing sub and dry_run in a live kernel -----------


@pytest.mark.asyncio
async def test_sub_preserves_crlf_line_endings(tmp_path):
    """THE SILENT ONE. _read_text used the default newline= translation, so a
    CRLF file came back with EVERY line ending flipped to LF — and the diff
    HID it, because unified_diff is fed splitlines(), which strips \\r from
    both sides. One word replaced, whole file reformatted, nothing to show
    it. write() re-read the preimage with the same default, so crow.db's undo
    log could not have restored the original either."""
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "a.toml"
    target.write_bytes(b'x = "OLD"\r\ny = 2\r\nz = 3\r\n')

    r = await fs("sub", str(root), "OLD", rewrite="NEW")

    assert target.read_bytes() == b'x = "NEW"\r\ny = 2\r\nz = 3\r\n'
    assert r.files[0].new_text == 'x = "NEW"\r\ny = 2\r\nz = 3\r\n'
    assert r.files[0].old_text == 'x = "OLD"\r\ny = 2\r\nz = 3\r\n'
    # The diff looked exactly this clean before the fix too — which is why
    # the bug shipped: the one view anyone checks was the one that hid it.
    assert r.files[0].diff.splitlines() == [
        "--- a/a.toml",
        "+++ b/a.toml",
        "@@ -1,3 +1,3 @@",
        '-x = "OLD"',
        '+x = "NEW"',
        " y = 2",
        " z = 3",
    ]


@pytest.mark.asyncio
async def test_rewrite_preserves_crlf_including_a_multiline_match(tmp_path):
    """The ast path shares _read_text, so it had the same flip — and a
    $$$BODY match SPANS the line endings, which is the case where a
    translation would show up inside the replacement rather than around it."""
    root = tmp_path / "proj"
    root.mkdir()
    one = root / "m.py"
    one.write_bytes(b"import os\r\n\r\np = os.path.join(a, b)\r\nq = 2\r\n")
    spanning = root / "n.py"
    spanning.write_bytes(b"def f(a, b):\r\n    return os.path.join(a, b)\r\n")

    single = await fs("rewrite", str(root), JOIN, rewrite="Path($A) / $B",
                      lang="python", file_pattern="m.py")
    multi = await fs("rewrite", str(root), "def $F($$$ARGS): $$$BODY",
                     rewrite="# $F", lang="python", file_pattern="n.py")

    assert one.read_bytes() == b"import os\r\n\r\np = Path(a) / b\r\nq = 2\r\n"
    assert spanning.read_bytes() == b"# f\r\n"
    assert (single.matches, multi.matches) == (1, 1)


@pytest.mark.asyncio
async def test_an_empty_rewrite_deletes_instead_of_being_refused(tmp_path):
    """``rewrite=""`` is sed's s/x//g. The guard used to test falsiness, so
    the one legitimate empty replacement was reported as a missing argument —
    and `rewrite is None` is the only check that can tell them apart."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.toml").write_text("# TODO: fix this\nx = 1\n")
    (root / "b.py").write_text("import os\np = os.path.join(a, b)\n")

    deleted = await fs("sub", str(root), "TODO: ", rewrite="", file_pattern="*.toml")
    node = await fs("rewrite", str(root), JOIN, rewrite="", file_pattern="*.py")

    assert (root / "a.toml").read_text() == "# fix this\nx = 1\n"
    # The node's range starts at "os", so deleting it leaves the space that
    # preceded it — a dry run shows exactly this before it happens.
    assert (root / "b.py").read_text() == "import os\np = \n"
    assert (deleted.changed, deleted.matches) == (1, 1)
    assert (node.changed, node.matches) == (1, 1)


@pytest.mark.asyncio
async def test_sub_no_op_replacement_counts_a_match_and_changes_no_file(tmp_path):
    """Same reading the ast path gives: the pattern hit, the replacement
    reproduced the source, so nothing was written and no write() row exists —
    but matches > 0 with changed == 0 says that plainly."""
    root = _grammarless_tree(tmp_path / "proj")

    r = await fs("sub", str(root), r"(OLD_ENV)", rewrite=r"\1")

    assert (r.changed, r.matches, r.scanned) == (0, 4, 4)
    assert r.files == [] and r.diff == "" and r
    assert [(e.tool, e.status) for e in pending()] == [("fs", "completed")]
