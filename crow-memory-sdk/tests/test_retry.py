"""Retry-budget behavior of the async MemoryClient.

Real HTTP servers (http.server in a thread) drive the retry loop end to
end; only asyncio.sleep is recorded (not faked away) where exact delay
sequences are asserted, so the tests stay fast and non-flaky.
"""

import http.server
import threading

import pytest

from crow_memory_sdk import MemoryApiError
from crow_memory_sdk.client import MemoryClient


class _ScriptedHandler(http.server.BaseHTTPRequestHandler):
    """Returns status codes from `server.script`, one per request (the last
    entry repeats forever)."""

    def do_GET(self):
        n = self.server.hits
        self.server.hits += 1
        script = self.server.script
        code = script[min(n, len(script) - 1)]
        body = b'{"status":"ok"}' if code == 200 else b'{"error":"down"}'
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server_factory():
    servers = []

    def start(script: list[int]) -> tuple[str, http.server.ThreadingHTTPServer]:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _ScriptedHandler)
        srv.script = script
        srv.hits = 0
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return f"http://127.0.0.1:{srv.server_address[1]}", srv

    yield start
    for srv in servers:
        srv.shutdown()


async def test_retries_503_then_success(server_factory):
    url, srv = server_factory([503, 503, 200])
    async with MemoryClient(url, max_retries=5, base_delay=0.01) as c:
        await c.health()
    assert srv.hits == 3


async def test_retryable_status_exhausts(server_factory):
    url, srv = server_factory([503])
    async with MemoryClient(url, max_retries=3, base_delay=0.01) as c:
        with pytest.raises(MemoryApiError) as ei:
            await c.health()
    assert ei.value.status == 503
    assert srv.hits == 3


async def test_unlimited_retries_outlasts_finite_budget(server_factory):
    # 5 failures then success: impossible under max_retries=3, fine with
    # max_retries=0 (retry forever).
    url, srv = server_factory([503, 503, 503, 503, 503, 200])
    async with MemoryClient(url, max_retries=0, base_delay=0.01) as c:
        await c.health()
    assert srv.hits == 6


async def test_connect_error_fails_with_status_zero():
    # Nothing listens on port 1: connection refused is retryable until the
    # budget is exhausted, then MemoryApiError(status=0).
    async with MemoryClient("http://127.0.0.1:1", max_retries=2, base_delay=0.01) as c:
        with pytest.raises(MemoryApiError) as ei:
            await c.health()
    assert ei.value.status == 0


async def test_non_retryable_status_fails_fast(server_factory):
    url, srv = server_factory([500])
    async with MemoryClient(url, max_retries=5, base_delay=0.01) as c:
        with pytest.raises(MemoryApiError) as ei:
            await c.health()
    assert ei.value.status == 500
    assert srv.hits == 1  # no retry storm (the v1 lesson)


async def test_backoff_doubles_and_caps(server_factory, monkeypatch):
    url, _ = server_factory([503])
    sleeps: list[float] = []

    async def record_sleep(d):
        sleeps.append(d)

    monkeypatch.setattr("crow_memory_sdk.client.asyncio.sleep", record_sleep)
    async with MemoryClient(url, max_retries=6, base_delay=1.0, max_delay=3.0) as c:
        with pytest.raises(MemoryApiError):
            await c.health()
    # 6 attempts = 5 sleeps: 1 → 2 → 4 capped to 3 → 3 → 3
    assert sleeps == [1.0, 2.0, 3.0, 3.0, 3.0]


async def test_default_budget_unchanged(server_factory, monkeypatch):
    # Defaults keep the historical policy: 3 attempts, 0.2s doubling, no cap.
    url, srv = server_factory([503])
    sleeps: list[float] = []

    async def record_sleep(d):
        sleeps.append(d)

    monkeypatch.setattr("crow_memory_sdk.client.asyncio.sleep", record_sleep)
    async with MemoryClient(url) as c:
        with pytest.raises(MemoryApiError):
            await c.health()
    assert srv.hits == 3
    assert sleeps == [0.2, 0.4]
