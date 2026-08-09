"""Python client for the crow-memory HTTP service.

Mirrors the Rust `crow-memory-sdk` crate: same endpoints, same retry policy
(retry only connect errors + 502/503/504 with exponential backoff; everything
else fails fast — the v1 no-backoff retry storm lesson). Append-only memory:
create + read/search, no update, no delete.

Two flavors: `MemoryClient` (async, httpx.AsyncClient) and `SyncMemoryClient`
(httpx.Client) — identical surface.
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
from .sync_client import SyncMemoryClient

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
    "SyncMemoryClient",
]
