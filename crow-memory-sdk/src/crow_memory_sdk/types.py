"""Wire types for the crow-memory SDK.

The record/request models are GENERATED (`types_wire.py`) from the rust
`crow-memory-types` crate — the single source of truth for the HTTP
contract (see `scripts/gen_wire_types.py` and the drift test in
`tests/test_schema_drift.py`). This module re-exports them and adds
client-side ergonomics:

- `MessageRecord`: derived `session_id` / `agent_idx` properties
- `ImageRecord`: `data` as decoded bytes (the wire carries base64 str)
- `MemoryApiError`, `SearchResults`, `default_memory_url`: client-only
"""

from __future__ import annotations

import os

from pydantic import BaseModel

from . import types_wire
from .types_wire import (
    AddImageRequest,
    AddMessageRequest,
    AddMessageResponse,
    AgentRecord,
    CreateAgentRequest,
    ErrorResponse,
    LookupPromptRequest,
    LookupPromptResponse,
    MaxAgentIdxResponse,
    PromptRecord,
    SearchMessagesRequest,
    SessionInfo,
)

# Must match `pub const DEFAULT_MEMORY_PORT` in crow-memory-types/src/lib.rs
# (enforced by tests/test_schema_drift.py).
DEFAULT_MEMORY_PORT = 27697  # CROWS on a phone keypad

_RETRYABLE_STATUS = {502, 503, 504}

__all__ = [
    "DEFAULT_MEMORY_PORT",
    "default_memory_url",
    "MemoryApiError",
    "SearchResults",
    "AddImageRequest",
    "AddMessageRequest",
    "AddMessageResponse",
    "AgentRecord",
    "CreateAgentRequest",
    "ErrorResponse",
    "ImageRecord",
    "LookupPromptRequest",
    "LookupPromptResponse",
    "MaxAgentIdxResponse",
    "MessageRecord",
    "PromptRecord",
    "SearchMessagesRequest",
    "SessionInfo",
]


def default_memory_url() -> str:
    return os.environ.get("CROW_MEMORY_URL", f"http://127.0.0.1:{DEFAULT_MEMORY_PORT}")


class MemoryApiError(Exception):
    """Non-retryable API error: status code + server error message.

    status == 0 means the server was unreachable after all retries.
    """

    def __init__(self, status: int, error: str):
        super().__init__(f"crow-memory {status}: {error}")
        self.status = status
        self.error = error


class MessageRecord(types_wire.MessageRecord):
    @property
    def session_id(self) -> str:
        """agent_id is '{session_id}-{agent_idx}'; the idx is the last segment."""
        return self.agent_id.rsplit("-", 1)[0]

    @property
    def agent_idx(self) -> int | None:
        try:
            return int(self.agent_id.rsplit("-", 1)[1])
        except (IndexError, ValueError):
            return None


class ImageRecord(types_wire.ImageRecord):
    #: Decoded image bytes; the wire format carries base64 in a str.
    data: bytes


class SearchResults(BaseModel):
    """Result of a memory search. Image search is unwired upstream (the
    images table has no index), so `images` is always empty for now."""

    messages: list[MessageRecord] = []
    images: list[ImageRecord] = []
