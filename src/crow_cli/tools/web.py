"""web — search and fetch: the web, Python-shaped.

Modes:
- ``search`` — ONE query to SearXNG -> structured hits (url, title, content,
  score, engines) plus the answers, infoboxes, suggestions, corrections and
  DOWN ENGINES SearXNG also returns and the MCP tool discarded.
- ``fetch``  — ONE URL -> the whole page: ``.markdown`` (readability +
  markdownify) and ``.html`` (raw), with ``.text`` a windowed rendering.

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
``node`` — measurably better than its pure-Python mode (no nav chrome, no raw
``<p>`` surviving into the markdown) at ~0.8s instead of ~0.1s. Availability
is decided HERE, with shutil.which and a directory stat, rather than by
readabilipy's own ``have_node()``: that function runs ``npm install`` when its
node_modules is missing, and npm install does a PROCESS-WIDE chdir — a network
install and a cwd race, triggered lazily by a fetch, in a kernel where other
cells resolve relative paths. Without node, extraction falls back to pure
Python and ``.extracted`` still tells the truth about what ran.

SearXNG at $SEARXNG_URL (default http://localhost:2946). Down is an ERROR
naming the URL, never an empty result — "no results" is exactly how a broken
backend hides, and web search is not optional equipment.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

from httpx import AsyncClient, HTTPError

from .register import subtool
from .results import (
    PageResult,
    WebError,
    WebHit,
    WebInfobox,
    WebSearchResult,
)

_MODES = ("search", "fetch")

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

# Tri-state: None until the first fetch decides, then a bool for the kernel's
# lifetime. node does not come and go mid-session, and the check is a
# which() plus a stat.
_readability: bool | None = None


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


@subtool(tool="web")
async def web(
    mode: str,
    target: str | None = None,
    limit: int | None = None,
    user_agent: str | None = None,
):
    """Search the web, or fetch one page from it.

    Args:
        mode: "search" or "fetch".
        target: search — the query. fetch — the URL, scheme included
            ("example.com" alone is an error, not a guess).
        limit: search only — hits to keep (default 10). SearXNG returns
            dozens; ``.total`` says how many and ``.truncated`` whether the
            limit cut it.
        user_agent: fetch only — default "CrowAgent/1.0". Some sites block
            obvious bots, and some block everything that is not a browser;
            for those, web(mode="run") is the answer.

    Returns:
        search -> WebSearchResult (.hits of WebHit(url, title, content,
        score, engines, published), .urls, .answers, .infoboxes,
        .suggestions, .corrections, .unresponsive, .total, .truncated,
        .text rendered); fetch -> PageResult (.markdown the whole
        extraction, .html the whole body, .title, .url final after
        redirects, .status, .content_type, .extracted, .chars, .text
        windowed).

    Raises:
        WebError: unknown mode, missing or blank target, limit= or user_agent=
            on the wrong mode, negative limit, SearXNG unreachable or non-200
            or not JSON, DNS/TLS/timeout/missing-scheme on fetch, HTTP >= 400,
            a non-text content type (a PDF — the message says how to
            download it instead), a body over 10MB.

    Note:
        The model sees only what the cell PRINTS — ``print(r.text)`` after
        either mode. ``.markdown`` is the WHOLE page: slice it
        (``r.markdown[5000:9000]``) rather than paginating, and gather
        several searches (``asyncio.gather(*[web("search", q) for q in qs])``)
        rather than passing a list. Print ``.unresponsive`` too — engines
        down looks exactly like a bad query if you don't. The client gets
        its own view regardless: a search-kind call titled with the query
        and a fetch-kind call titled with the URL, each carrying the
        rendered text.
    """
    if mode not in _MODES:
        raise WebError(
            f"unknown web mode {mode!r} — expected one of: {', '.join(_MODES)}"
        )
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
    # Cross-cutting, so neither mode can quietly ignore an argument the
    # caller cared about.
    if limit is not None and mode != "search":
        raise WebError(
            f"limit= is for mode='search', not {mode!r} — a page is not"
            " paginated, slice r.markdown"
        )
    if user_agent is not None and mode != "fetch":
        raise WebError(f"user_agent= is for mode='fetch', not {mode!r}")

    if mode == "search":
        return await _search(target, _cap(limit))
    return await _fetch(target, user_agent or _USER_AGENT)
