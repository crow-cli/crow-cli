"""End-to-end paint test for the crow-gui browser runtime (`crow --web`).

The whole point of the wasm route (CONTEXT.md, "Web / wasm route") is that the
ratatui-over-wgpu render path gets real end-to-end feedback: a headless browser
actually rasterises the frames and we assert on the pixels.

Skips unless the wasm bundle has been staged:

    crate/scripts/build-web.sh

which runs `cargo build -p crow-gui --features web --target wasm32-unknown-unknown`
and wasm-bindgen into `crate/web/target/`.
"""

import http.server
import socket
import threading
from pathlib import Path

import pytest

CRATE = Path(__file__).resolve().parents[2] / "crate"
WEB = CRATE / "web"
STAGED = WEB / "target" / "crow_web.js"

pytestmark = pytest.mark.skipif(
    not STAGED.exists(),
    reason="wasm bundle not staged — run crate/scripts/build-web.sh",
)


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # keep pytest output clean
        pass


@pytest.fixture(scope="module")
def served_web():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    httpd = http.server.ThreadingHTTPServer(
        ("127.0.0.1", port), lambda *a: _Quiet(*a, directory=str(WEB))
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}/"
    httpd.shutdown()


@pytest.fixture(scope="module")
def browser_page(served_web):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        # The runner reports failures through `log` (console_log), not through
        # the probe object, so capture the console to make a timeout diagnosable.
        console = []
        page.on("console", lambda m: console.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: console.append(f"[pageerror] {e}"))
        page.goto(served_web)
        try:
            page.wait_for_function("window.__crowProbe && window.__crowProbe.ready === true",
                                   timeout=30_000)
        except Exception as exc:
            raise AssertionError(
                "backend never became ready: "
                f"{exc}\nconsole:\n" + "\n".join(console)
            ) from None
        yield page
        browser.close()


def _probe(page):
    return page.evaluate("window.__crowProbe")


def test_backend_reaches_ready_and_the_loop_is_live(browser_page):
    probe = _probe(browser_page)
    assert probe["stage"] == "ready", probe
    first = probe["frames"]
    browser_page.wait_for_timeout(1000)
    second = _probe(browser_page)["frames"]
    assert second > first, f"render loop stalled at {first} frames"


def test_paints_the_requested_palette(browser_page, tmp_path):
    import numpy as np
    from PIL import Image

    shot = tmp_path / "paint.png"
    browser_page.screenshot(path=str(shot))
    px = np.asarray(Image.open(shot).convert("RGB")).astype(int)

    flat = px.reshape(-1, 3)
    distinct = len(np.unique(flat, axis=0))
    # Anti-aliased glyph edges produce hundreds of shades; a blank canvas is ~1.
    assert distinct > 100, f"only {distinct} distinct colors — nothing was painted"

    r, g, b = px[..., 0], px[..., 1], px[..., 2]
    checks = {
        "dark bluish background dominates": ((b > r) & (flat.sum(axis=1) < 250).reshape(px.shape[:2])).mean() > 0.9,
        "near-white foreground glyphs": ((r > 200) & (g > 200) & (b > 200)).sum() > 500,
        "yellow span": ((r > 200) & (g > 200) & (b < 80)).sum() > 100,
        "cyan span": ((r < 80) & (g > 200) & (b > 200)).sum() > 100,
        "green span": ((r < 80) & (g > 90) & (g < 190) & (b < 80)).sum() > 100,
    }
    failed = [name for name, ok in checks.items() if not ok]
    assert not failed, f"missing from the raster: {failed}"
