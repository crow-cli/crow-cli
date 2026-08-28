"""Lazy heap-trim middleware — keep a long-lived server's RSS at its live set.

A Python MCP server does not leak the objects a request builds: refcounts
drop, the GC collects them. The retention is one layer down. glibc's malloc
retires freed chunks into per-thread arenas and only returns an arena to the
OS when its top is free, so a long-lived process's RSS is a HIGH-WATER MARK,
not a live count. Every large transient — materializing a big session, a
large tool result — stretches an arena to a new peak, the objects die, and
the peak stays. Over days the footprint ratchets to hundreds of MB that
nothing is using.

The fix is to ask the allocator for the free pages back once the request is
done. That is what this middleware does, on a cadence rather than every call:
trimming is cheap when there is nothing to trim, so every-N requests keeps RSS
snapping back to the live set without paying the cost per request.

Platform behavior:
  * Linux/glibc  -> ``malloc_trim(0)`` returns free arena memory to the OS.
  * musl / macOS / Windows -> no ``malloc_trim``; the middleware degrades to a
    periodic ``gc.collect()`` only (still useful for cyclic garbage).

This is deliberately a *policy* knob, not a correctness requirement: the
server behaves identically with it absent.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import gc
import logging
import sys
from typing import Any

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

logger = logging.getLogger(__name__)

_MALLOC_TRIM = None
_RESOLVED = False


def _resolve_malloc_trim():
    """Return libc's ``malloc_trim`` if this platform has it, else None.

    Resolved once. ``malloc_trim`` is glibc-specific; musl and the BSD/macOS
    allocators don't provide it, so absence is normal and not an error.
    """
    global _MALLOC_TRIM, _RESOLVED
    if _RESOLVED:
        return _MALLOC_TRIM
    _RESOLVED = True
    if sys.platform != "linux":
        return None
    try:
        libc_name = ctypes.util.find_library("c") or "libc.so.6"
        libc = ctypes.CDLL(libc_name, use_errno=True)
        fn = libc.malloc_trim
    except (OSError, AttributeError):
        return None
    fn.argtypes = [ctypes.c_size_t]
    fn.restype = ctypes.c_int
    _MALLOC_TRIM = fn
    return _MALLOC_TRIM


def evict() -> bool:
    """Reclaim cyclic garbage, then hand free heap pages back to the OS.

    Returns True if the allocator reported releasing memory. ``gc.collect()``
    runs first so cyclic structures (SQLAlchemy sessions, pydantic graphs)
    are freed before we ask glibc to return the now-free pages.
    """
    gc.collect()
    trim = _resolve_malloc_trim()
    if trim is None:
        return False
    try:
        return bool(trim(0))
    except Exception:  # pragma: no cover - defensive; never break a request
        logger.exception("heap trim failed; continuing")
        return False


class MemoryTrimMiddleware(Middleware):
    """Evict freed heap memory every ``every`` requests.

    Example:
        ```python
        from fastmcp import FastMCP
        from crow_cli.mcp.server.memtrim import MemoryTrimMiddleware

        mcp = FastMCP("MyServer")
        mcp.add_middleware(MemoryTrimMiddleware(every=10))
        ```

    Args:
        every: Trim once every this many requests (default 10). Trimming is
            cheap when nothing is free, so a small value is fine; raise it to
            amortize the cost on very chatty servers.
    """

    def __init__(self, every: int = 10):
        if every < 1:
            raise ValueError("every must be >= 1")
        self.every = every
        self._count = 0

    async def on_request(self, context: MiddlewareContext, call_next: CallNext) -> Any:
        try:
            return await call_next(context)
        finally:
            # Count requests, not just successes — a failed large query still
            # built the transient and freed it, so it still wants a trim.
            self._count += 1
            if self._count % self.every == 0:
                evict()
