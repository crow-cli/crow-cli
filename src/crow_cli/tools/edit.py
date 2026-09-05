"""edit — the file editor, Python-shaped.

Same nine-level fuzzy engine as the MCP tool (imported from
crow_cli.mcp.editor.main, not duplicated — the engine ``replace()`` is
already a pure function that raises ValueError; the MCP wrapper is what
flattens it into "Error: ..." strings). The contract here is the Python
one: raise EditError on failure, return an EditResult the REPL prints as
one line and later cells can reuse (.diff, .old_text, .new_text).
"""

from __future__ import annotations

import difflib

from crow_cli.mcp.editor.main import _resolve_path, replace

from .register import subtool
from .results import EditError, EditResult


@subtool(tool="edit")
async def edit(
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> EditResult:
    """Replace old_string with new_string in a file (nine-level fuzzy matching).

    Args:
        file_path: Path to the file (absolute, or relative to the kernel cwd).
        old_string: Text to replace — must be unique unless replace_all.
        new_string: Replacement text.
        replace_all: Replace every occurrence (renames).

    Returns:
        EditResult with .path, .old_text, .new_text, .diff, .added, .removed.

    Raises:
        EditError: file missing/unreadable, no match, or ambiguous match.
    """
    if old_string == new_string:
        raise EditError("old_string and new_string must be different")

    try:
        path = _resolve_path(file_path)
    except ValueError as e:
        raise EditError(str(e)) from None

    if not path.exists():
        raise EditError(f"File does not exist: {path}")
    if not path.is_file():
        raise EditError(f"Path is a directory: {path}")

    try:
        old_text = path.read_text(encoding="utf-8")
    except PermissionError:
        raise EditError(f"Permission denied: {path}") from None
    except OSError as e:
        raise EditError(f"Failed to read file: {e}") from None

    try:
        new_text = replace(old_text, old_string, new_string, replace_all)
    except ValueError as e:
        raise EditError(str(e)) from None

    try:
        path.write_text(new_text, encoding="utf-8")
    except PermissionError:
        raise EditError(f"Permission denied: {path}") from None
    except OSError as e:
        raise EditError(f"Failed to write file: {e}") from None

    diff = "\n".join(
        difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=f"a/{path.name}",
            tofile=f"b/{path.name}",
            lineterm="",
        )
    )
    return EditResult(
        path=str(path), old_text=old_text, new_text=new_text, diff=diff
    )
