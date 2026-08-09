"""Python client for the crow-memory HTTP service.

Mirrors the Rust `crow-memory-sdk` crate: same endpoints, same retry policy
(retry only connect errors + 502/503/504 with exponential backoff; everything
else fails fast — the v1 no-backoff retry storm lesson). Append-only memory:
create + read/search, no update, no delete.

Single flavor: `MemoryClient` (async, httpx.AsyncClient). Both consumers —
the crow-cli agent and crow-mcp — run async event loops, so the sync client
that used to live here was ripped out instead of maintained.
"""

from .types import (
    DEFAULT_MEMORY_PORT,
    AgentRecord,
    ImageRecord,
    MemoryApiError,
    MessageRecord,
    PromptRecord,
    SearchResults,
    SessionInfo,
    default_memory_url,
)
from .client import MemoryClient

__all__ = [
    "DEFAULT_MEMORY_PORT",
    "default_memory_url",
    "MemoryApiError",
    "PromptRecord",
    "AgentRecord",
    "MessageRecord",
    "SessionInfo",
    "ImageRecord",
    "SearchResults",
    "MemoryClient",
]
