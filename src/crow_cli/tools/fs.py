"""fs — read, glob, search, ast, rewrite: the filesystem, Python-shaped.

Modes:
- ``read``    — one file as a line-numbered window (offset/limit). The old
  MCP read tool's contract, ported here rather than imported: crow_cli.mcp
  is pared to execute in the endgame, and this is the part that survives.
- ``glob``    — gitignore-style pattern -> matching FILES under a root.
- ``search``  — regex -> structured matches (path, line, text) under a root.
- ``ast``     — structural search (ast-grep patterns: ``os.path.join($A,
  $B)``, ``def $F($$$ARGS): $$$BODY``) -> the same SearchResult shape.
- ``rewrite`` — the same pattern plus a ``rewrite=`` string with the
  pattern's own metavariables -> every matching file rewritten.

glob, search, ast and rewrite all walk with ripgrep, which is why they get
real gitignore semantics for free (nested .gitignore, .git/info/exclude,
hidden files skipped) instead of a reimplementation: one engine, every mode
that touches a tree. It is an external binary — absent, fs raises rather
than degrading. ast-grep is imported lazily, so a kernel that never parses
a tree never loads the native extension.

A rewrite does NOT carry N files in one payload: each changed file goes
through write(), so each is its own subtool row and its own diff on the
client, and crow.db holds every preimage. The rewrite's own row is the
operation — pattern, rewrite string, summary.

Images are refused politely: reading a png as text is never what the caller
meant, and vision(mode="file") is.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import shutil
import signal
import tempfile
from pathlib import Path

from crow_cli.mcp.editor.main import _resolve_path

from .register import subtool
from .results import (
    FileResult,
    FsError,
    GlobResult,
    RewriteResult,
    SearchMatch,
    SearchResult,
)

_MAX_LINE_LENGTH = 2000
_BINARY_CHECK_SIZE = 8192
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Per-mode caps when the caller passes no limit: lines, files, matches.
_DEFAULT_LIMIT = {"read": 2000, "glob": 500, "search": 200}

_IMAGE_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp",
    ".gif",
    ".ico",
    ".tif",
    ".tiff",
}

# Excluded from every glob and search even when .gitignore does not: a
# kernel's own venv and caches are noise, never the answer.
_ALWAYS_EXCLUDE = (".git", ".venv", "__pycache__", "node_modules")

_RG_TIMEOUT = 60.0

# A structural match can span lines (a whole function); the rendered line
# collapses whitespace and caps, so one match is one line of output.
_MATCH_TEXT_MAX = 160

# ast-grep's bundled grammars, by extension. This map is also the language
# VALIDATOR: an unsupported language makes the native binding PANIC (a
# pyo3 PanicException, which is a BaseException — it would sail straight
# through an `except Exception`), so nothing reaches SgRoot unless it is a
# value in here. sql, toml, zig, r, vue and svelte are notably absent.
_LANG_BY_EXT = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
    ".rs": "rust",
    ".go": "go",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".hxx": "cpp",
    ".cs": "csharp",
    ".java": "java",
    ".rb": "ruby",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".sh": "bash",
    ".bash": "bash",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".swift": "swift",
    ".php": "php",
    ".lua": "lua",
    ".scala": "scala",
    ".ex": "elixir",
    ".exs": "elixir",
    ".hs": "haskell",
    ".dart": "dart",
    ".nix": "nix",
    ".sol": "solidity",
}

_LANGS = sorted(set(_LANG_BY_EXT.values()))

# $$$MULTI before $SINGLE, or the tail of a multi-metavar matches first.
_METAVAR = re.compile(r"\$\$\$\w+|\$\w+")


def _cap(limit: int | None, mode: str) -> int:
    """The per-mode cap. A limit is a COUNT, not a slice end: negative would
    silently drop lines off the tail (read) or empty the result while still
    claiming truncated (glob/search), so it is refused rather than clamped."""
    if limit is None:
        return _DEFAULT_LIMIT[mode]
    limit = int(limit)
    if limit < 0:
        raise FsError(f"limit must be >= 0, got {limit}")
    return limit


def _is_binary(path) -> bool:
    """Ported from crow_cli.mcp.read.main: NUL byte, undecodable, or a
    third-plus control characters in the first 8KB."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(_BINARY_CHECK_SIZE)
    except OSError:
        return False
    if not chunk:
        return False
    if b"\x00" in chunk:
        return True
    try:
        text = chunk.decode("utf-8")
    except UnicodeDecodeError:
        return True
    if "\ufffd" in text:
        return True
    control = sum(1 for c in text if ord(c) < 9 or (13 < ord(c) < 32))
    return control / len(text) > 0.3


def _number(lines: list[str], offset: int, total: int) -> str:
    """Line-numbered window (1-indexed, arrow separator — the read tool's
    format, so a model that has read files before reads this the same way),
    plus the paging notice when the file was cut. An empty window gets no
    notice: "showing lines 1-0" is noise, and .truncated says it in code."""
    if not lines:
        return ""
    padding = len(str(offset + len(lines) - 1))
    out = []
    for idx, line in enumerate(lines):
        if len(line) > _MAX_LINE_LENGTH:
            line = line[:_MAX_LINE_LENGTH] + "... [line truncated]"
        out.append(f"{offset + idx:>{padding}}\u2192{line}")
    text = "\n".join(out)
    if offset - 1 + len(lines) < total:
        text += (
            f"\n\n[File truncated: showing lines {offset}-{offset + len(lines) - 1}"
            f" of {total} total. Read again with offset/limit for the rest.]"
        )
    return text


def _read(path: Path, offset: int, limit: int) -> FileResult:
    if not path.exists():
        raise FsError(f"File does not exist: {path}")
    if path.is_dir():
        raise FsError(
            f"Path is a directory: {path} — fs(mode='glob', path={str(path)!r})"
            " lists it"
        )
    if not path.is_file():
        # A pipe, socket or device: open() on a FIFO with no writer BLOCKS
        # FOREVER, and it blocks in a worker thread that cannot be
        # cancelled — a hung cell, not a slow one.
        raise FsError(f"Not a regular file: {path} — nothing to read as text")
    if path.suffix.lower() in _IMAGE_EXTS:
        raise FsError(
            f"{path} is an image — vision(mode='file', path={str(path)!r}) sees it,"
            " reading its bytes as text cannot"
        )
    size = path.stat().st_size
    if size > _MAX_FILE_SIZE:
        raise FsError(f"File too large: {size} bytes (max {_MAX_FILE_SIZE})")
    if _is_binary(path):
        raise FsError(f"Cannot read binary file: {path}")
    try:
        content = path.read_text(encoding="utf-8")
    except PermissionError:
        raise FsError(f"Permission denied: {path}") from None
    except OSError as e:
        raise FsError(f"Failed to read file: {e}") from None

    all_lines = content.splitlines()
    start = min(max(0, offset - 1), len(all_lines))  # clamped: past EOF is empty
    window = all_lines[start : start + limit]
    return FileResult(
        path=str(path),
        content="\n".join(window),
        text=_number(window, start + 1, len(all_lines)),
        lines=len(all_lines),
        offset=start + 1,
        shown=len(window),
    )


def _rg() -> str:
    found = shutil.which("rg")
    if found is None:
        raise FsError("ripgrep (rg) is not on PATH — fs glob and search need it")
    return found


def _excludes() -> list[str]:
    return [arg for name in _ALWAYS_EXCLUDE for arg in ("-g", f"!{name}/")]


def _json_path(field) -> str:
    """rg --json base64s a path it cannot emit as UTF-8 text. Taking only
    ``.text`` yields "" for such a file, and "" joined onto the root blames
    the ROOT DIRECTORY for a match inside it — so decode the bytes, with
    fsdecode (surrogateescape) to keep the result a real, openable path."""
    field = field or {}
    if field.get("text") is not None:
        return field["text"]
    return os.fsdecode(base64.b64decode(field.get("bytes") or ""))


def _json_line(field) -> str:
    """Same for the matched line's own bytes (a latin-1 file matches fine
    and its text arrives base64'd — without this the match renders empty)."""
    field = field or {}
    if field.get("text") is not None:
        return field["text"].rstrip("\n")
    raw = base64.b64decode(field.get("bytes") or "")
    return raw.decode("utf-8", "replace").rstrip("\n")


def _file_items(root: Path):
    """Parser for `rg --files`: one path per line, as raw bytes.

    os.fsdecode, NOT decode(errors="replace"): a replacement character makes
    a path that looks fine and does not exist, so glob would hand back
    unopenable paths and an ast walk would silently skip the file."""

    def parse(raw: bytes) -> Path | None:
        line = raw.rstrip(b"\n")
        return root / os.fsdecode(line) if line else None

    return parse


def _match_items(root: Path):
    """Parser for `rg --json`: match records become SearchMatch, everything
    else (begin/end/summary) is skipped."""

    def parse(raw: bytes) -> SearchMatch | None:
        raw = raw.rstrip(b"\n")
        if not raw:
            return None
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if record.get("type") != "match":
            return None
        data = record["data"]
        return SearchMatch(
            path=str(root / _json_path(data.get("path"))),
            line=data.get("line_number") or 0,
            text=_json_line(data.get("lines")),
        )

    return parse


def _kill_group(proc) -> None:
    """SIGKILL the child's whole process group, not just the child.

    A grandchild that inherited stdout keeps the pipe open after the child
    we killed is gone, and the drain below then waits for an EOF that will
    not arrive until it exits — ``sh -c 'echo hit; sleep 30'`` cost a full
    30s. The child is started with start_new_session=True, so its pgid is
    its pid.
    """
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()


async def _rg_stream(argv: list[str], root: Path, parse, cap: int | None):
    """Run rg with cwd=root and "." as the search path, STREAMING stdout.

    Three reasons this is not ``proc.communicate()``:

    * the cwd is not a detail — rg matches a -g pattern containing a slash
      against the path relative to the PROCESS cwd, not the search path, so
      `-g 'src/tools/*.py' /abs/root` returns nothing from anywhere else
      (slashless patterns match at any level and hide the bug). Running in
      the root makes patterns and output root-relative; callers absolutize.
    * output is unbounded — a broad pattern over a big tree is gigabytes of
      JSON. ``parse`` turns a stdout line into an item (or None to skip it)
      and the stream STOPS at ``cap`` items, killing rg's whole process
      group mid-flight and draining the pipe it was killed with, so a search
      cannot buffer the tree in the kernel. ``cap=None`` walks everything
      (the ast modes must see every file).
    * stderr goes to a temporary file, not a pipe: nothing drains it while
      stdout is being read, and a full stderr buffer would deadlock rg.

    The exit code is only read when rg finished on its own — 0 is matches, 1
    is "no matches", >=2 is an error, and a process we killed has no
    meaningful code.
    """
    err_file = tempfile.TemporaryFile()
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(root),
        stdout=asyncio.subprocess.PIPE,
        stderr=err_file,
        start_new_session=True,  # its own process group — see _kill_group
    )
    items: list = []
    truncated = False
    try:
        async with asyncio.timeout(_RG_TIMEOUT):
            async for raw in proc.stdout:
                item = parse(raw)
                if item is None:
                    continue
                items.append(item)
                if cap is not None and len(items) > cap:
                    truncated = True
                    break
        if not truncated:
            await proc.wait()
            if proc.returncode not in (0, 1):
                err_file.seek(0)
                detail = err_file.read().decode(errors="replace").strip()
                raise FsError(f"ripgrep failed ({proc.returncode}): {detail}")
    except TimeoutError:
        raise FsError(f"ripgrep timed out after {_RG_TIMEOUT}s") from None
    finally:
        if proc.returncode is None:
            _kill_group(proc)
            # communicate(), NOT wait(). Breaking out of the stream early
            # leaves the StreamReader over its high-water mark, which PAUSES
            # the pipe transport: it comes off the selector, so EOF is never
            # observed and wait() blocks forever — a wedged kernel, not a
            # slow one (`yes hit` reproduces it every time; rg reproduces it
            # whenever the reader happens to be paused at the break).
            # Draining resumes the transport and reaps the child.
            await proc.communicate()
        err_file.close()
    return items, truncated


def _files_argv(file_pattern: str | None, extra: list[str] | None = None) -> list[str]:
    argv = [
        _rg(),
        "--files",
        "--no-messages",
        "--no-config",
        "--sort",
        "path",  # rg searches in parallel: unsorted output is nondeterministic
        *_excludes(),
    ]
    if file_pattern:
        argv += ["-g", file_pattern]
    return [*argv, *(extra or []), "."]


async def _glob(root: Path, pattern: str, limit: int) -> GlobResult:
    paths, truncated = await _rg_stream(
        _files_argv(None, ["-g", pattern]), root, _file_items(root), limit
    )
    return GlobResult(
        pattern=pattern,
        root=str(root),
        paths=[str(p) for p in paths[:limit]],
        truncated=truncated,
    )


async def _search(
    root: Path, pattern: str, limit: int, file_pattern: str | None
) -> SearchResult:
    argv = [
        _rg(),
        "--json",
        "--no-messages",
        "--no-config",
        "--sort",
        "path",  # deterministic hit order across files
        *_excludes(),
    ]
    if file_pattern:
        argv += ["-g", file_pattern]
    argv += ["--regexp", pattern, "."]
    matches, truncated = await _rg_stream(argv, root, _match_items(root), limit)
    return SearchResult(
        pattern=pattern,
        root=str(root),
        matches=matches[:limit],
        truncated=truncated,
    )


async def _walk(root: Path, file_pattern: str | None) -> list[Path]:
    """Every file rg will list under root — gitignore-aware, excludes
    applied, and deliberately UNCAPPED: the ast modes have to see the whole
    tree, and paths are small where matches are not."""
    files, _ = await _rg_stream(_files_argv(file_pattern), root, _file_items(root), None)
    return files


def _lang_of(path: Path) -> str | None:
    return _LANG_BY_EXT.get(path.suffix.lower())


def _candidates(files: list[Path], lang: str | None) -> list[Path]:
    """The walk, narrowed to what ast-grep can parse: one language when the
    caller named it, every mapped extension otherwise."""
    if lang:
        return [p for p in files if _lang_of(p) == lang]
    return [p for p in files if _lang_of(p)]


def _read_text(path: Path) -> str | None:
    """None for anything that is not decodable text. A tree walk turns up
    binaries, huge files and exotic encodings; in a walk those are skips,
    not errors (mode='read' raises on exactly the same conditions)."""
    try:
        if path.stat().st_size > _MAX_FILE_SIZE or _is_binary(path):
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _parse(text: str, lang: str, pattern: str):
    """(root, matches). A bad PATTERN raises RuntimeError in the binding,
    which becomes an FsError naming the pattern."""
    from ast_grep_py import SgRoot

    try:
        root = SgRoot(text, lang).root()
        return root, root.find_all(pattern=pattern)
    except RuntimeError as e:
        raise FsError(f"ast-grep cannot match pattern {pattern!r}: {e}") from None


def _match_text(node) -> str:
    text = " ".join(node.text().split())
    return text if len(text) <= _MATCH_TEXT_MAX else text[:_MATCH_TEXT_MAX] + "\u2026"


def _expand(rewrite: str, node) -> str:
    """Substitute the pattern's own metavariables into the rewrite string —
    the binding's ``replace()`` inserts literally, there is no fix engine.

    Only metavars the pattern actually CAPTURED expand, so a ``$`` that
    belongs to the target language (a JS template literal, a shell variable,
    a PHP variable) survives untouched. That is ast-grep's own rule, and it
    is why ``$NAME`` needs no escaping here.

    A ``$$$MULTI`` expands to the SOURCE SPAN it captured, not to its
    captures joined: tree-sitter hands back the punctuation too (``$$$REST``
    on ``join(a, b, c)`` is [b, ",", c]), so joining re-invents separators
    and produces ``b, ,, c``. First capture's start to last capture's end,
    sliced out of the root text, is the original source verbatim.
    """

    def sub(match: re.Match) -> str:
        token = match.group(0)
        name = token.lstrip("$")
        if token.startswith("$$$"):
            multi = node.get_multiple_matches(name)
            if not multi:
                return token
            source = node.get_root().root().text()
            return source[
                multi[0].range().start.index : multi[-1].range().end.index
            ]
        hit = node.get_match(name)
        return hit.text() if hit is not None else token

    return _METAVAR.sub(sub, rewrite)


def _ast_scan(files: list[Path], pattern: str, lang: str | None, limit: int):
    """Structural search, synchronous — tree-sitter parsing is CPU work and
    belongs off the kernel's loop. Stops at limit matches."""
    matches: list[SearchMatch] = []
    for path in files:
        text = _read_text(path)
        if text is None:
            continue
        _, nodes = _parse(text, lang or _lang_of(path), pattern)
        for node in nodes:
            matches.append(
                SearchMatch(str(path), node.range().start.line + 1, _match_text(node))
            )
            if len(matches) > limit:
                return matches[:limit], True
    return matches, False


def _non_overlapping(nodes: list) -> list:
    """The matches to actually edit: outermost wins, left to right.

    A greedy pattern (``$CALL``, ``$$$BODY``) matches NESTED nodes too, and
    commit_edits on overlapping ranges does not complain — it splices
    garbage out of the file (``f(g(x))`` came back as ``wrapped(f(g(x))\\n)``
    from the pattern ``$CALL``). So overlapping matches are dropped, the
    same non-overlapping scan re.sub does, and the caller reports how many.
    """
    ordered = sorted(
        nodes, key=lambda n: (n.range().start.index, -n.range().end.index)
    )
    kept = []
    end = -1
    for node in ordered:
        span = node.range()
        if span.start.index >= end:
            kept.append(node)
            end = span.end.index
    return kept


def _plan_rewrites(files: list[Path], pattern: str, rewrite: str, lang: str | None):
    """Every (path, old_text, new_text) the rewrite would produce, computed
    BEFORE anything is written: a bad pattern — or one unwritable file —
    fails with the whole tree untouched."""
    planned: list[tuple[Path, str, str]] = []
    scanned = 0
    matches = 0
    skipped = 0
    for path in files:
        text = _read_text(path)
        if text is None:
            continue
        scanned += 1
        root, nodes = _parse(text, lang or _lang_of(path), pattern)
        if not nodes:
            continue
        kept = _non_overlapping(nodes)
        skipped += len(nodes) - len(kept)
        matches += len(kept)
        new_text = root.commit_edits(
            [node.replace(_expand(rewrite, node)) for node in kept]
        )
        if new_text == text:
            continue
        if not os.access(path, os.W_OK):
            raise FsError(f"permission denied: {path} — nothing was written")
        planned.append((path, text, new_text))
    return planned, scanned, matches, skipped


async def _ast(
    root: Path, pattern: str, lang: str | None, file_pattern: str | None, limit: int
) -> SearchResult:
    files = _candidates(await _walk(root, file_pattern), lang)
    matches, truncated = await asyncio.to_thread(_ast_scan, files, pattern, lang, limit)
    return SearchResult(
        pattern=pattern, root=str(root), matches=matches, truncated=truncated
    )


async def _rewrite(
    root: Path,
    pattern: str,
    rewrite: str,
    lang: str | None,
    file_pattern: str | None,
) -> RewriteResult:
    files = _candidates(await _walk(root, file_pattern), lang)
    planned, scanned, matches, skipped = await asyncio.to_thread(
        _plan_rewrites, files, pattern, rewrite, lang
    )
    # Call-time import on purpose: reload() refreshes fs BEFORE write, so a
    # module-level `from .write import write` would keep the stale function.
    from .write import write

    results = [await write(str(path), new_text) for path, _, new_text in planned]
    return RewriteResult(
        pattern=pattern,
        rewrite=rewrite,
        root=str(root),
        files=results,
        scanned=scanned,
        matches=matches,
        skipped=skipped,
    )


@subtool(tool="fs")
async def fs(
    mode: str,
    path: str | None = None,
    pattern: str | None = None,
    offset: int = 1,
    limit: int | None = None,
    file_pattern: str | None = None,
    lang: str | None = None,
    rewrite: str | None = None,
):
    """Read a file, glob for files, search their contents, or rewrite their syntax.

    Args:
        mode: "read", "glob", "search", "ast" or "rewrite".
        path: read — the file. every other mode — the root directory to walk
            (default: the kernel's cwd). Absolute, or relative to cwd.
        pattern: glob — a gitignore-style glob ("**/*.py", "tests/*_fs.py").
            search — a regex (rg's; "(?i)" for case-insensitive). ast and
            rewrite — an ast-grep pattern, where $NAME captures one node and
            $$$NAME captures many ("os.path.join($A, $B)",
            "def $F($$$ARGS): $$$BODY").
        offset: read only — 1-indexed first line (default 1).
        limit: cap per mode — read: lines (2000), glob: files (500), search
            and ast: matches (200). Result carries .truncated.
        file_pattern: glob/search/ast/rewrite — restrict the walk to files
            matching a glob (rg -g, e.g. "*.py").
        lang: ast/rewrite only — one grammar instead of every mapped
            extension (python, javascript, typescript, tsx, jsx, rust, go,
            c, cpp, csharp, java, ruby, html, css, json, yaml, markdown,
            bash, kotlin, swift, php, lua, scala, elixir, haskell, dart,
            nix, solidity). Unsupported languages raise — the binding panics
            on them, so they are refused before they get near it.
        rewrite: rewrite only — the replacement, with the pattern's own
            metavariables substituted ($A, $$$ARGS). A $ that the pattern
            did not capture is left alone, so target-language $ syntax
            survives.

    Returns:
        read -> FileResult (.content raw, .text line-numbered, .lines,
        .offset, .shown, .truncated); glob -> GlobResult (.paths,
        .truncated); search and ast -> SearchResult (.matches of
        SearchMatch(path, line, text), .paths deduplicated, .text rendered,
        .truncated); rewrite -> RewriteResult (.files of EditResult, .paths,
        .changed, .scanned, .matches, .summary).

    Raises:
        FsError: missing mode/path/pattern/rewrite, directory or image or
            binary or oversized file on read, unsupported language,
            unmatchable ast pattern, ripgrep absent, failed or timed out.

    Note:
        The model sees only what the cell PRINTS — ``print(r.text)`` after a
        read/search/ast, ``print(r.summary)`` after a rewrite. The client
        gets its own view regardless: a read arrives as a read-kind call
        located at the file, glob/search/ast as text, and a rewrite as one
        edit-kind diff call PER FILE (each went through write()) plus the
        rewrite's own summary call.
    """
    if mode == "read":
        if not path:
            raise FsError("mode='read' requires path=")
        try:
            target = _resolve_path(path)
        except ValueError as e:
            raise FsError(str(e)) from None
        # Blocking file IO — keep the kernel's loop responsive.
        return await asyncio.to_thread(_read, target, int(offset), _cap(limit, mode))

    if mode in ("glob", "search", "ast", "rewrite"):
        if not pattern:
            raise FsError(f"mode={mode!r} requires pattern=")
        if mode == "rewrite" and not rewrite:
            raise FsError("mode='rewrite' requires rewrite=")
        if lang is not None and lang not in _LANGS:
            raise FsError(
                f"unsupported ast language {lang!r} — expected one of:"
                f" {', '.join(_LANGS)}"
            )
        try:
            root = _resolve_path(path or ".")
        except ValueError as e:
            raise FsError(str(e)) from None
        if not root.is_dir():
            raise FsError(f"not a directory: {root}")
        if mode == "glob":
            return await _glob(root, pattern, _cap(limit, mode))
        if mode == "search":
            return await _search(root, pattern, _cap(limit, mode), file_pattern)
        if mode == "ast":
            return await _ast(root, pattern, lang, file_pattern, _cap(limit, "search"))
        return await _rewrite(root, pattern, rewrite, lang, file_pattern)

    raise FsError(
        f"unknown fs mode {mode!r} — expected 'read', 'glob', 'search',"
        " 'ast' or 'rewrite'"
    )
