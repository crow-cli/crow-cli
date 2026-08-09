"""Tests for web_fetch pagination/truncation logic (network mocked out)."""

import pytest

# `from`-import (not `import ... as`) — the module sits in a circular import
# chain (web_fetch.main <-> server.main) that breaks the `import a.b.c as x` form.
from crow_mcp.web_fetch import main as wf


@pytest.fixture
def fake_fetch(monkeypatch):
    """Patch fetch_url so no real HTTP happens."""

    def _set(content, prefix=""):
        async def _fake(url, user_agent=wf.DEFAULT_USER_AGENT):
            return content, prefix

        monkeypatch.setattr(wf, "fetch_url", _fake)

    return _set


class TestWebFetch:
    async def test_basic_content(self, fake_fetch):
        fake_fetch("hello world")
        out = await wf.web_fetch(url="http://x", max_length=5000)
        assert "hello world" in out
        assert "http://x" in out

    async def test_truncation_hint(self, fake_fetch):
        fake_fetch("a" * 100)
        out = await wf.web_fetch(url="http://x", max_length=10, start_index=0)
        assert "truncated" in out.lower()
        assert "start_index=10" in out

    async def test_start_index_beyond_end(self, fake_fetch):
        fake_fetch("short")
        out = await wf.web_fetch(url="http://x", max_length=10, start_index=999)
        assert "No more content" in out

    async def test_raw_mode(self, fake_fetch):
        fake_fetch("<html>raw</html>")
        out = await wf.web_fetch(url="http://x", raw=True, max_length=5000)
        assert "Raw HTML" in out
        assert "<html>raw</html>" in out

    async def test_prefix_included(self, fake_fetch):
        fake_fetch("body", prefix="Content type: text/plain\n")
        out = await wf.web_fetch(url="http://x", max_length=5000)
        assert "Content type: text/plain" in out

    async def test_error_path(self, monkeypatch):
        async def _boom(url, user_agent=wf.DEFAULT_USER_AGENT):
            raise RuntimeError("kaboom")

        monkeypatch.setattr(wf, "fetch_url", _boom)
        out = await wf.web_fetch(url="http://x")
        assert "Error fetching" in out and "kaboom" in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
