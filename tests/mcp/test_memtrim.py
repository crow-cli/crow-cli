"""MemoryTrimMiddleware tests — real server, real client, real GC.

The middleware's job: after every N requests, run gc.collect() and hand free
heap pages back to the OS (malloc_trim on glibc). The end-to-end test proves
the wiring by creating cyclic garbage inside a tool — unreachable under
refcounting, reclaimable only by a full collection — and watching a weakref
finalist fire when the middleware's eviction collects it.
"""

import gc
import sys
import weakref

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.transports import FastMCPTransport

from crow_cli.mcp.server.memtrim import (
    MemoryTrimMiddleware,
    _resolve_malloc_trim,
    evict,
)


class TestEvict:
    def test_returns_bool(self):
        assert isinstance(evict(), bool)

    def test_malloc_trim_resolution(self):
        trim = _resolve_malloc_trim()
        if sys.platform == "linux":
            # glibc ships malloc_trim; the dev/CI target is glibc Linux.
            assert callable(trim)
        else:
            assert trim is None

    def test_evict_collects_cyclic_garbage(self):
        class Cycle:
            pass

        reclaimed = []
        was_enabled = gc.isenabled()
        gc.disable()
        try:
            gc.collect()  # baseline sweep; garbage made below survives until evict
            a, b = Cycle(), Cycle()
            a.other, b.other = b, a
            weakref.finalize(a, reclaimed.append, True)
            del a, b
            assert not reclaimed
            evict()
        finally:
            if was_enabled:
                gc.enable()
        assert reclaimed, "evict() must collect cyclic garbage"


class TestMemoryTrimMiddleware:
    def test_every_must_be_positive(self):
        with pytest.raises(ValueError):
            MemoryTrimMiddleware(every=0)

    @staticmethod
    def _server(every: int) -> tuple[FastMCP, MemoryTrimMiddleware, list]:
        mcp = FastMCP("memtrim-test")
        mw = MemoryTrimMiddleware(every=every)
        mcp.add_middleware(mw)
        reclaimed: list = []

        class Cycle:
            pass

        @mcp.tool
        def make_garbage() -> str:
            """Create a garbage cycle that only a full collection frees."""
            a, b = Cycle(), Cycle()
            a.other, b.other = b, a
            weakref.finalize(a, reclaimed.append, True)
            del a, b
            return "ok"

        @mcp.tool
        def explode() -> str:
            """A tool that fails — failed requests still count."""
            raise RuntimeError("boom")

        return mcp, mw, reclaimed

    async def test_eviction_fires_every_n_requests(self):
        mcp, mw, reclaimed = self._server(every=2)
        was_enabled = gc.isenabled()
        gc.disable()  # only the middleware's evict() may collect
        try:
            async with Client(FastMCPTransport(mcp)) as client:
                for _ in range(4):
                    result = await client.call_tool("make_garbage", {})
                    assert result.data == "ok"
        finally:
            if was_enabled:
                gc.enable()
        assert mw._count >= 4, "every tool call is a request"
        assert reclaimed, "middleware eviction must reclaim request garbage"

    async def test_failed_requests_are_counted(self):
        mcp, mw, _ = self._server(every=100)
        async with Client(FastMCPTransport(mcp)) as client:
            with pytest.raises(Exception):
                await client.call_tool("explode", {})
            before = mw._count
            with pytest.raises(Exception):
                await client.call_tool("explode", {})
        assert mw._count == before + 1, "failed requests still count toward trims"

    async def test_wired_into_production_server(self):
        from crow_cli.mcp.server.app import mcp as prod_mcp

        assert any(
            isinstance(m, MemoryTrimMiddleware) for m in prod_mcp.middleware
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
