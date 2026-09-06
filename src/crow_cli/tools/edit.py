"""edit — the file editor, Python-shaped.

Same nine-level fuzzy engine as the MCP tool (imported from
crow_cli.mcp.editor.main, not duplicated — the engine ``replace()`` is
already a pure function that raises ValueError; the MCP wrapper is what
flattens it into "Error: ..." strings). The contract here is the Python
one: raise EditError on failure, return an EditResult later cells can
reuse (.diff, .old_text, .new_text). Nothing about the call reaches the
model on its own — the cell's stdout is the LLM channel, and the ACP
client gets the diff on its own.
"""

from __future__ import annotations

import difflib

from crow_cli.mcp.editor.main import _resolve_path, replace

from .register import subtool
from .results import EditError, EditResult


def _in_file_endings(text: str, old_string: str, new_string: str):
    """The caller's strings, in the file's own line endings.

    The model saw this file through ``read``, which normalizes endings for
    display, so its old_string arrives with bare ``\\n`` even when the file is
    CRLF. Matching that against a faithful read needs the translation — and
    the replacement needs it too, or the edit splices LF lines into a CRLF
    file. Only the dominant ending is considered: a file that is mostly CRLF
    is a CRLF file. A caller who sends CRLF explicitly is already speaking
    the file's language and is left alone.
    """
    if "\r\n" in text and "\r\n" not in old_string:
        # Normalize first, so a mixed-ending replacement cannot double up
        # into \r\r\n.
        return (
            old_string.replace("\r\n", "\n").replace("\n", "\r\n"),
            new_string.replace("\r\n", "\n").replace("\n", "\r\n"),
        )
    return old_string, new_string


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

    Note:
        The model sees only what the cell PRINTS — the return value is for
        code, not for the conversation. ``print(res.diff)`` to surface it.
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
        # newline="": read the file as it is. The default translates every
        # \r\n to \n, and the write below used to hand that back — so ONE
        # edit to a CRLF file silently reformatted all of it, with a diff
        # that showed a single changed line (unified_diff is fed
        # splitlines(), which strips \r from both sides).
        old_text = path.read_text(encoding="utf-8", newline="")
    except PermissionError:
        raise EditError(f"Permission denied: {path}") from None
    except OSError as e:
        raise EditError(f"Failed to read file: {e}") from None

    old_string, new_string = _in_file_endings(old_text, old_string, new_string)
    try:
        new_text = replace(old_text, old_string, new_string, replace_all)
    except ValueError as e:
        raise EditError(str(e)) from None

    try:
        path.write_text(new_text, encoding="utf-8", newline="")
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
