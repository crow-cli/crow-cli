"""fs — read, glob, search: the filesystem, Python-shaped.

Modes:
- ``read``   — one file as a line-numbered window (offset/limit). The old
  MCP read tool's contract, ported here rather than imported: crow_cli.mcp
  is pared to execute in the endgame, and this is the part that survives.
- ``glob``   — gitignore-style pattern -> matching FILES under a root.
- ``search`` — regex -> structured matches (path, line, text) under a root.

glob and search both shell out to ripgrep, which is why they get real
gitignore semantics for free (nested .gitignore, .git/info/exclude, hidden
files skipped) instead of a reimplementation: one engine, two modes. It is
an external binary — absent, fs raises rather than degrading.

Images are refused politely: reading a png as text is never what the caller
meant, and vision(mode="file") is.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from crow_cli.mcp.editor.main import _resolve_path

from .register import subtool
from .results import FileResult, FsError, GlobResult, SearchMatch, SearchResult

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
    plus the paging notice when the file was cut."""
    padding = len(str(offset + len(lines) - 1)) if lines else len(str(offset))
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
    )


def _rg() -> str:
    found = shutil.which("rg")
    if found is None:
        raise FsError("ripgrep (rg) is not on PATH — fs glob and search need it")
    return found


def _excludes() -> list[str]:
    return [arg for name in _ALWAYS_EXCLUDE for arg in ("-g", f"!{name}/")]


async def _run(argv: list[str], root: Path) -> str:
    """Run rg with cwd=root and "." as the search path. Exit 1 means "no
    matches", not failure.

    The cwd is not a detail: rg matches -g patterns that contain a slash
    against the path RELATIVE TO THE CWD, not relative to the search path,
    so `-g 'src/tools/*.py' /abs/root` from anywhere else matches nothing
    (slashless patterns like '*.py' match at any level and hide the bug).
    Running in the root makes patterns and output root-relative and
    deterministic; callers absolutize.
    """
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), _RG_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise FsError(f"ripgrep timed out after {_RG_TIMEOUT}s") from None
    if proc.returncode not in (0, 1):
        detail = err.decode(errors="replace").strip()
        raise FsError(f"ripgrep failed ({proc.returncode}): {detail}")
    return out.decode(errors="replace")


async def _glob(root: Path, pattern: str, limit: int) -> GlobResult:
    argv = [
        _rg(),
        "--files",
        "--no-messages",
        "--no-config",
        "--sort",
        "path",  # rg searches in parallel: unsorted output is nondeterministic
        *_excludes(),
        "-g",
        pattern,
        ".",
    ]
    out = await _run(argv, root)
    paths = [str(root / ln) for ln in out.splitlines() if ln]
    return GlobResult(
        pattern=pattern,
        root=str(root),
        paths=paths[:limit],
        truncated=len(paths) > limit,
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
    out = await _run(argv, root)

    matches: list[SearchMatch] = []
    for line in out.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("type") != "match":
            continue
        data = record["data"]
        matches.append(
            SearchMatch(
                path=str(root / (data.get("path") or {}).get("text", "")),
                line=data.get("line_number") or 0,
                text=(data.get("lines") or {}).get("text", "").rstrip("\n"),
            )
        )
        if len(matches) > limit:
            break
    return SearchResult(
        pattern=pattern,
        root=str(root),
        matches=matches[:limit],
        truncated=len(matches) > limit,
    )


@subtool(tool="fs")
async def fs(
    mode: str,
    path: str | None = None,
    pattern: str | None = None,
    offset: int = 1,
    limit: int | None = None,
    file_pattern: str | None = None,
):
    """Read a file, glob for files, or search their contents.

    Args:
        mode: "read", "glob" or "search".
        path: read — the file. glob/search — the root directory to walk
            (default: the kernel's cwd). Absolute, or relative to cwd.
        pattern: glob — a gitignore-style glob ("**/*.py", "tests/*_fs.py").
            search — a regex (rg's; "(?i)" for case-insensitive).
        offset: read only — 1-indexed first line (default 1).
        limit: cap per mode — read: lines (2000), glob: files (500),
            search: matches (200). Result carries .truncated.
        file_pattern: search only — restrict to files matching a glob
            (rg -g, e.g. "*.py").

    Returns:
        read -> FileResult (.content raw, .text line-numbered, .lines,
        .offset, .shown, .truncated); glob -> GlobResult (.paths,
        .truncated); search -> SearchResult (.matches of SearchMatch(path,
        line, text), .paths deduplicated, .text rendered, .truncated).

    Raises:
        FsError: missing mode/path/pattern, directory or image or binary or
            oversized file on read, ripgrep absent, failed or timed out.

    Note:
        The model sees only what the cell PRINTS — ``print(r.text)`` after a
        read, ``print(r.text)`` or ``print(*r.paths, sep="\\n")`` after a
        search/glob. The client gets its own view regardless: a read arrives
        as a read-kind tool call located at the file, glob/search as text.
    """
    if mode == "read":
        if not path:
            raise FsError("mode='read' requires path=")
        try:
            target = _resolve_path(path)
        except ValueError as e:
            raise FsError(str(e)) from None
        cap = limit if limit is not None else _DEFAULT_LIMIT["read"]
        # Blocking file IO — keep the kernel's loop responsive.
        return await asyncio.to_thread(_read, target, int(offset), int(cap))

    if mode in ("glob", "search"):
        if not pattern:
            raise FsError(f"mode={mode!r} requires pattern=")
        try:
            root = _resolve_path(path or ".")
        except ValueError as e:
            raise FsError(str(e)) from None
        if not root.is_dir():
            raise FsError(f"not a directory: {root}")
        cap = limit if limit is not None else _DEFAULT_LIMIT[mode]
        if mode == "glob":
            return await _glob(root, pattern, int(cap))
        return await _search(root, pattern, int(cap), file_pattern)

    raise FsError(f"unknown fs mode {mode!r} — expected 'read', 'glob' or 'search'")
