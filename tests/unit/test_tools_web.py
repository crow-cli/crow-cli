"""web — search/fetch, Python-shaped: real result objects, WebError raised on
failure, register + write-through like every subtool.

No mocks and no internet. A local ThreadingHTTPServer stands in for BOTH the
web (fetch routes) and SearXNG (a /search route serving canned JSON in the
exact shape the real one returns, captured live) — so the real httpx client,
the real streaming cap, the real readability/markdownify extraction and the
real error paths all run, hermetically. SEARXNG_URL is read at call time, so
pointing it at the fixture is the whole trick.

Extraction assertions hold with OR without node: readabilipy's pure-Python
mode produces an article too, so `extracted` is True either way and only the
title's exact text differs. Nothing here may depend on node being installed.
"""

import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from crow_cli.tools import web
from crow_cli.tools.register import begin_cell, clear, pending
from crow_cli.tools.results import (
    BrowserClosed,
    PageResult,
    VisionResult,
    WebError,
    WebSearchResult,
)

# from-import of internals IS safe; `import crow_cli.tools.web as m` is not —
# the facade resolves that name to the FUNCTION.
from crow_cli.tools.web import _answer, _engine_down, _is_html, _is_texty

MOD = sys.modules["crow_cli.tools.web"]

PAGE = (
    "<html><head><title>Tiny Page</title></head><body>"
    "<nav><a href='/'>Home</a><a href='/x'>About</a></nav>"
    "<article><h1>The Heading</h1><p>Body one.</p><p>Body two.</p></article>"
    "</body></html>"
)
HUGE = "line of text\n" * 4000  # 52k chars — past the 5k print window
OVER_CAP = b"x" * (11 * 1024 * 1024)
# The page that does not exist until JavaScript builds it — the whole reason
# mode="run" exists. fetch sees "before", run sees "built by JS".
JS_PAGE = (
    "<html><head><title>Static Title</title></head><body><div id='app'>"
    "before</div><script>document.title='Rendered Title';"
    "document.getElementById('app').textContent='built by JS';"
    "</script></body></html>"
)

# Captured live from SearXNG 2026.9: every top-level key it returns, of which
# the MCP tool kept exactly one (`results`).
FULL = {
    "query": "full",
    "results": [
        {
            "url": "https://a.example/1",
            "title": "First",
            "content": "Snippet one",
            "score": 3.5,
            "engines": ["bing", "naver"],
            "publishedDate": "2026-01-02T03:04:05",
        },
        {
            "url": "https://b.example/2",
            "title": "Second",
            "content": "Snippet two",
            "score": 1.0,
            "engines": ["bing"],
        },
        {"url": "https://c.example/3", "title": "Third", "score": 0.0},
    ],
    # A plugin answer, verbatim: four rendering fields around one worth
    # reading.
    "answers": [
        {
            "url": None,
            "engine": "plugin: time_zone",
            "parsed_url": None,
            "template": "answer/legacy.html",
            "answer": "Sep 6, 2026, 8:24:44\u202fAM",
        }
    ],
    "infoboxes": [
        {
            "infobox": "Albert Einstein",
            "id": "https://en.wikipedia.org/wiki/Albert_Einstein",
            "content": "German-born theoretical physicist.",
            "urls": [{"title": "Wikipedia", "url": "https://en.wikipedia.org/x"}],
        }
    ],
    "suggestions": ["related one", "related two"],
    "corrections": ["speling"],
    "unresponsive_engines": [["duckduckgo", "CAPTCHA"], "brave"],
}
# Answer types with no `answer` key exist (Translations, WeatherAnswer in
# searx/result_types/answer.py) — the payload minus boilerplate is the honest
# rendering, not str() of a dict and not an invented string.
ODD_ANSWER = {
    "engine": "plugin: deepl",
    "template": "answer/translations.html",
    "url": None,
    "parsed_url": None,
    "translations": [{"text": "foobar", "synonyms": ["foo", "bar"]}],
}
LEGACY = {
    "results": [{"url": "https://a.example/1", "title": "First", "content": "c"}],
    "answers": ["a plain string answer"],
    "infoboxes": [{"urls": [{"url": "https://entity.example"}], "content": "x"}],
    "unresponsive_engines": ["startpage"],
}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _send(self, code, body: bytes, ctype=None, extra=None):
        self.send_response(code)
        if ctype is not None:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parts = urlsplit(self.path)
        route = parts.path
        query = parse_qs(parts.query)
        if route == "/search":
            q = (query.get("q") or [""])[0]
            if q == "notjson":
                self._send(200, b"<html>not json</html>", "text/html")
            elif q == "empty":
                self._send(200, json.dumps({"results": [], "query": q}).encode(),
                           "application/json")
            elif q == "bare":
                self._send(200, b"{}", "application/json")
            elif q == "odd":
                self._send(200, json.dumps({"results": [], "answers": [ODD_ANSWER]}).encode(),
                           "application/json")
            elif q == "legacy":
                self._send(200, json.dumps(LEGACY).encode(), "application/json")
            else:
                self._send(200, json.dumps(FULL).encode(), "application/json")
        elif route == "/page.html":
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif route == "/html-noctype":
            self._send(200, PAGE.encode())
        elif route == "/json-noctype":
            self._send(200, b'{"a": 1, "b": [2, 3]}')
        elif route == "/api.json":
            self._send(200, b'{"ok": true}', "application/json")
        elif route == "/plain.txt":
            self._send(200, b"just text\nline two\n", "text/plain; charset=utf-8")
        elif route == "/huge.txt":
            self._send(200, HUGE.encode(), "text/plain")
        elif route == "/doc.pdf":
            self._send(200, b"%PDF-1.4 not text", "application/pdf")
        elif route == "/over-cap":
            self._send(200, OVER_CAP, "text/plain")
        elif route == "/missing":
            self._send(404, b"nope", "text/plain")
        elif route == "/redirect":
            self._send(302, b"", None, {"Location": "/page.html"})
        elif route == "/echo-ua":
            self._send(200, self.headers.get("User-Agent", "<none>").encode(),
                       "text/plain")
        elif route == "/slow":
            import time

            time.sleep(1.0)
            self._send(200, b"late", "text/plain")
        elif route == "/js":
            self._send(200, JS_PAGE.encode(), "text/html; charset=utf-8")
        elif route == "/hang":
            import time

            time.sleep(6.0)
            self._send(200, b"late", "text/html")
        else:
            self._send(404, b"unknown route", "text/plain")


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # The cap test hangs up mid-body and the timeout test hangs up mid-
        # sleep; both surface here as BrokenPipeError from the server side,
        # which is the client behaving correctly.
        pass


@pytest.fixture(scope="module")
def base():
    server = _Server(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def _clean(base, monkeypatch):
    """Every test talks to the fixture, never to a real SearXNG, and starts
    with an empty register and an undecided readability cache."""
    monkeypatch.setenv("SEARXNG_URL", base)
    monkeypatch.setattr(MOD, "_readability", None)
    clear()
    yield
    clear()


@pytest.fixture(scope="module")
def chromium():
    """A real chromium, or skip. run is the one mode that cannot be exercised
    without a browser, and a 170MB download is not a test dependency — the
    binary lives in the shared ~/.cache/ms-playwright when playwright install
    has put it there."""
    from playwright.async_api import async_playwright

    async def _probe():
        pw = await async_playwright().start()
        try:
            browser = await pw.chromium.launch()
            await browser.close()
        finally:
            await pw.stop()

    try:
        asyncio.run(_probe())
    except Exception as e:
        pytest.skip(f"no chromium for playwright: {type(e).__name__}: {e}")
    return True


@pytest.fixture(autouse=True)
async def _browser_down():
    """No test may leave a browser behind for the next one: the singleton is
    process-wide, and a leaked chromium is 200MB of someone else's machine."""
    yield
    await MOD._shutdown()


# --- search ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_parses_every_part_of_the_response():
    """The five keys the MCP tool discarded are the point of the port:
    `unresponsive` is what tells a degraded backend from a bad query."""
    r = await web("search", "anything")
    assert isinstance(r, WebSearchResult) and r
    assert r.query == "anything"
    assert r.total == 3 and len(r.hits) == 3 and not r.truncated
    hit = r.hits[0]
    assert (hit.url, hit.title, hit.content) == (
        "https://a.example/1",
        "First",
        "Snippet one",
    )
    assert hit.score == 3.5 and hit.engines == ["bing", "naver"]
    assert hit.published == "2026-01-02T03:04:05"
    assert r.urls == ["https://a.example/1", "https://b.example/2", "https://c.example/3"]
    assert r.suggestions == ["related one", "related two"]
    assert r.corrections == ["speling"]
    assert r.unresponsive == ["duckduckgo (CAPTCHA)", "brave"]
    assert r.infoboxes[0].topic == "Albert Einstein"
    assert r.infoboxes[0].url == "https://en.wikipedia.org/wiki/Albert_Einstein"
    assert r.infoboxes[0].content == "German-born theoretical physicist."


@pytest.mark.asyncio
async def test_search_answer_is_the_text_not_the_dict():
    """A plugin answer arrives as {url, engine, parsed_url, template, answer}.
    str() of that dict buries the one field worth reading under four that are
    rendering boilerplate — and answers are the most valuable part of a
    search response, a direct answer beating ten links."""
    r = await web("search", "time")
    assert r.answers == ["Sep 6, 2026, 8:24:44\u202fAM"]
    assert r.text.splitlines()[1] == "ANSWER: Sep 6, 2026, 8:24:44\u202fAM"


@pytest.mark.asyncio
async def test_search_answer_without_an_answer_key_stays_structured():
    """Translations and WeatherAnswer have no `answer` field at all. JSON
    minus the boilerplate is honest; str() of a dict is not."""
    r = await web("search", "odd")
    assert r.answers == [json.dumps({"translations": ODD_ANSWER["translations"]})]
    assert "template" not in r.answers[0]


@pytest.mark.asyncio
async def test_search_legacy_shapes():
    """Older builds: answers as bare strings, unresponsive as bare engine
    names, an infobox with no `id` (its url comes from urls[])."""
    r = await web("search", "legacy")
    assert r.answers == ["a plain string answer"]
    assert r.unresponsive == ["startpage"]
    assert r.infoboxes[0].topic == ""
    assert r.infoboxes[0].url == "https://entity.example"


@pytest.mark.asyncio
async def test_search_missing_keys_are_empty_not_errors():
    r = await web("search", "bare")
    assert (r.hits, r.total, r.answers, r.infoboxes) == ([], 0, [], [])
    assert (r.suggestions, r.corrections, r.unresponsive) == ([], [], [])
    assert r.text == "bare — 0 of 0 hits"
    assert r  # an empty result is a successful search, not a failure


@pytest.mark.asyncio
async def test_search_limit_slices_and_reports():
    r = await web("search", "anything", limit=2)
    assert len(r.hits) == 2 and r.total == 3 and r.truncated
    assert r.urls == ["https://a.example/1", "https://b.example/2"]


@pytest.mark.asyncio
async def test_search_limit_zero_is_empty_not_everything():
    """The MCP tool broke out of its loop with `if i == limit - 1`, so
    limit=0 never broke and returned the whole result set."""
    r = await web("search", "anything", limit=0)
    assert r.hits == [] and r.total == 3 and r.truncated
    assert r.text.startswith("anything — 0 of 3 hits")


@pytest.mark.asyncio
async def test_search_down_backend_is_an_error_naming_the_url(monkeypatch):
    """"No results" is exactly how a broken backend hides, and web search is
    not optional equipment — so an unreachable SearXNG raises."""
    monkeypatch.setenv("SEARXNG_URL", "http://127.0.0.1:1")
    with pytest.raises(WebError, match=r"SearXNG at http://127.0.0.1:1"):
        await web("search", "anything")


@pytest.mark.asyncio
async def test_search_non_json_is_an_error():
    with pytest.raises(WebError, match="not JSON"):
        await web("search", "notjson")


@pytest.mark.asyncio
async def test_search_http_error_is_an_error(monkeypatch, base):
    """A non-200 from SearXNG must not come back as an empty result set."""
    monkeypatch.setenv("SEARXNG_URL", f"{base}/missing")
    with pytest.raises(WebError, match=r"did not answer 'anything'.*404 Not Found"):
        await web("search", "anything")


@pytest.mark.asyncio
async def test_search_does_not_leak_a_client(monkeypatch):
    """The MCP tool built an AsyncClient per call and never closed it — one
    leaked connection pool per search. A tracking subclass over the REAL
    client (not a mock: the HTTP still happens) is the only way to observe
    closure from outside."""
    live: list[httpx.AsyncClient] = []

    class Tracked(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            live.append(self)

    monkeypatch.setattr(MOD, "AsyncClient", Tracked)
    await asyncio.gather(*[web("search", "anything") for _ in range(4)])
    assert len(live) == 4
    assert all(c.is_closed for c in live)


# --- fetch -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_html_is_extracted(base):
    p = await web("fetch", f"{base}/page.html")
    assert isinstance(p, PageResult) and p
    assert p.status == 200 and p.result_kind == "web"
    assert p.content_type == "text/html; charset=utf-8"
    assert p.extracted and "Tiny" in p.title
    assert "Body one." in p.markdown and "<p>" not in p.markdown
    assert p.html == PAGE  # the raw body is kept whole, alongside
    assert p.chars == len(p.markdown)
    assert p.url == f"{base}/page.html"


@pytest.mark.asyncio
async def test_fetch_undeclared_html_is_sniffed(base):
    p = await web("fetch", f"{base}/html-noctype")
    assert p.content_type == "" and p.extracted and "Body one." in p.markdown


@pytest.mark.asyncio
async def test_fetch_undeclared_json_is_not_fed_to_readability(base):
    """The MCP tool's is_html treated a MISSING content type as HTML, so a
    JSON API that omitted the header was parsed as a page and came back
    mangled. A declared type is believed; only an undeclared body is sniffed,
    and only for `<html`."""
    p = await web("fetch", f"{base}/json-noctype")
    assert not p.extracted and p.title == ""
    assert p.markdown == '{"a": 1, "b": [2, 3]}'


@pytest.mark.asyncio
async def test_fetch_declared_non_html_is_the_body_verbatim(base):
    for route, body in (("/api.json", '{"ok": true}'), ("/plain.txt", "just text\nline two")):
        p = await web("fetch", base + route)
        assert not p.extracted and p.markdown == body.strip()


@pytest.mark.asyncio
async def test_fetch_follows_redirects_and_reports_the_final_url(base):
    p = await web("fetch", f"{base}/redirect")
    assert p.url == f"{base}/page.html" and p.status == 200 and p.extracted


@pytest.mark.asyncio
async def test_fetch_sends_the_user_agent(base):
    assert (await web("fetch", f"{base}/echo-ua")).markdown == "CrowAgent/1.0"
    custom = "Mozilla/5.0 (X11; Linux x86_64) Crow/1"
    got = await web("fetch", f"{base}/echo-ua", user_agent=custom)
    assert got.markdown == custom


@pytest.mark.asyncio
async def test_fetch_404_names_the_status_and_url(base):
    """raise_for_status inside a bare `except Exception` made a 404 and a DNS
    failure indistinguishable — both came back as "Error fetching"."""
    with pytest.raises(WebError, match=rf"404 Not Found for {base}/missing"):
        await web("fetch", f"{base}/missing")


@pytest.mark.asyncio
async def test_fetch_non_text_says_how_to_download_it_instead(base):
    """Decoding a PDF into mojibake is worse than refusing, and httpx is
    ambient — so the error carries the two lines that do it properly."""
    with pytest.raises(WebError, match="application/pdf, not text") as exc:
        await web("fetch", f"{base}/doc.pdf")
    assert "httpx.AsyncClient()" in str(exc.value)
    assert "write_bytes" in str(exc.value)


@pytest.mark.asyncio
async def test_fetch_over_the_cap_is_refused_mid_stream(base):
    """Streamed against the cap, so 11MB is refused at 10MB rather than after
    it has landed in RAM — the lesson ripgrep taught fs."""
    with pytest.raises(WebError, match="over 10MB"):
        await web("fetch", f"{base}/over-cap")


@pytest.mark.asyncio
async def test_fetch_timeout_is_a_weberror(base, monkeypatch):
    monkeypatch.setattr(MOD, "_TIMEOUT", 0.05)
    with pytest.raises(WebError, match=rf"fetching {base}/slow failed"):
        await web("fetch", f"{base}/slow")


@pytest.mark.asyncio
async def test_fetch_missing_scheme_is_an_error_not_a_guess():
    with pytest.raises(WebError, match="missing an 'http://'"):
        await web("fetch", "example.com")


@pytest.mark.asyncio
async def test_page_text_is_a_window_over_the_whole_markdown(base):
    """.text is what the LLM sees and must not flood the context; .markdown is
    what code sees and must be whole. The tail says how many chars are left
    and gives the slice that reaches them."""
    p = await web("fetch", f"{base}/huge.txt")
    assert p.chars == len(HUGE.strip()) > 5000
    assert p.text.startswith(f"{base}/huge.txt — 200 text/plain,")
    assert ", unextracted" in p.text.splitlines()[0]
    lines = p.text.splitlines()
    assert lines[-1] == f"… {p.chars - 5000:,} more chars — markdown[5000:]"
    assert len(p.text) < 5200
    assert p.markdown[5000:5020] == HUGE.strip()[5000:5020]


@pytest.mark.asyncio
async def test_page_text_has_no_tail_when_the_page_fits(base):
    p = await web("fetch", f"{base}/plain.txt")
    assert "more chars" not in p.text
    assert p.text == (
        f"{base}/plain.txt — 200 text/plain, 18 chars, unextracted\n"
        "just text\nline two"
    )


# --- run / close (a real chromium, skipped without one) ---------------------


@pytest.mark.asyncio
async def test_run_renders_what_fetch_cannot(chromium, base):
    """The distinction the mode exists for: fetch reads the bytes the server
    sent, run reads the DOM after the page's JavaScript ran. Same route, same
    request — different pages."""
    f = await web("fetch", f"{base}/js")
    r = await web("run", f"{base}/js", screenshot=False)
    assert (f.title, f.markdown, f.rendered) == ("Static Title", "before", False)
    assert isinstance(r, PageResult) and r
    assert r.rendered and r.status == 200
    assert r.title == "Rendered Title"
    assert r.markdown == "built by JS"
    assert "built by JS" in r.html
    assert r.url == f"{base}/js"
    assert ", rendered" in r.text.splitlines()[0]
    assert r.screenshot is None and "screenshot" not in r.text


@pytest.mark.asyncio
async def test_run_screenshot_rides_the_row(chromium, base, tmp_path):
    """The artifact that earns the wrapper its place: bytes on disk are
    invisible to the model, so the PNG goes to the ImageStore and its ref
    rides the row — the drain hydrates it into an image_url block."""
    begin_cell(session_id="s1", parent_tool_call_id="t/c", images_dir=str(tmp_path / "img"))
    r = await web("run", f"{base}/js")
    assert isinstance(r.screenshot, VisionResult)
    assert r.screenshot.mime == "image/png"
    assert (r.screenshot.width, r.screenshot.height) == (1280, 720)
    assert r.screenshot.source == f"{base}/js"
    blobs = [p for p in (tmp_path / "img").rglob("*.png")]
    assert len(blobs) == 1
    assert blobs[0].read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert r.screenshot.image.size == (1280, 720)
    assert r.llm_images() == [{"key": r.screenshot.key, "mime": "image/png"}]
    entry = pending()[0]
    assert (entry.tool, entry.mode, entry.result_kind) == ("web", "run", "web")
    assert entry.llm_images == r.llm_images()
    assert ", screenshot" in entry.acp_payload["text"]


@pytest.mark.asyncio
async def test_run_screenshot_is_capped_like_vision(chromium, base, tmp_path, monkeypatch):
    """The viewport is 1280x720 by default but r.page.set_viewport_size is
    ambient, so a screenshot goes through vision's cap: a 3000px shot is
    bytes no vision model wants."""
    vision_mod = sys.modules["crow_cli.tools.vision"]
    monkeypatch.setattr(vision_mod, "_MAX_DIM", 100)
    begin_cell(session_id="s1", parent_tool_call_id="t/c", images_dir=str(tmp_path / "img"))
    r = await web("run", f"{base}/js")
    assert (r.screenshot.width, r.screenshot.height) == (100, 56)


@pytest.mark.asyncio
async def test_run_page_is_live_then_stale(chromium, base):
    """`.page` is raw playwright in the kernel — and the NEXT run closes it,
    so a stale one raises instead of silently pointing at a different
    navigation (verified live: a shared page made cell 1's r.page click the
    wrong thing by cell 3)."""
    first = await web("run", f"{base}/js", screenshot=False)
    page = first.page
    assert not page.is_closed()
    handle = await page.wait_for_selector("#app")
    assert await handle.text_content() == "built by JS"

    second = await web("run", f"{base}/page.html", screenshot=False)
    assert second.page is not page and page.is_closed()
    with pytest.raises(Exception, match="closed"):
        await page.title()


@pytest.mark.asyncio
async def test_run_context_survives_across_runs(chromium, base):
    """Cookies and storage live on the context, which is created once: a new
    page per run must not mean a new identity per run."""
    await web("run", f"{base}/js", screenshot=False)
    first_context = MOD._state["context"]
    await web("run", f"{base}/page.html", screenshot=False)
    assert MOD._state["context"] is first_context


@pytest.mark.asyncio
async def test_run_gather_is_serialized_and_each_result_is_its_own(chromium, base):
    """One page at a time, so two gotos cannot race on it — but gather still
    returns one correct result per URL, each with its own page."""
    rs = await asyncio.gather(
        *[web("run", f"{base}{u}", screenshot=False) for u in ("/js", "/page.html")]
    )
    assert [r.title for r in rs] == ["Rendered Title", "Tiny Page"]
    assert rs[0].page is not rs[1].page
    assert rs[0].page.is_closed() and not rs[1].page.is_closed()


@pytest.mark.asyncio
async def test_run_http_error_raises_like_fetch(chromium, base):
    """A PageResult is a page that was RETRIEVED: fetch raises on >= 400 and
    so does run, or .status would mean two different things in two modes."""
    with pytest.raises(WebError, match=rf"404 Not Found for {base}/missing"):
        await web("run", f"{base}/missing", screenshot=False)


@pytest.mark.asyncio
async def test_run_timeout_is_seconds(chromium, base):
    """The server sleeps 6s; 0.5s of patience must raise, in seconds, not in
    playwright's milliseconds."""
    with pytest.raises(WebError, match=r"failed on .*hang"):
        await web("run", f"{base}/hang", screenshot=False, timeout=0.5)


@pytest.mark.asyncio
async def test_run_without_an_image_store(chromium, base, monkeypatch):
    """Checked BEFORE launching anything: a browser with nowhere to put the
    artifact is a wasted launch and a confusing failure, and the error says
    how to proceed either way."""
    monkeypatch.setattr(MOD, "image_store", lambda: None)
    with pytest.raises(WebError, match="screenshot=False"):
        await web("run", f"{base}/js")
    r = await web("run", f"{base}/js", screenshot=False)
    assert r.screenshot is None


@pytest.mark.asyncio
async def test_close_is_idempotent_and_run_restarts(chromium, base):
    first = await web("close")
    assert isinstance(first, BrowserClosed) and not first.was_running
    assert first.text == "no browser was running"

    await web("run", f"{base}/js", screenshot=False)
    assert MOD._state["browser"] is not None
    closed = await web("close")
    assert closed.was_running and closed.text == "browser closed"
    assert MOD._state == {**MOD._state, "pw": None, "browser": None, "context": None, "page": None}

    again = await web("close")
    assert not again.was_running

    restarted = await web("run", f"{base}/js", screenshot=False)
    assert restarted.status == 200


@pytest.mark.asyncio
async def test_close_records_a_row():
    begin_cell(session_id="s1", parent_tool_call_id="t/c")
    await web("close")
    entry = pending()[0]
    assert (entry.tool, entry.mode, entry.status, entry.result_kind) == (
        "web",
        "close",
        "completed",
        "text",
    )
    assert entry.acp_payload["text"] == "no browser was running"


# --- guards ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_mode():
    with pytest.raises(WebError, match=r"unknown web mode 'crawl'"):
        await web("crawl", "x")


@pytest.mark.asyncio
async def test_missing_and_blank_target():
    """A blank query is a caller bug, and SearXNG answers one with a plugin's
    clock reading instead of an error — a nonsense success that hides the
    mistake."""
    for mode in ("search", "fetch"):
        with pytest.raises(WebError, match=rf"mode='{mode}' requires target="):
            await web(mode)
        with pytest.raises(WebError, match=rf"mode='{mode}' requires target="):
            await web(mode, "   ")


@pytest.mark.asyncio
async def test_arguments_are_not_silently_ignored_on_the_wrong_mode(base):
    """Cross-cutting, checked before either mode runs: an argument the caller
    cared about must never be quietly dropped."""
    with pytest.raises(WebError, match="a page is not paginated"):
        await web("fetch", f"{base}/plain.txt", limit=5)
    with pytest.raises(WebError, match="user_agent= is for mode='fetch'"):
        await web("search", "anything", user_agent="Bot/1")


@pytest.mark.asyncio
async def test_negative_limit():
    with pytest.raises(WebError, match="limit must be >= 0, got -1"):
        await web("search", "anything", limit=-1)


@pytest.mark.asyncio
async def test_run_arguments_are_rejected_elsewhere(base):
    """wait_until/timeout/screenshot are browser vocabulary; passing them to
    fetch or search must not be silently dropped."""
    with pytest.raises(WebError, match=r"screenshot= is for mode='run'"):
        await web("fetch", f"{base}/plain.txt", screenshot=True)
    with pytest.raises(WebError, match=r"wait_until= is for mode='run'"):
        await web("fetch", f"{base}/plain.txt", wait_until="load")
    with pytest.raises(WebError, match=r"timeout= is for mode='run'"):
        await web("search", "anything", timeout=5)


@pytest.mark.asyncio
async def test_wait_until_is_playwrights_vocabulary():
    with pytest.raises(WebError, match=r"unknown wait_until 'whenever'"):
        await web("run", "https://example.com/", wait_until="whenever")


@pytest.mark.asyncio
async def test_timeout_must_be_positive():
    for bad in (0, -1):
        with pytest.raises(WebError, match=rf"timeout must be > 0 seconds, got {bad}"):
            await web("run", "https://example.com/", timeout=bad)


@pytest.mark.asyncio
async def test_close_takes_no_target():
    with pytest.raises(WebError, match=r"mode='close' takes no target="):
        await web("close", "https://example.com/")


# --- internals -------------------------------------------------------------


def test_is_html_believes_a_declared_type():
    assert _is_html("text/html; charset=utf-8", "")
    assert _is_html("application/xhtml+xml", "")
    assert not _is_html("application/json", "<html><body>x")
    assert not _is_html("text/plain", "<html>")


def test_is_html_sniffs_only_an_undeclared_body():
    assert _is_html("", "<html><head>")
    assert _is_html("", "  <HTML lang='en'>")
    assert not _is_html("", '{"a": 1}')
    assert not _is_html("", "")


def test_is_texty():
    assert _is_texty("text/plain")
    assert _is_texty("text/html; charset=utf-8")
    assert _is_texty("application/json")
    assert _is_texty("application/vnd.api+json")
    assert _is_texty("application/atom+xml")
    assert _is_texty("")  # undeclared: assume text, then sniff
    assert not _is_texty("application/pdf")
    assert not _is_texty("image/png")
    assert not _is_texty("application/octet-stream")


def test_answer_shapes():
    assert _answer("plain") == "plain"
    assert _answer({"answer": "the text", "template": "t"}) == "the text"
    assert _answer({"engine": "e", "translations": [1]}) == '{"translations": [1]}'
    assert _answer(42) == "42"


def test_engine_down_shapes():
    assert _engine_down(["duckduckgo", "CAPTCHA"]) == "duckduckgo (CAPTCHA)"
    assert _engine_down(["duckduckgo"]) == "duckduckgo"
    assert _engine_down(["duckduckgo", ""]) == "duckduckgo"
    assert _engine_down("brave") == "brave"


def test_use_readability_without_node(monkeypatch):
    """readabilipy's own have_node() spawns `node -v` per call and runs
    `npm install` when its node_modules is missing — and npm install chdirs
    the whole process. Availability is decided here instead, so a fetch can
    never trigger a network install or a cwd race in a kernel where other
    cells resolve relative paths."""
    monkeypatch.setattr(MOD.shutil, "which", lambda _: None)
    assert MOD._use_readability() is False
    assert MOD._readability is False  # cached: decided once per kernel


def test_use_readability_without_bundled_node_modules(monkeypatch, tmp_path):
    """The other half of the guard: node present, readabilipy's bundled
    node_modules absent — exactly the state in which readabilipy would shell
    out to `npm install`. A stat of a directory decides it instead."""
    import importlib.machinery
    import types

    monkeypatch.setattr(MOD.shutil, "which", lambda _: "/usr/bin/node")
    fake = types.ModuleType("readabilipy")
    fake.__spec__ = importlib.machinery.ModuleSpec(
        "readabilipy",
        None,
        origin=str(tmp_path / "readabilipy" / "__init__.py"),
    )
    monkeypatch.setitem(sys.modules, "readabilipy", fake)
    assert MOD._use_readability() is False


# --- register --------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_records_entry():
    begin_cell(session_id="s1", parent_tool_call_id="t/c")
    await web("search", "anything")
    entries = pending()
    assert [(e.tool, e.mode, e.status, e.result_kind) for e in entries] == [
        ("web", "search", "completed", "search")
    ]
    assert entries[0].args["target"] == "anything"
    payload = entries[0].acp_payload
    assert payload["content"] == "text"
    # A subject, not a path: a query is displayed, never claimed as a location.
    assert payload["subject"] == "anything"
    assert "path" not in payload
    assert payload["text"].startswith("anything — 3 of 3 hits")


@pytest.mark.asyncio
async def test_fetch_records_entry_with_the_url_as_subject(base):
    begin_cell(session_id="s1", parent_tool_call_id="t/c")
    await web("fetch", f"{base}/plain.txt")
    entry = pending()[0]
    assert (entry.tool, entry.mode, entry.status, entry.result_kind) == (
        "web",
        "fetch",
        "completed",
        "web",
    )
    assert entry.acp_payload["subject"] == f"{base}/plain.txt"


@pytest.mark.asyncio
async def test_failure_records_failed(base):
    begin_cell(session_id="s1", parent_tool_call_id="t/c")
    with pytest.raises(WebError):
        await web("fetch", f"{base}/missing")
    assert [(e.tool, e.mode, e.status) for e in pending()] == [
        ("web", "fetch", "failed")
    ]
    assert "404" in pending()[0].error


@pytest.mark.asyncio
async def test_gather_records_one_row_per_call():
    """One row is one call — the model's parallelism must not collapse into a
    single ACP tool call. Rows land in COMPLETION order, which is the honest
    order for concurrent calls (and each carries started_at/ended_at), so
    this compares as a set rather than a sequence."""
    begin_cell(session_id="s1", parent_tool_call_id="t/c")
    await asyncio.gather(*[web("search", q) for q in ("one", "two", "three")])
    assert sorted(e.args["target"] for e in pending()) == ["one", "three", "two"]
    assert all(e.parent_tool_call_id == "t/c" for e in pending())
