"""Wire types for the crow-memory SDK — pydantic models.

Mirrors `crow-memory-types` in the Rust workspace. Models are tolerant:
extra fields from newer servers are ignored, missing fields from older
servers get defaults (same backward-compat contract as the Rust types).
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, ConfigDict

DEFAULT_MEMORY_PORT = 27697  # CROWS on a phone keypad

_RETRYABLE_STATUS = {502, 503, 504}


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


class _Record(BaseModel):
    model_config = ConfigDict(extra="ignore")


class PromptRecord(_Record):
    id: str
    name: str
    template: str


class AgentRecord(_Record):
    agent_id: str
    session_id: str
    agent_idx: int
    cwd: str = ""
    prompt_id: str = ""
    prompt_args: Any = None
    system_prompt: str = ""
    tool_definitions: Any = None
    request_params: Any = None
    model_identifier: str = ""
    status: str = ""
    created_at: str = ""


class MessageRecord(_Record):
    id: int
    agent_id: str
    created_at: str = ""
    data: Any = None
    role: str = ""
    #: Search relevance (lower = better, LanceDB `_distance`); semantic hits only.
    score: float | None = None

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


class SessionInfo(_Record):
    session_id: str
    last_activity: str = ""
    message_count: int = 0
    agent_count: int = 0
    last_role: str = ""
    cwd: str = ""
    model_identifier: str = ""
    agent_idxs: list[int] = []
    last_message: MessageRecord | None = None


class ImageRecord(_Record):
    image_id: str
    mime: str
    data: bytes
    w: int
    h: int
    created_at: str = ""


class SearchResults(_Record):
    """Result of a memory search. Image search is unwired upstream (the
    images table has no index), so `images` is always empty for now."""

    messages: list[MessageRecord] = []
    images: list[ImageRecord] = []
