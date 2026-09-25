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


# A delegate's answer is the ONE thing that comes back into the caller's
# context, so it is the one thing rlm has to bound — a fork that answers at
# length has spent exactly what the delegation existed to save. Same default
# as a page: print(r.text) costs about what an MCP tool call used to, and
# r.answer is the whole thing.
_RLM_WINDOW = 5000


@dataclass
class RlmResult(ToolResult):
    """A delegation: what a fork of THIS session answered to one question.

    ``answer`` is the artifact and it is the WHOLE answer — ``.text`` windows
    it, the object does not, so slicing or grepping it stays Python rather
    than a pagination protocol.

    ``session_id`` is a handle, not a label — and it is the fork's WIRE id,
    which for a fork is its ``agent_id`` (``{session}-{agent}-{fork}``; a
    trunk's wire id is its bare session id). ``memory("list",
    session_id=...)`` resolves a bare session id OR a wire agent id, so the
    delegate's transcript is readable under that id — which is how an
    ``rlm(wait=False)`` delegation gets collected: this same object comes
    back with ``waited`` False and an empty ``answer``, and the transcript is
    the mailbox. No delivery table, because a task owner goes idle between
    launch and completion while an rlm caller is a running cell.

    ``depth`` is how deep this delegation went (1 for the first), which is
    the number the next one is refused against. ``stop_reason`` is the
    delegate's own: ``end_turn`` means it finished, and anything else means
    the answer is whatever it managed before it stopped.
    """

    session_id: str
    answer: str
    prompt: str
    waited: bool = True
    depth: int = 1
    stop_reason: str | None = None

    # get_tool_kind("rlm") matches no substring rule and falls to "other",
    # but a delegation is the artifact kind "think": reasoning paid for out
    # of a fork instead of out of the caller's context. Decided by
    # _KIND_BY_RESULT, by artifact, like every other shape in this module.
    result_kind = "rlm"

    def acp_payload(self) -> dict:
        return {
            "content": "text",
            "text": self.text,
            "subject": self.session_id,
        }

    @property
    def chars(self) -> int:
        return len(self.answer)

    @property
    def text(self) -> str:
        if not self.waited:
            return (
                f"delegate {self.session_id} is working (depth {self.depth}) —"
                " no answer yet. Its transcript is the mailbox:"
                f' memory("list", session_id="{self.session_id}").'
            )
        head = f"delegate {self.session_id} — depth {self.depth}"
        if self.stop_reason and self.stop_reason != "end_turn":
            head += f", stopped: {self.stop_reason}"
        head += f", {self.chars:,} chars"
        body = self.answer[:_RLM_WINDOW]
        more = self.chars - len(body)
        tail = f"\n… {more:,} more chars — answer[{len(body)}:]" if more else ""
        return f"{head}\n{body}{tail}"


class RlmToolError(ToolError):
    """A delegation could not be made, or the delegate could not be driven.

    The budget refusals land here too. A delegate that tries to delegate is
    not a crash — it is the one rule about forks that has to hold, or the
    mirror is back — so the message states the budget rather than the
    exception.
    """


# Same reasoning as _RLM_WINDOW: a subagent's answer is the one thing that
# comes back into the owner's context, so it is the one thing task has to
# bound. The object keeps the whole result; only the rendering is windowed.
_TASK_WINDOW = 5000


@dataclass
class TaskResult(ToolResult):
    """One background task: its handle, its state, and what it produced.

    ``task_id`` is the durable handle. It survives this cell, this kernel and
    this process because it is a row, which is what makes an async launch
    collectable later — by ``task_read``, or by the owner's mailbox when the
    task finishes and wakes it.

    ``session_id`` is the subagent's WIRE id and the key its transcript is
    stored under, so ``memory("list", session_id=...)`` reads the work rather
    than the summary of it. Empty until the child session exists.

    ``status`` is the row's: running, completed, failed or cancelled.
    ``result`` is the subagent's own last word when it completed and the error
    when it failed; it is empty while the task runs, and stays empty on an
    async launch even after the task finishes, because this object is a
    snapshot of one call and the completion goes to the mailbox instead. On a
    task that is NOT terminal-by-way-of-an-answer — a cancel whose teardown is
    still in flight, a row closed as orphaned — ``result`` carries the note
    explaining that, and ``.text`` renders it in place of the generic prose.

    ``waited`` says whether THIS call blocked for the outcome. ``poked`` says
    whether the wake reached the bus — reported rather than raised, because a
    missed poke costs latency and nothing else: the row is already committed
    and the owner's backstop poll delivers it.
    """

    task_id: str
    status: str
    session_id: str = ""
    prompt: str = ""
    result: str = ""
    waited: bool = False
    poked: bool = False

    # A task is orchestration, and ACP has no kind for "something else is
    # working on your behalf" — the same call v1's tool_kind made for the
    # orchestration names it exact-matches ahead of its substring rules.
    result_kind = "task"

    def acp_payload(self) -> dict:
        return {"content": "text", "text": self.text, "subject": self.task_id}

    @property
    def chars(self) -> int:
        return len(self.result)

    @property
    def text(self) -> str:
        head = f"{self.task_id}: {self.status}"
        if self.session_id:
            head += f" (subagent {self.session_id})"
        if self.status == "running":
            if self.result:
                # A note from the call that got here — a cancel whose teardown
                # is still in flight. It supersedes the generic prose because
                # it says something more specific about THIS state.
                return f"{head} — {self.result}"
            look = (
                f'read the transcript with memory("list",'
                f' session_id="{self.session_id}")'
            )
            if self.waited:
                # A wait that ran out is NOT a failure and must not read like
                # one: the subtool call is recorded as succeeded, the child is
                # alive, and the completion is still coming. Saying "still
                # running" without saying "you waited" invites the caller to
                # wait again, and again, until the turn is gone.
                return (
                    f"{head} — you waited for it and it is still going. That"
                    " is a timeout on the WAIT, not a failure of the task:"
                    " the child is alive and its completion will still land in"
                    f" your mailbox and wake you. To act now, {look} to see"
                    f' what it is stuck on, task_send("{self.task_id}", ...) to'
                    f' steer it, or task_cancel("{self.task_id}") to stop it.'
                )
            return (
                f"{head} — no result yet, and this object will not grow one."
                f" The completion lands in your mailbox and wakes you; to look"
                f" now, {look} or call task_read("
                f'"{self.task_id}").'
            )
        if self.status == "cancelled":
            note = f" {self.result}" if self.result else ""
            return f"{head} — cancelled, so there is no delivery to collect.{note}"
        head += f", {self.chars:,} chars"
        if not self.waited:
            head += " (this call did not wait for it)"
        body = self.result[:_TASK_WINDOW]
        more = self.chars - len(body)
        tail = f"\n… {more:,} more chars — result[{len(body)}:]" if more else ""
        return f"{head}\n{body}{tail}"


@dataclass
class TaskListResult(ToolResult):
    """Every task this session owns.

    ``tasks`` is the whole list for filtering in Python; ``.text`` is the
    table, which is what print() shows. Results are not repeated here — a
    list that carried every answer would cost exactly the context the task
    system exists to protect, so it carries handles and states and points at
    task_read for the one you want.
    """

    tasks: list[TaskResult] = field(default_factory=list)

    result_kind = "task"

    def acp_payload(self) -> dict:
        return {
            "content": "text",
            "text": self.text,
            "subject": f"{len(self.tasks)} tasks",
        }

    def __len__(self) -> int:
        return len(self.tasks)

    @property
    def text(self) -> str:
        if not self.tasks:
            return "no tasks — this session has launched none"
        width = max(len(t.task_id) for t in self.tasks)
        return "\n".join(
            f"{t.task_id:<{width}}  {t.status:<9}  {t.session_id or '-'}"
            for t in self.tasks
        )


class TaskError(ToolError):
    """A task could not be launched, steered or read.

    The refusals land here too, and they state the rule rather than the
    exception: a re-prompt aimed at a task that is still mid-turn is not a
    crash, it is the one ordering the redirect workflow depends on, so the
    message says to cancel first.
    """


@dataclass
class GoalResult(ToolResult):
    """The goal row after the model ended it — or found it already ended.

    ``status`` is read back off the row rather than echoed from the call, so
    it is the truth and not the intent: a goal the user paused mid-turn comes
    back ``paused``, because the model does not get to overrule the person who
    stopped it. ``changed`` says whether this call is what moved it. Both
    exits are idempotent on purpose — a model that has just decided the work
    is done should not have to reason about whether it already said so — and
    an idempotent call that quietly did nothing is a call that gets made
    again, so it says so out loud.

    ``reason`` is what ``goal_blocked`` stored, and it is the one field a
    completed goal never has: a blocked goal is waiting on a person, and this
    is the only thing that person gets to read about why.

    There is no ``goal_id`` in ``.text``, unlike TaskResult's ``task_id``. A
    task id is a handle the model passes to three other calls; a goal id is a
    stale-write guard nobody types.
    """

    status: str
    objective: str = ""
    reason: str = ""
    changed: bool = True
    turns_used: int = 0
    tokens_used: int = 0
    token_budget: int | None = None
    time_used_seconds: int = 0

    # A goal is orchestration of the session itself, which is what "task"
    # files the subagent calls under, and ACP has no kind for either.
    result_kind = "goal"

    def acp_payload(self) -> dict:
        # The objective is the subject because it is the only part a person
        # scanning a transcript can recognize; the status is already in the
        # title the drain builds from the tool name.
        return {"content": "text", "text": self.text, "subject": self.subject}

    @property
    def subject(self) -> str:
        return self.objective[:60] + ("…" if len(self.objective) > 60 else "")

    @property
    def text(self) -> str:
        head = f"goal {self.status}"
        if not self.changed:
            head += ", and it already was — this call changed nothing"
        lines = [f'{head}: "{self.subject}"']
        if self.reason:
            lines.append(f"why: {self.reason}")
        tokens = f"{self.tokens_used:,}"
        if self.token_budget is not None:
            tokens += f" of {self.token_budget:,}"
        lines.append(
            f"{self.turns_used} turns, {tokens} tokens,"
            f" {self.time_used_seconds // 60}m{self.time_used_seconds % 60:02d}s."
        )
        # The consequence, which is the whole reason the row exists. Stated
        # for the status the row actually has, because a write that lost the
        # race against a new goal leaves an ACTIVE one behind and promising
        # it would stop is the one thing this must not say.
        lines.append(
            "The goal is still active, so this session keeps being continued."
            if self.status == "active"
            else "This session will not be continued automatically."
        )
        return "\n".join(lines)


class GoalError(ToolError):
    """A goal could not be ended.

    The refusals land here too, and they state the rule rather than the
    exception: reaching for ``goal_done`` in a session that has no goal is not
    a crash, it is a model looking for an exit that was never armed, and
    ``goal_blocked`` with no reason is not a mistake to report but a thing to
    ask again for — the reason is the only part of a blocked goal anybody
    reads.
    """


