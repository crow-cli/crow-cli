"""Wire types for the crow-memory SDK.

The record/request classes come from the `crow_memory_types` native
module — the crow-memory-types rust crate compiled with PyO3. Validation
and serialization run through the SAME serde impls as the crow-memory
server: one contract, no codegen, nothing to drift.

This module re-exports them and adds client-side ergonomics:

- `MessageRecord`: derived `session_id` / `agent_idx` properties
- `ImageRecord`: `data` as decoded bytes (the wire carries base64 str)
- `SessionInfo`: `last_message` as a `MessageRecord` wrapper
- `MemoryApiError`, `SearchResults`, `default_memory_url`: client-only
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field

import crow_memory_types as _wire
from crow_memory_types import (
    DEFAULT_MEMORY_PORT,
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
)

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


class MessageRecord:
    """Wire MessageRecord + derived `session_id` / `agent_idx`."""

    __slots__ = ("_w",)

    def __init__(self, wire: _wire.MessageRecord) -> None:
        self._w = wire

    @classmethod
    def from_dict(cls, d: object) -> MessageRecord:
        return cls(_wire.MessageRecord.from_dict(d))

    @classmethod
    def from_json(cls, s: str) -> MessageRecord:
        return cls(_wire.MessageRecord.from_json(s))

    def to_dict(self) -> dict:
        return self._w.to_dict()

    def to_json(self) -> str:
        return self._w.to_json()

    @property
    def session_id(self) -> str:
        """agent_id is '{session_id}-{agent_idx}'; the idx is the last segment."""
        return self._w.agent_id.rsplit("-", 1)[0]

    @property
    def agent_idx(self) -> int | None:
        try:
            return int(self._w.agent_id.rsplit("-", 1)[1])
        except (IndexError, ValueError):
            return None

    def __getattr__(self, name: str):
        return getattr(self._w, name)

    def __repr__(self) -> str:
        return repr(self._w)


class ImageRecord:
    """Wire ImageRecord with `data` decoded to bytes (wire carries base64)."""

    __slots__ = ("_w", "_data")

    def __init__(self, wire: _wire.ImageRecord) -> None:
        self._w = wire
        self._data: bytes | None = None

    @classmethod
    def from_dict(cls, d: object) -> ImageRecord:
        return cls(_wire.ImageRecord.from_dict(d))

    @classmethod
    def from_json(cls, s: str) -> ImageRecord:
        return cls(_wire.ImageRecord.from_json(s))

    @property
    def data(self) -> bytes:
        if self._data is None:
            self._data = base64.b64decode(self._w.data)
        return self._data

    def to_dict(self) -> dict:
        return self._w.to_dict()

    def to_json(self) -> str:
        return self._w.to_json()

    def __getattr__(self, name: str):
        return getattr(self._w, name)

    def __repr__(self) -> str:
        return repr(self._w)


class SessionInfo:
    """Wire SessionInfo with `last_message` as a `MessageRecord` wrapper."""

    __slots__ = ("_w",)

    def __init__(self, wire: _wire.SessionInfo) -> None:
        self._w = wire

    @classmethod
    def from_dict(cls, d: object) -> SessionInfo:
        return cls(_wire.SessionInfo.from_dict(d))

    @classmethod
    def from_json(cls, s: str) -> SessionInfo:
        return cls(_wire.SessionInfo.from_json(s))

    @property
    def last_message(self) -> MessageRecord | None:
        lm = self._w.last_message
        return MessageRecord.from_dict(lm) if lm is not None else None

    def to_dict(self) -> dict:
        return self._w.to_dict()

    def to_json(self) -> str:
        return self._w.to_json()

    def __getattr__(self, name: str):
        return getattr(self._w, name)

    def __repr__(self) -> str:
        return repr(self._w)


@dataclass
class SearchResults:
    """Result of a memory search. Image search is unwired upstream (the
    images table has no index), so `images` is always empty for now."""

    messages: list[MessageRecord] = field(default_factory=list)
    images: list[ImageRecord] = field(default_factory=list)
