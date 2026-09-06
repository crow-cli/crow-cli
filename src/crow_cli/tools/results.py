"""Result objects for crow_cli.tools — the Python channel of the three-fold split.

A tool call inside an execute cell produces three outputs, and only one of
them is the return value:

1. Python — what the calling code gets back: these result objects. Truthy
   on success, real attributes for reuse in later cells (EditResult.diff,
   VisionResult.image as a PIL Image). Failures RAISE (ToolError
   subclasses); "Error: ..." strings are an MCP wire convention, not a
   Python one. No designed reprs: execute returns what the cell PRINTED,
   so display strings are not a channel — print() is.
2. ACP — what the client sees: ``acp_payload()`` returns a JSON-native
   semantic dict (diff, image ref, text). The server-side drain renders it
   into acp types (ToolCallStart/Progress content); this package never
   imports acp.
3. LLM — what the model sees: execute's output — stdout + stderr, or the
   traceback on failure — UNMODIFIED. The one exception, and the only
   reason this channel exists: when vision tools ran, hydrated image_url
   blocks are PREPENDED to that output, or vision models could never see
   images. The signal is ``llm_images()`` ImageStore refs riding the DB
   row — non-empty means prepend (has_vision, in effect). No text
   markers, no repr tricks, no blob autodetection.
"""

from __future__ import annotations

from dataclasses import dataclass


class ToolError(Exception):
    """Base for tool failures — raised, never returned as strings."""


class ToolResult:
    """Base for the Python channel. Subclasses declare their ACP/LLM split."""

    result_kind: str = "text"

    def acp_payload(self) -> dict | None:
        return None

    def llm_images(self) -> list[dict]:
        """ImageStore refs ``[{"key": ..., "mime": ...}]``, hydrated at drain."""
        return []

    def __bool__(self) -> bool:
        return True


@dataclass
class EditResult(ToolResult):
    path: str
    old_text: str
    new_text: str
    diff: str = ""

    result_kind = "diff"

    def acp_payload(self) -> dict:
        # Mirrors agent/tools.py execute_acp_edit: whole-file old/new text,
        # rendered as tool_diff_content at emission time.
        return {
            "content": "diff",
            "path": self.path,
            "old_text": self.old_text,
            "new_text": self.new_text,
        }

    @property
    def added(self) -> int:
        return sum(
            1
            for ln in self.diff.splitlines()
            if ln.startswith("+") and not ln.startswith("+++")
        )

    @property
    def removed(self) -> int:
        return sum(
            1
            for ln in self.diff.splitlines()
            if ln.startswith("-") and not ln.startswith("---")
        )


class EditError(ToolError):
    pass


@dataclass
class VisionResult(ToolResult):
    """One captured image. Bytes live in the ImageStore under ``key``
    (content-addressed ``<sha256hex><ext>``, same scheme as message
    images) — the result object, the register entry, and the DB row all
    hold refs, never bytes.

    Code gets a real image: ``.image`` loads the bytes from the store as a
    PIL Image (save/resize/compose/pass along). The LLM side needs no
    marker anywhere: ``llm_images()`` refs ride the row, and the
    server-side drain prepends hydrated image_url blocks to execute's
    output when any are present (has_vision, in effect).
    """

    key: str
    mime: str
    width: int
    height: int
    source: str  # original file path, or "webcam:<device_index>"

    result_kind = "image"

    def acp_payload(self) -> dict:
        # Rendered server-side into an acp image content block — bytes
        # hydrated from the ImageStore by key at emission time.
        return {"content": "image", "key": self.key, "mime": self.mime}

    def llm_images(self) -> list[dict]:
        return [{"key": self.key, "mime": self.mime}]

    @property
    def image(self):
        """The bytes as a PIL Image, loaded from the ImageStore."""
        import io

        from PIL import Image

        from .register import image_store

        store = image_store()
        raw = store.get(self.key) if store is not None else None
        if raw is None:
            raise VisionError(f"image blob missing from store: {self.key}")
        return Image.open(io.BytesIO(raw))


class VisionError(ToolError):
    pass


@dataclass
class FileResult(ToolResult):
    """One file's window, read.

    ``content`` is the window's lines joined with ``\\n`` — what code wants
    (slice it, regex it, hand it to edit). Note that this NORMALIZES line
    endings: a CRLF file comes back with LF, so writing ``content`` back
    would re-write the whole file's endings. ``text`` is the same window
    line-numbered, with the paging notice when the file was cut, which is
    what print() should show and what the client renders.

    ``shown`` is a field, not ``len(content.splitlines())``: a window
    holding a single empty line has content ``""``, which splitlines()
    counts as zero.
    """

    path: str
    content: str
    text: str
    lines: int  # total lines in the file
    offset: int = 1  # 1-indexed first line of the window
    shown: int = 0  # lines in the window

    result_kind = "read"

    def acp_payload(self) -> dict:
        # Mirrors agent/tools.py execute_acp_read: the numbered text on a
        # read-kind call, located at the path.
        return {"content": "read", "path": self.path, "text": self.text}

    @property
    def truncated(self) -> bool:
        return self.offset - 1 + self.shown < self.lines


@dataclass
class GlobResult(ToolResult):
    """Files matching a gitignore-style pattern under a root."""

    pattern: str
    root: str
    paths: list[str]
    truncated: bool = False

    result_kind = "search"

    def acp_payload(self) -> dict:
        return {
            "content": "text",
            "text": "\n".join(self.paths) or f"no files match {self.pattern}",
        }


@dataclass
class SearchMatch:
    """One ripgrep hit — a plain record, not a channel of its own."""

    path: str
    line: int
    text: str


@dataclass
class SearchResult(ToolResult):
    """Regex hits under a root, structured for code and rendered for print."""

    pattern: str
    root: str
    matches: list[SearchMatch]
    truncated: bool = False

    result_kind = "search"

    def acp_payload(self) -> dict:
        return {"content": "text", "text": self.text or f"no matches for {self.pattern}"}

    @property
    def text(self) -> str:
        return "\n".join(f"{m.path}:{m.line}: {m.text}" for m in self.matches)

    @property
    def paths(self) -> list[str]:
        """The files that matched, in hit order, deduplicated."""
        return list(dict.fromkeys(m.path for m in self.matches))


class FsError(ToolError):
    pass


@dataclass
class RewriteResult(ToolResult):
    """A multi-file replace — by syntax (``rewrite``) or by regex (``sub``).

    Each changed file was written through ``write()``, so every one of them
    is its OWN subtool row and its own diff on the client — this result is
    the operation that caused them, and its payload is the summary, not N
    copies of N files. ``.files`` holds the EditResults for code that wants
    the diffs (and the preimages: each carries whole old_text/new_text, so
    crow.db is the undo log — no separate shadow store needed).

    ``matches`` counts the edits APPLIED, and ``skipped`` the matches dropped
    because they overlapped one already applied: a greedy pattern
    (``$CALL``) matches nested nodes, and committing overlapping edits
    corrupts the file, so the outermost match wins and the ones inside it
    are dropped — left-to-right non-overlapping, like re.sub.

    A rewrite that reproduces the source counts as a match and changes no
    file, so ``changed == 0`` with ``matches > 0`` reads as what it is: the
    pattern hit, the rewrite was a no-op.

    ``syntax`` says which engine ran: ``"ast"`` (an ast-grep pattern, whose
    own metavariables expand in the replacement) or ``"regex"`` (Python
    ``re``, so the replacement is a Python replacement template — ``\\1``,
    ``\\g<name>``). ``skipped`` only means anything for ``"ast"``: re.sub is
    non-overlapping by definition.

    ``dry_run`` planned everything and wrote nothing. ``.files`` still holds
    real EditResults with real diffs, so ``print(r.diff)`` shows exactly what
    WOULD change — and no diff reaches the client, because nothing happened
    to the files and a diff view over an untouched file is a lie.
    """

    pattern: str
    rewrite: str
    root: str
    files: list  # EditResult per changed file
    scanned: int  # files parsed (ast) or read (regex)
    matches: int  # matches APPLIED
    skipped: int = 0  # matches dropped for overlapping an applied one
    syntax: str = "ast"  # "ast" | "regex"
    dry_run: bool = False

    # Not "text": a rewrite MODIFIES files, so the client shows it as an
    # edit-kind call even though its payload is the summary. Keyed here
    # rather than left to get_tool_kind's substring rules, which classify
    # "rewrite" as an edit only because it happens to contain "write" — and
    # "sub" does not.
    result_kind = "rewrite"

    def acp_payload(self) -> dict:
        return {"content": "text", "text": self.summary}

    @property
    def changed(self) -> int:
        return len(self.files)

    @property
    def paths(self) -> list[str]:
        return [f.path for f in self.files]

    @property
    def diff(self) -> str:
        """Every changed file's unified diff, concatenated.

        This is the LLM's half of a multi-file replace: the per-file diffs
        go to the CLIENT on their own calls, and the model sees only what the
        cell printed — so ``print(r.diff)`` is how it sees what it did (or,
        with dry_run=True, what it is about to do).
        """
        return "\n".join(f.diff for f in self.files if f.diff)

    @property
    def summary(self) -> str:
        overlap = f", {self.skipped} overlapping skipped" if self.skipped else ""
        noun = "parsed" if self.syntax == "ast" else "scanned"
        verb = "[DRY RUN] would rewrite" if self.dry_run else "rewrote"
        return (
            f"{verb} {self.changed} of {self.scanned} {noun} file(s), "
            f"{self.matches} match(es){overlap}: {self.pattern} -> {self.rewrite}"
        )


