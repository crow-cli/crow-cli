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

from dataclasses import dataclass, field
from typing import Any


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


# A printed page is windowed; the object is not. 5000 chars is what the MCP
# fetch tool returned per call, kept as the default so print(r.text) costs
# about what it used to — but r.markdown is the whole page and slicing it is
# Python, not a pagination protocol.
_PAGE_WINDOW = 5000


@dataclass
class WebHit:
    """One search result — a plain record, not a channel of its own.

    ``score`` is SearXNG's aggregate relevance and ``engines`` the engines
    that returned this URL, which is how one engine's opinion is told apart
    from five engines agreeing.
    """

    url: str
    title: str
    content: str
    score: float = 0.0
    engines: list[str] = field(default_factory=list)
    published: str = ""


@dataclass
class WebInfobox:
    """An entity card — SearXNG's encyclopaedic answer to "python"."""

    topic: str
    url: str
    content: str


@dataclass
class WebSearchResult(ToolResult):
    """One query's hits, structured for code and rendered for print.

    ONE query per call: the MCP tool took a list and looped over it
    SEQUENTIALLY, because it had to return one string. Here the model writes
    ``await asyncio.gather(*[web("search", q) for q in queries])`` and gets
    real parallelism plus one of these per query.

    ``answers``, ``infoboxes``, ``suggestions``, ``corrections`` and
    ``unresponsive`` are the parts of SearXNG's response the MCP tool threw
    away. ``unresponsive`` is the important one: ``["duckduckgo (CAPTCHA)"]``
    is the difference between "thin results, refine the query" and "thin
    results, the backend is degraded" — and web search is not optional
    equipment, so a degraded backend must not be able to hide behind an
    empty result list.
    """

    query: str
    hits: list[WebHit]
    total: int = 0  # hits SearXNG returned, before the limit
    answers: list[str] = field(default_factory=list)
    infoboxes: list[WebInfobox] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)
    unresponsive: list[str] = field(default_factory=list)

    result_kind = "search"

    def acp_payload(self) -> dict:
        return {
            "content": "text",
            "text": self.text,
            "subject": self.query,
        }

    @property
    def truncated(self) -> bool:
        return len(self.hits) < self.total

    @property
    def urls(self) -> list[str]:
        return [h.url for h in self.hits]

    @property
    def text(self) -> str:
        blocks = [f"ANSWER: {a}" for a in self.answers]
        blocks += [f"{ib.topic} — {ib.url}\n{ib.content}" for ib in self.infoboxes]
        blocks += [
            f"{i}. {h.title}\n   {h.url}\n   {h.content}"
            for i, h in enumerate(self.hits, 1)
        ]
        notes = []
        if self.corrections:
            notes.append(f"corrections: {', '.join(self.corrections)}")
        if self.suggestions:
            notes.append(f"suggestions: {', '.join(self.suggestions)}")
        if self.unresponsive:
            notes.append(f"ENGINES DOWN: {', '.join(self.unresponsive)}")
        head = f"{self.query} — {len(self.hits)} of {self.total} hits"
        return "\n".join([head, *blocks, *notes])


@dataclass
class PageResult(ToolResult):
    """One page: the WHOLE thing for code, a window for print.

    ``markdown`` is the extraction and ``html`` the raw body, both complete —
    there is no start_index/max_length, because those existed only to slice
    one string across several MCP calls, and ``r.markdown[5000:9000]`` is
    Python. ``text`` is the windowed rendering (a header line, the first
    characters, and how many are left plus how to get them) so ``print(r)``'s
    output cannot flood the context: the same content/text split FileResult
    draws.

    ``extracted`` says whether readability produced an article. False means
    ``markdown`` IS the body — a JSON response, a text file, or a JS shell
    with nothing to extract — which is honest where the MCP tool returned
    the string "<error>Failed to parse HTML</error>" and lost the page.

    ``rendered`` is the distinction a browser buys: True means a real
    chromium executed the page's JavaScript and ``html`` is the DOM it
    produced, not the bytes the server sent. Same shape for both modes
    because it is the same artifact — one page read.

    ``screenshot`` composes a VisionResult rather than duplicating its
    fields, so ``r.screenshot.image`` is a PIL Image and its ``llm_images()``
    ref rides this row: the drain hydrates it into an image_url block and a
    vision model SEES the page. ``page`` is the live playwright Page (run
    only) — clicking, typing and framing stay raw playwright in the kernel
    instead of a bad reimplementation of the playwright API here. It stays
    live across cells until the NEXT run closes it, so a stale one raises
    rather than quietly pointing at a different navigation.
    """

    url: str  # the FINAL url, after redirects
    title: str
    status: int
    content_type: str
    markdown: str
    html: str
    extracted: bool = False
    rendered: bool = False
    screenshot: VisionResult | None = None
    page: Any = None

    # Not "read": a page is not a file, and the read branch of the drain
    # stamps locations=[path] — a URL in a path field is a lie. The drain
    # files "web" under fetch by ARTIFACT (_KIND_BY_RESULT), because the
    # mode name only happens to work for one of the two modes that produce
    # this: get_tool_kind("fetch") is "fetch", get_tool_kind("run") is
    # "other", and a browser loading a page is a fetch either way.
    result_kind = "web"

    def acp_payload(self) -> dict:
        return {"content": "text", "text": self.text, "subject": self.url}

    def llm_images(self) -> list[dict]:
        return self.screenshot.llm_images() if self.screenshot else []

    @property
    def chars(self) -> int:
        return len(self.markdown)

    @property
    def text(self) -> str:
        flags = []
        if not self.extracted:
            flags.append("unextracted")
        if self.rendered:
            flags.append("rendered")
        if self.screenshot is not None:
            flags.append("screenshot")
        head = (
            f"{self.url} — {self.status} {self.content_type.split(';')[0].strip()}"
            f", {self.chars:,} chars"
            + (f", {', '.join(flags)}" if flags else "")
        )
        body = self.markdown[:_PAGE_WINDOW]
        more = self.chars - len(body)
        tail = f"\n… {more:,} more chars — markdown[{len(body)}:]" if more else ""
        return f"{head}\n{body}{tail}"


@dataclass
class BrowserClosed(ToolResult):
    """web(mode="close") — the kernel's browser, shut down.

    ``was_running`` because closing twice is not an error and the two states
    are worth telling apart: False means the browser was never started, or
    something already tore it down.
    """

    was_running: bool

    result_kind = "text"

    def acp_payload(self) -> dict:
        return {"content": "text", "text": self.text}

    @property
    def text(self) -> str:
        return "browser closed" if self.was_running else "no browser was running"


class WebError(ToolError):
    pass


# Rows are cheap, message JSON is not: the live crow.db averages 6KB per
# message and holds 499MB of it, with a single 12.8MB outlier. The cap is
# set above the biggest legitimate read — one whole session's transcript,
# 32.3MB for the largest of 2695 sessions — so it only ever fires on a
# query that was going to take the kernel's RAM with it.
_MEMORY_BYTES = 64 * 1024 * 1024
_SUBJECT_MAX = 100


@dataclass
class MemoryResult(ToolResult):
    """Rows out of the agent's own memory, as a polars DataFrame.

    ``df`` is the artifact and it is a real DataFrame: filter it, group it,
    join it, print one column. polars' own repr is bounded in all three
    dimensions — 5 rows from each end, 4 columns from each end, ~30 chars
    per cell — so ``print(r.df)`` is a readable table of ANY result and can
    never flood the context, which is why there is no windowing here (the
    ``_PAGE_WINDOW`` a page needs) and no pagination (the ``offset`` a
    string-returning tool needs). Eight columns per mode, chosen so the repr
    elides nothing.

    ``sql`` is the statement that ran, even for the list and search modes
    that build it for you: reading it is how the schema gets learned without
    a second round trip, and it is the honest answer to "what did this
    actually ask for".

    ``total`` is the rows that matched before the limit, when that is cheap
    to know, so ``50 of 2695`` says "raise the limit" where ``50`` alone
    would not. ``truncated`` means the byte cap fired and the frame is a
    prefix of the answer — never silent, because a DataFrame that looks
    complete is indistinguishable from one that is.
    """

    df: Any  # polars DataFrame — duck-typed so this module imports no polars
    subject: str  # what was asked: the query, the session id, the SQL
    sql: str = ""
    total: int = 0
    truncated: bool = False

    # Not "read" by name: the drain files it under read by ARTIFACT
    # (_KIND_BY_RESULT), because the mode cannot decide it —
    # get_tool_kind("list") is "read" and get_tool_kind("search") is
    # "search", but all three modes are the same thing, rows read from a
    # connection that is read-only at the OS level.
    result_kind = "memory"

    def acp_payload(self) -> dict:
        return {
            "content": "text",
            "text": self.text,
            "subject": self.subject[:_SUBJECT_MAX],
        }

    @property
    def rows(self) -> int:
        return self.df.height

    @property
    def text(self) -> str:
        head = f"{self.subject} — {self.rows:,} row(s)"
        if self.total > self.rows:
            head += f" of {self.total:,} matching"
        lines = [head, repr(_compact(self.df))]
        if self.truncated:
            lines.append(
                f"… TRUNCATED at {_MEMORY_BYTES // (1024 * 1024)}MB — the frame"
                " is a prefix of the answer; narrow the query, select fewer"
                " columns, or add a LIMIT"
            )
        return "\n".join(lines)


def _compact(df: Any) -> Any:
    """The frame as ``.text`` renders it: ISO timestamps cut to the second.

    polars wraps a cell to the width its column got, and a full stamp
    (``2026-09-06T10:17:44.233789+00:00``) spends that width on microseconds
    and an offset the model cannot use — at a 100-char table budget it
    renders as ``2026-09-06T10`` / ``:17:44.233789`` / ``+00:…``, three lines
    whose readable content is the same 19 characters. Trimming is noise
    reduction first. The height it saves depends on the width budget AND on
    whether the stamp is the tallest cell in its row: measured on a 10-row
    messages frame, 27 lines -> 17 at 150 chars and nothing at 100 or 200. It
    never costs height, and ``id`` already carries the true order.

    ``.df`` keeps the whole stamp (and its lexicographic comparisons); this
    is the rendering, which is what ``.text`` is for.
    """
    import polars as pl

    stamps = [
        c
        for c in ("created_at", "last_activity")
        if c in df.columns and df.schema[c] == pl.String
    ]
    if not stamps:
        return df
    return df.with_columns([pl.col(c).str.slice(0, 19) for c in stamps])


class MemoryToolError(ToolError):
    """The memory tool failed.

    Not ``MemoryError``: that builtin means the process ran out of RAM, and a
    traceback reading "MemoryError: unknown memory mode 'lst'" would send the
    model hunting for a leak instead of a typo.
    """


