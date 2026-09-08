"""web — search, fetch, run: the web, Python-shaped.

Modes:
- ``search`` — ONE query to SearXNG -> structured hits (url, title, content,
  score, engines) plus the answers, infoboxes, suggestions, corrections and
  DOWN ENGINES SearXNG also returns and the MCP tool discarded.
- ``fetch``  — ONE URL -> the whole page: ``.markdown`` (readability +
  markdownify) and ``.html`` (raw), with ``.text`` a windowed rendering.
- ``run``    — ONE URL in a real headless chromium -> the same PageResult,
  but ``.rendered`` and ``.html`` is the DOM after the page's JavaScript ran.
  Plus ``.screenshot`` (a VisionResult in the ImageStore, so a vision model
  SEES the page) and ``.page`` (the live playwright Page).
- ``close``  — shut the kernel's browser down.

One query per call and no pagination, for the same reason: an MCP tool has to
return ONE STRING, so web_search took a list of queries and looped over them
SEQUENTIALLY, and web_fetch sliced pages with start_index/max_length. In a
kernel the model writes ``asyncio.gather(*[web("search", q) for q in qs])``
for real parallelism and ``r.markdown[5000:9000]`` for the next page.

Bodies are STREAMED against a cap, so a 2GB download is refused at 10MB
instead of after it has landed in RAM — the lesson ripgrep taught fs. A
non-text content type raises rather than decoding a PDF into mojibake, and
the error says what to do instead: httpx is ambient, so two lines of cell
code download the bytes with nothing lost.

Extraction prefers Mozilla's Readability.js, which readabilipy drives through
``node`` — measurably better than its pure-Python mode at ~0.8s instead of
~0.1s. Availability is decided HERE, with shutil.which and a directory stat,
rather than by readabilipy's own ``have_node()``: that function runs ``npm
install`` when its node_modules is missing, and npm install does a
PROCESS-WIDE chdir — a network install and a cwd race, triggered lazily by a
fetch, in a kernel where other cells resolve relative paths. Without node,
extraction falls back to pure Python; crow strips the ``<title>`` that mode
leaks into content (markdownify would pass it through as raw HTML) so both
paths produce clean markdown, and ``.extracted`` still tells the truth about
what ran.

The browser is ONE chromium and ONE context for the kernel's lifetime,
started on the first ``run`` — a launch per cell costs ~0.3s and leaks
processes, and the context is what carries cookies between runs — but each
``run`` gets a FRESH page and closes the previous one, so a stale ``.page``
fails loudly instead of silently pointing at the latest navigation.
playwright is imported at call time (the wheel is 47MB because it bundles
the Node driver — playwright-python is JSON-RPC to a node subprocess, not an
FFI binding) and the async API only, because the sync one greenlet-switches
into its own event loop and a cell already runs inside ipykernel's.

SearXNG at $SEARXNG_URL (default http://localhost:2946). Down is an ERROR
naming the URL, never an empty result — "no results" is exactly how a broken
backend hides, and web search is not optional equipment.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from contextlib import suppress
from pathlib import Path

from httpx import AsyncClient, HTTPError

from .register import image_store, subtool
from .results import (
    BrowserClosed,
    PageResult,
    VisionResult,
    WebError,
    WebHit,
    WebInfobox,
    WebSearchResult,
)

_MODES = ("search", "fetch", "run", "close")

_SEARXNG_URL = "http://localhost:2946"
_DEFAULT_LIMIT = 10
_TIMEOUT = 30.0
_MAX_PAGE_BYTES = 10 * 1024 * 1024
_USER_AGENT = "CrowAgent/1.0"
_HTML_TYPES = ("text/html", "application/xhtml+xml")
_TEXT_TYPES = (
    "application/json",
    "application/xml",
    "application/javascript",
    "application/yaml",
    "application/x-yaml",
    "application/x-sh",
    "application/toml",
)

# playwright's own vocabulary for "when is the page done".
_WAIT_UNTIL = ("load", "domcontentloaded", "networkidle", "commit")
_BROWSER_TIMEOUT = 30.0  # seconds; playwright thinks in milliseconds

# Tri-state: None until the first fetch decides, then a bool for the kernel's
# lifetime. node does not come and go mid-session, and the check is a
# which() plus a stat.
_readability: bool | None = None

# Browser handles live in a mutable CELL, not in module globals:
# importlib.reload re-executes this source in the EXISTING module dict, so a
# module-level `_page = None` would drop the handle on every reload() and
# orphan a running chromium — and reload() is both how PRELUDE starts a
# kernel and how the model iterates on tools mid-session. setdefault keeps
# the one container across re-executions, and playwright itself is never
# reloaded (reload() only touches crow_cli.tools.*), so the objects inside it
# stay live.
_state: dict = globals().setdefault("_state", {})
_state.setdefault("lock", asyncio.Lock())


def _use_readability() -> bool:
    """Whether Readability.js can run — decided without asking readabilipy.

    Its own ``have_node()`` spawns ``node -v`` on every call and, when the
    bundled node_modules is missing, runs ``npm install`` — which chdirs the
    whole process. Neither belongs inside a fetch.
    """
    global _readability
    if _readability is None:
        import importlib.util

        spec = importlib.util.find_spec("readabilipy")
        bundled = Path(spec.origin).parent / "javascript" if spec else None
        _readability = (
            shutil.which("node") is not None
            and bundled is not None
            and (bundled / "node_modules").is_dir()
        )
    return _readability


def _mime(content_type: str) -> str:
    return content_type.split(";")[0].strip().lower()


def _is_texty(content_type: str) -> bool:
    """Whether the body is worth decoding as text at all."""
    ct = _mime(content_type)
    if not ct:
        return True  # undeclared: assume text, and sniff for HTML below
    return (
        ct.startswith("text/")
        or ct.endswith("+json")
        or ct.endswith("+xml")
        or ct in _TEXT_TYPES
    )


def _is_html(content_type: str, head: str) -> bool:
    """A DECLARED content type is believed; only an undeclared body is
    sniffed. The MCP tool treated a missing header as HTML, so a JSON API
    that omitted it was fed to readability and came back mangled."""
    ct = _mime(content_type)
    if ct in _HTML_TYPES:
        return True
    if ct:
        return False
    return "<html" in head[:512].lower()


def _cap(limit: int | None) -> int:
    if limit is None:
        return _DEFAULT_LIMIT
    if limit < 0:
        raise WebError(f"limit must be >= 0, got {limit}")
    return int(limit)


def _seconds(timeout: float | None) -> float:
    """Seconds here, milliseconds on the wire: playwright thinks in ms, and
    an argument named timeout= that silently means something different from
    every other duration in this package is a bug factory."""
    if timeout is None:
        return _BROWSER_TIMEOUT
    if timeout <= 0:
        raise WebError(f"timeout must be > 0 seconds, got {timeout}")
    return float(timeout)


def _first_url(infobox: dict) -> str:
    for link in infobox.get("urls") or []:
        if isinstance(link, dict) and link.get("url"):
            return str(link["url"])
    return ""


def _engine_down(entry) -> str:
    """SearXNG reports ["duckduckgo", "CAPTCHA"]; older builds report a bare
    engine name. The reason is the useful half — CAPTCHA means retry later,
    an empty result means refine the query."""
    if isinstance(entry, (list, tuple)) and entry:
        reason = str(entry[1]) if len(entry) > 1 and entry[1] else ""
        return f"{entry[0]} ({reason})" if reason else str(entry[0])
    return str(entry)


_ANSWER_BOILERPLATE = ("template", "parsed_url", "engine", "score", "url")


def _answer(entry) -> str:
    """The text of one SearXNG answer.

    ``Answer`` (searx/result_types/answer.py) carries it in ``answer``, and
    that is the shape a plugin returns — ``{"url": null, "engine": "plugin:
    time_zone", "parsed_url": null, "template": "answer/legacy.html",
    "answer": "Sep 6, 2026, 8:24:44 AM"}``. str() of that dict buries the one
    field worth reading under four that are rendering boilerplate. Other
    answer types (Translations, WeatherAnswer) have no ``answer`` key at all,
    so those come through as JSON minus the boilerplate: still structured,
    still readable, nothing invented.
    """
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        text = entry.get("answer")
        if text:
            return str(text)
        rest = {
            k: v
            for k, v in entry.items()
            if k not in _ANSWER_BOILERPLATE and v not in (None, "", [], {})
        }
        return json.dumps(rest, ensure_ascii=False, default=str)
    return str(entry)



async def _search(query: str, limit: int) -> WebSearchResult:
    base = os.getenv("SEARXNG_URL", _SEARXNG_URL)
    try:
        # `async with`, unlike the MCP tool, which built an AsyncClient per
        # call and never closed it — one leaked connection pool per search.
        async with AsyncClient(base_url=base, timeout=_TIMEOUT) as client:
            response = await client.get(
                "/search", params={"q": query, "format": "json"}
            )
            response.raise_for_status()
    except HTTPError as e:
        raise WebError(f"SearXNG at {base} did not answer {query!r}: {e}") from None
    try:
        data = response.json()
    except ValueError as e:
        raise WebError(
            f"SearXNG at {base} answered {query!r} with something that is not"
            f" JSON: {e}"
        ) from None

    raw = data.get("results") or []
    return WebSearchResult(
        query=query,
        # A slice, not `if i == limit - 1: break` — which returned EVERYTHING
        # when limit was 0.
        hits=[
            WebHit(
                url=str(h.get("url") or ""),
                title=str(h.get("title") or ""),
                content=str(h.get("content") or ""),
                score=float(h.get("score") or 0.0),
                engines=[str(e) for e in (h.get("engines") or [])],
                published=str(h.get("publishedDate") or h.get("pubdate") or ""),
            )
            for h in raw[:limit]
        ],
        total=len(raw),
        answers=[_answer(a) for a in (data.get("answers") or [])],
        infoboxes=[
            WebInfobox(
                topic=str(ib.get("infobox") or ib.get("title") or ""),
                url=str(ib.get("id") or _first_url(ib)),
                content=str(ib.get("content") or ""),
            )
            for ib in (data.get("infoboxes") or [])
        ],
        suggestions=[str(s) for s in (data.get("suggestions") or [])],
        corrections=[str(c) for c in (data.get("corrections") or [])],
        unresponsive=[_engine_down(e) for e in (data.get("unresponsive_engines") or [])],
    )


def _extract(body: str, content_type: str) -> tuple[str, str, bool]:
    """(markdown, title, extracted). Blocking — bs4, and when node is
    available two subprocesses and two temp files — so it runs in a thread.

    The imports are call-time on purpose: PRELUDE reloads every tool module
    on kernel start, and lxml plus bs4 are hundreds of milliseconds a kernel
    that never browses should not pay. Same reasoning as ast-grep in fs.
    """
    if not _is_html(content_type, body):
        return body.strip(), "", False

    import markdownify
    from bs4 import BeautifulSoup
    import readabilipy.simple_json

    try:
        parsed = readabilipy.simple_json.simple_json_from_html_string(
            body, use_readability=_use_readability()
        )
    except Exception:
        # A page readability chokes on is not a failed fetch: the raw body is
        # still the best answer available, and .extracted says what happened.
        return body.strip(), "", False
    title = str(parsed.get("title") or "")
    article = parsed.get("content") or ""
    if not article:
        return body.strip(), title, False
    # readabilipy's pure-Python mode (no node) leaves the <title> element in
    # content — markdownify then passes it through as raw HTML, so a page's
    # title text rode into the markdown wrapped in literal <p> tags. The title
    # is already reported separately; it does not belong in the body.
    soup = BeautifulSoup(article, "html.parser")
    for junk in soup.find_all("title"):
        junk.decompose()
    article = str(soup)
    if not article.strip():
        return body.strip(), title, False
    markdown = markdownify.markdownify(article, heading_style=markdownify.ATX)
    return markdown.strip(), title, True


async def _fetch(url: str, user_agent: str) -> PageResult:
    try:
        async with AsyncClient(follow_redirects=True, timeout=_TIMEOUT) as client:
            async with client.stream(
                "GET", url, headers={"User-Agent": user_agent}
            ) as response:
                status = response.status_code
                content_type = response.headers.get("content-type", "")
                final = str(response.url)
                if status >= 400:
                    raise WebError(
                        f"{status} {response.reason_phrase} for {final}"
                    )
                if not _is_texty(content_type):
                    raise WebError(
                        f"{final} is {_mime(content_type) or 'an undeclared type'},"
                        " not text — web('fetch') reads pages. httpx is ambient:"
                        " async with httpx.AsyncClient() as c:"
                        " Path('f.pdf').write_bytes((await c.get(url)).content)"
                    )
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > _MAX_PAGE_BYTES:
                        raise WebError(
                            f"{final} is over"
                            f" {_MAX_PAGE_BYTES // (1024 * 1024)}MB — refusing to"
                            " read the rest of it"
                        )
                    chunks.append(chunk)
                encoding = response.encoding or "utf-8"
    except WebError:
        raise
    except HTTPError as e:
        raise WebError(f"fetching {url} failed: {e}") from None

    body = b"".join(chunks).decode(encoding, errors="replace")
    markdown, title, extracted = await asyncio.to_thread(_extract, body, content_type)
    return PageResult(
        url=final,
        title=title,
        status=status,
        content_type=content_type,
        markdown=markdown,
        html=body,
        extracted=extracted,
    )


async def _shutdown() -> bool:
    """Tear the browser down; report whether one was running.

    Best effort by necessity: a browser that crashed raises when you close
    it, and close() still has to get rid of the driver subprocess — so every
    layer is attempted, page then context then browser then driver, and a
    failure at one layer does not strand the next.
    """
    was_running = _state.get("browser") is not None
    for key, method in (
        ("page", "close"),
        ("context", "close"),
        ("browser", "close"),
        ("pw", "stop"),
    ):
        obj = _state.get(key)
        _state[key] = None
        if obj is None:
            continue
        with suppress(Exception):
            await getattr(obj, method)()
    return was_running


async def _browser_page():
    """A fresh page in the kernel's one context, closing the previous page.

    ONE browser and ONE context for the kernel's lifetime — a launch per cell
    costs ~0.3s and leaks processes, and the context is what makes cookies
    and localStorage survive from one run to the next. But a NEW page per
    run, with the previous one closed, because a shared page is a silent
    trap: verified live, ``r.page`` from an earlier cell was pointing at
    whatever the LATEST run had navigated to, so a selector that happened to
    exist on both pages clicked the wrong thing and one that did not burned
    a 30s timeout. Closing it makes a stale ``.page`` fail loudly with
    playwright's own "Page has been closed".
    """
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import async_playwright

    try:
        if _state.get("browser") is None:
            if _state.get("pw") is None:
                _state["pw"] = await async_playwright().start()
            _state["browser"] = await _state["pw"].chromium.launch()
        if _state.get("context") is None:
            _state["context"] = await _state["browser"].new_context()
        old = _state.get("page")
        if old is not None and not old.is_closed():
            with suppress(Exception):
                await old.close()
        _state["page"] = await _state["context"].new_page()
    except PlaywrightError as e:
        # A missing browser binary surfaces here with playwright's own
        # "please run playwright install" text, which is kept verbatim: it
        # is the instruction the reader needs.
        await _shutdown()
        raise WebError(f"cannot start a browser: {e}") from None
    return _state["page"]


def _store_shot(png: bytes, source: str) -> VisionResult:
    """A screenshot into the ImageStore, via the same path vision takes.

    Capped for the same reason: the viewport is 1280x720 by default but
    ``r.page.set_viewport_size`` is ambient, and a 3000px shot is bytes no
    vision model wants. Going through vision's own helpers means the key is
    content-addressed identically, so a screenshot dedupes against a
    webcam capture or a file read of the same image.
    """
    import cv2
    import numpy as np

    from .vision import _cap_resolution, _encode, _store

    frame = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise WebError("the browser returned a screenshot cv2 cannot decode")
    frame = _cap_resolution(frame)
    height, width = frame.shape[:2]
    return _store(_encode(frame, "image/png"), "image/png", width, height, source)


async def _run(
    url: str, wait_until: str, timeout: float, screenshot: bool
) -> PageResult:
    from playwright.async_api import Error as PlaywrightError

    if screenshot and image_store() is None:
        # Before launching anything: a browser with nowhere to put the
        # artifact is a wasted 0.3s and a confusing failure.
        raise WebError(
            "no ImageStore configured for this kernel (begin_cell got no"
            " images_dir), so a screenshot has nowhere to go — pass"
            " screenshot=False, or run under the execute server, which"
            " injects one"
        )

    async with _state["lock"]:
        # One page, so concurrent runs are serialized rather than
        # interleaved: two gotos racing on one page would leave both results
        # describing whichever navigation landed last. gather() over run
        # still works, it just goes one at a time — and a model that wants
        # real tabs opens them itself (r.page.context.new_page()).
        page = await _browser_page()
        try:
            response = await page.goto(
                url, wait_until=wait_until, timeout=timeout * 1000
            )
            status = response.status if response is not None else 0
            # A PageResult is a page that was RETRIEVED. fetch raises on
            # >= 400, so run raises too, or .status would mean two different
            # things in two modes of one tool — and a 404 body read as
            # content is a worse mistake than a caught error. Error bodies
            # stay reachable the ambient way: httpx, or playwright itself.
            if status >= 400:
                raise WebError(f"{status} {response.status_text} for {page.url}")
            content_type = (
                response.headers.get("content-type", "")
                if response is not None
                else ""
            )
            final = page.url
            html = await page.content()
            title = await page.title()
            png = await page.screenshot() if screenshot else None
        except WebError:
            raise
        except PlaywrightError as e:
            raise WebError(f"the browser failed on {url}: {e}") from None
        shot = (
            await asyncio.to_thread(_store_shot, png, url) if png is not None else None
        )

    # Outside the lock: extraction is the slow half (two subprocesses when
    # node runs) and it no longer touches the browser. The DOM is HTML
    # whatever the server claimed it was — that is the whole point of
    # rendering it — so the declared content type is not consulted.
    markdown, parsed_title, extracted = await asyncio.to_thread(
        _extract, html, "text/html"
    )
    return PageResult(
        url=final,
        title=title or parsed_title,
        status=status,
        content_type=content_type,
        markdown=markdown,
        html=html,
        extracted=extracted,
        rendered=True,
        screenshot=shot,
        page=page,
    )


async def _close() -> BrowserClosed:
    async with _state["lock"]:
        return BrowserClosed(was_running=await _shutdown())


@subtool(tool="web")
async def web(
    mode: str,
    target: str | None = None,
    limit: int | None = None,
    user_agent: str | None = None,
    wait_until: str | None = None,
    timeout: float | None = None,
    screenshot: bool | None = None,
):
    """Search the web, fetch a page from it, or render one in a browser.

    Args:
        mode: "search", "fetch", "run" or "close".
        target: search — the query. fetch/run — the URL, scheme included
            ("example.com" alone is an error, not a guess). close takes none.
        limit: search only — hits to keep (default 10). SearXNG returns
            dozens; ``.total`` says how many and ``.truncated`` whether the
            limit cut it.
        user_agent: fetch only — default "CrowAgent/1.0". Some sites block
            obvious bots, and some block everything that is not a browser;
            for those, mode="run" is the answer (a browser sends its own, and
            ``r.page.context`` is ambient if you need to change it).
        wait_until: run only — when the page counts as done: "load"
            (default), "domcontentloaded", "networkidle" (a SPA that renders
            after the load event), "commit". playwright's own vocabulary.
        timeout: run only — seconds to allow the navigation (default 30).
            Seconds here, not playwright's milliseconds.
        screenshot: run only — default True: a PNG of the viewport into the
            ImageStore, riding the row as an image block so a vision model
            SEES the page. Pass False in a loop over URLs, where one image
            per page is more context than the pages are worth.

    Returns:
        search -> WebSearchResult (.hits of WebHit(url, title, content,
        score, engines, published), .urls, .answers, .infoboxes,
        .suggestions, .corrections, .unresponsive, .total, .truncated);
        fetch/run -> PageResult (.markdown the whole extraction, .html the
        whole body — the RENDERED DOM for run — .title, .url final after
        redirects, .status, .content_type, .extracted, .rendered, .chars,
        .text windowed; run also .screenshot, a VisionResult, and .page, the
        live playwright Page); close -> BrowserClosed (.was_running).

    Raises:
        WebError: unknown mode, missing or blank target, an argument on the
            wrong mode, negative limit, non-positive timeout, unknown
            wait_until, SearXNG unreachable or non-200 or not JSON,
            DNS/TLS/timeout/missing-scheme on fetch, HTTP >= 400, a non-text
            content type (a PDF — the message says how to download it
            instead), a body over 10MB, a browser that cannot start (no
            chromium binary), a page that will not load, a screenshot with no
            ImageStore to put it in.

    Note:
        The model sees only what the cell PRINTS — ``print(r.text)`` after
        any mode. ``.markdown`` is the WHOLE page: slice it
        (``r.markdown[5000:9000]``) rather than paginating, and gather
        several searches (``asyncio.gather(*[web("search", q) for q in qs])``)
        rather than passing a list. Print ``.unresponsive`` too — engines
        down looks exactly like a bad query if you don't.

        fetch or run? fetch is httpx: fast, no browser, right for anything
        server-rendered. run is chromium: slower, and the only way to get
        what JavaScript builds or to be seen as a browser rather than a bot.
        ``.rendered`` on the result says which one happened.

        The browser is one chromium and one context for the kernel's
        lifetime, and ``.page`` is live in the next cell — click, type,
        wait_for_selector, then read the settled DOM with ``await
        r.page.content()``. The NEXT ``run`` closes it and opens a fresh
        page, so finish with a page before navigating again (cookies and
        storage survive; the context is the same). Everything playwright
        does is ambient; this tool starts the browser, navigates, captures
        and gets out of the way. ``web("close")`` shuts it all down.

        The client gets its own view regardless: one sibling call per row,
        titled with the query or the URL, carrying the rendered text and any
        screenshot.
    """
    if mode not in _MODES:
        raise WebError(
            f"unknown web mode {mode!r} — expected one of: {', '.join(_MODES)}"
        )
    if mode == "close":
        if target is not None:
            raise WebError(
                "mode='close' takes no target= — it closes the kernel's browser"
            )
        return await _close()
    # Strip before the check: a blank query is a caller bug, and SearXNG
    # answers one with a plugin's clock reading instead of an error —
    # verified live, q="  " comes back with an answers=[{"engine":
    # "plugin: time_zone", "answer": "Sep 6, 2026, 8:24:44 AM"}] and no hits.
    # A nonsense success hides a mistake; an error names it.
    target = (target or "").strip()
    if not target:
        raise WebError(
            f"mode={mode!r} requires target="
            + (" a query to search for" if mode == "search" else " a URL")
        )
    # Cross-cutting, so no mode can quietly ignore an argument the caller
    # cared about.
    if limit is not None and mode != "search":
        raise WebError(
            f"limit= is for mode='search', not {mode!r} — a page is not"
            " paginated, slice r.markdown"
        )
    if user_agent is not None and mode != "fetch":
        raise WebError(f"user_agent= is for mode='fetch', not {mode!r}")
    for name, value in (
        ("wait_until", wait_until),
        ("timeout", timeout),
        ("screenshot", screenshot),
    ):
        if value is not None and mode != "run":
            raise WebError(f"{name}= is for mode='run', not {mode!r}")

    if mode == "search":
        return await _search(target, _cap(limit))
    if mode == "fetch":
        return await _fetch(target, user_agent or _USER_AGENT)
    wait = wait_until or "load"
    if wait not in _WAIT_UNTIL:
        raise WebError(
            f"unknown wait_until {wait!r} — expected one of:"
            f" {', '.join(_WAIT_UNTIL)}"
        )
    return await _run(
        target, wait, _seconds(timeout), True if screenshot is None else screenshot
    )
