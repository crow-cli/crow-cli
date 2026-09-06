"""write — create or overwrite files, Python-shaped.

Same contract as edit: raise WriteError on failure, return an EditResult
(a write IS a diff — old_text is "" for new files, the previous content
for overwrites) so the client sees created/changed files exactly like
edits. The MCP wrapper's "Error: ..." strings stay on the MCP side.
"""

from __future__ import annotations

import difflib

from crow_cli.mcp.editor.main import _resolve_path

from .register import subtool
from .results import EditResult, ToolError


class WriteError(ToolError):
    pass


@subtool(tool="write")
async def write(file_path: str, content: str) -> EditResult:
    """Write content to a file, creating it (and parent dirs) or overwriting.

    Args:
        file_path: Path to the file (absolute, or relative to the kernel cwd).
        content: Full content to write.

    Returns:
        EditResult with .path, .old_text ("" when new), .new_text, .diff,
        .added, .removed.

    Raises:
        WriteError: path is a directory, permission denied, or write failed.

    Note:
        The model sees only what the cell PRINTS — the return value is for
        code, not for the conversation. ``print(res.diff)`` (or res.path,
        res.added) to surface it. The ACP client gets the diff on its own
        channel regardless of what the cell prints.
    """
    try:
        path = _resolve_path(file_path)
    except ValueError as e:
        raise WriteError(str(e)) from None

    if path.is_dir():
        raise WriteError(f"Path is a directory: {path}")

    old_text = ""
    if path.exists():
        try:
            # newline="": the preimage is the undo log, so it has to be the
            # bytes that were actually there. The default translation turns
            # every \r\n into \n, and restoring that "undo" would silently
            # reformat the whole file.
            old_text = path.read_text(encoding="utf-8", newline="")
        except UnicodeDecodeError:
            old_text = ""  # binary-ish file: diff against empty
        except OSError:
            old_text = ""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise WriteError(f"Permission denied creating directory: {path.parent}") from None
    except OSError as e:
        raise WriteError(f"Failed to create directory: {e}") from None

    try:
        # newline="": write the string the caller passed, byte for byte. The
        # default translates every \n to os.linesep, which on Windows turns a
        # CRLF file's endings into \r\r\n.
        path.write_text(content, encoding="utf-8", newline="")
    except PermissionError:
        raise WriteError(f"Permission denied: {path}") from None
    except OSError as e:
        raise WriteError(f"Failed to write file: {e}") from None

    diff = "\n".join(
        difflib.unified_diff(
            old_text.splitlines(),
            content.splitlines(),
            fromfile=f"a/{path.name}",
            tofile=f"b/{path.name}",
            lineterm="",
        )
    )
    return EditResult(
        path=str(path), old_text=old_text, new_text=content, diff=diff
    )
