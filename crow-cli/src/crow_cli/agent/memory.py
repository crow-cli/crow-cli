"""In-process memory layer for crow-cli.

Wraps crow-memory's MemoryStore (LanceDB + ColBERT/ColQwen2) directly — no
HTTP, no service, no retry logic. The embedders are loaded once per process
via a singleton; the model weights are mmap'd and shared with crow-mcp by the
kernel's page cache.
"""

import logging
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_MEMORY_PATH = str(Path.home() / ".crow" / "memory.lance")


class MemoryServiceError(Exception):
    """Raised when a memory operation fails (e.g. agent not found)."""

    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"memory error {status}: {detail}")


class MemoryClient:
    """In-process adapter over MemoryStore.

    Same interface as the old HTTP client so session.py / main.py don't change
    shape — but backed by a direct LanceDB connection. The `base_url` param is
    now a filesystem path (kept as positional for compat during transition).
    """

    def __init__(self, path: str = DEFAULT_MEMORY_PATH, **_kwargs):
        from crow_memory import get_store
        self._store = get_store(path)

    def close(self):
        pass  # nothing to close; store is process-global

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    # ---- agents ----

    def create_agent(
        self,
        *,
        agent_id: str,
        session_id: str,
        agent_idx: int = 1,
        cwd: str = "/tmp",
        prompt_id: str | None = None,
        prompt_args: dict | None = None,
        system_prompt: str = "",
        tool_definitions: list[dict] | None = None,
        request_params: dict | None = None,
        model_identifier: str = "",
        initial_messages: list[dict] | None = None,
    ) -> dict:
        agent = self._store.add_agent({
            "agent_id": agent_id,
            "session_id": session_id,
            "agent_idx": agent_idx,
            "cwd": cwd,
            "prompt_id": prompt_id,
            "prompt_args": prompt_args or {},
            "system_prompt": system_prompt,
            "tool_definitions": tool_definitions or [],
            "request_params": request_params or {},
            "model_identifier": model_identifier,
        })
        for m in (initial_messages or []):
            if m.get("role") != "system":
                self._store.add_message(agent_id, m)
        return agent

    def load(self, agent_id: str, hydrate: bool = False) -> tuple[dict, list[dict]]:
        agent = self._store.get_agent(agent_id)
        if agent is None:
            raise MemoryServiceError(404, f"agent '{agent_id}' not found")
        messages = self._store.load_messages(agent_id, hydrate_images=hydrate)
        return agent, messages

    def list_agents(self, session_id: str | None = None) -> list[dict]:
        return self._store.list_agents(session_id=session_id)

    # ---- messages ----

    def add_message(self, agent_id: str, message: dict, usage: dict | None = None) -> dict:
        return self._store.add_message(agent_id, message, usage)

    def save_messages(self, agent_id: str, messages: list[dict]) -> dict:
        ids = [self._store.add_message(agent_id, m)["id"] for m in messages]
        return {"agent_id": agent_id, "ids": ids, "count": len(ids)}

    def query_messages(
        self,
        *,
        session_id: str | None = None,
        agent_id: str | None = None,
        agent_idx: int | None = None,
        roles: list[str] | None = None,
        after: str | None = None,
        before: str | None = None,
        order: str = "asc",
        limit: int = 1_000_000,
        offset: int = 0,
    ) -> list[dict]:
        return self._store.query_messages(
            session_id=session_id, agent_id=agent_id, agent_idx=agent_idx,
            roles=roles, after=after, before=before, order=order,
            limit=limit, offset=offset,
        )

    # ---- sessions ----

    def get_max_agent_idx(self, session_id: str) -> int:
        return self._store.get_max_agent_idx(session_id)

    def list_sessions(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return self._store.list_sessions(limit=limit, offset=offset)

    # ---- prompts ----

    def lookup_or_create_prompt(self, template: str, name: str = "crow-default") -> str:
        result = self._store.lookup_or_create_prompt(template, name)
        return result["id"]

    def get_prompt(self, prompt_id: str) -> dict:
        p = self._store.get_prompt(prompt_id)
        if p is None:
            raise MemoryServiceError(404, f"prompt '{prompt_id}' not found")
        return p

    # ---- images ----

    def get_image(self, image_id: str) -> tuple[bytes, str]:
        img = self._store.get_image(image_id)
        if img is None:
            raise MemoryServiceError(404, f"image '{image_id}' not found")
        return img["data"], img["mime"]

    # ---- search ----

    def search(
        self,
        query: str | None = None,
        modality: str = "text",
        filters: dict | None = None,
        limit: int = 10,
        query_image: bytes | None = None,
    ) -> dict:
        out = {"messages": [], "images": []}
        if modality in ("text", "both") and query:
            out["messages"] = self._store.search_messages(query, filters, limit)
        if modality in ("image", "both"):
            out["images"] = self._store.search_images(
                query=query, query_image=query_image, limit=limit
            )
        return out
