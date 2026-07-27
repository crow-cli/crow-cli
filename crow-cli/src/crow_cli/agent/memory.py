"""
HTTP SDK for the crow-memory service.

This is crow-cli's persistence layer. It replaces SQLAlchemy/db.py for the live
ACP path: instead of opening a sqlite database, AgentSession talks to the
crow-memory FastAPI service over HTTP. Pure httpx — no torch, no lancedb, no
ORM. The heavy ML + LanceDB live server-side; crow-cli stays light.

The service URL comes from config (`Config.memory_url`, a config.yaml key — we
do NOT do env vars). `DEFAULT_MEMORY_URL` is just the standard local fallback.
"""

import base64

import httpx

DEFAULT_MEMORY_URL = "http://localhost:8901"


class MemoryServiceError(Exception):
    """Raised when the crow-memory service returns a non-2xx response."""

    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"crow-memory service error {status}: {detail}")


class MemoryClient:
    """Thin HTTP client mirroring the AgentSession persistence interface."""

    def __init__(self, base_url: str = DEFAULT_MEMORY_URL, timeout: float = 120.0):
        self.base_url = (base_url or DEFAULT_MEMORY_URL).rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- low-level ----
    def _post(self, path: str, json: dict) -> dict:
        try:
            r = self._http.post(path, json=json)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise MemoryServiceError(e.response.status_code, e.response.text) from e
        return r.json()

    def _get(self, path: str, params: dict | None = None) -> dict:
        try:
            r = self._http.get(path, params=params)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise MemoryServiceError(e.response.status_code, e.response.text) from e
        return r.json()

    def health(self) -> dict:
        return self._get("/health")

    # ---- agents (AgentSession.create / .load) ----
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
        return self._post(
            "/agents",
            {
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
                "initial_messages": initial_messages or [],
            },
        )

    def load(self, agent_id: str, hydrate: bool = False) -> tuple[dict, list[dict]]:
        """Return (agent_dict, messages). Raises MemoryServiceError(404) if absent."""
        data = self._get(f"/agents/{agent_id}", params={"hydrate": hydrate})
        return data["agent"], data["messages"]

    def list_agents(self, session_id: str | None = None) -> list[dict]:
        params = {"session_id": session_id} if session_id else None
        return self._get("/agents", params=params)

    # ---- messages (add_message / _save_messages) ----
    def add_message(self, agent_id: str, message: dict, usage: dict | None = None) -> dict:
        return self._post(
            f"/agents/{agent_id}/messages", {"message": message, "usage": usage}
        )

    def save_messages(self, agent_id: str, messages: list[dict]) -> dict:
        return self._post(f"/agents/{agent_id}/messages/batch", {"messages": messages})

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
        """Filtered message browse (no semantic search). Returns MessageRecord dicts."""
        return self._post(
            "/messages/query",
            {
                "session_id": session_id,
                "agent_id": agent_id,
                "agent_idx": agent_idx,
                "roles": roles,
                "after": after,
                "before": before,
                "order": order,
                "limit": limit,
                "offset": offset,
            },
        )

    # ---- sessions ----
    def get_max_agent_idx(self, session_id: str) -> int:
        return self._get(f"/sessions/{session_id}/max-idx")["max_agent_idx"]

    # ---- prompts (lookup_or_create_prompt) ----
    def lookup_or_create_prompt(self, template: str, name: str = "crow-default") -> str:
        """Look up a prompt by template content, else mint one. Returns the id."""
        return self._post("/prompts", {"template": template, "name": name})["id"]

    def get_prompt(self, prompt_id: str) -> dict:
        """Return {id, name, template, created}. Raises MemoryServiceError(404) if absent."""
        return self._get(f"/prompts/{prompt_id}")

    # ---- images ----
    def get_image(self, image_id: str) -> tuple[bytes, str]:
        try:
            r = self._http.get(f"/images/{image_id}")
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise MemoryServiceError(e.response.status_code, e.response.text) from e
        return r.content, r.headers.get("content-type", "image/png")

    # ---- search (semantic; backs the future query_memory) ----
    def search(
        self,
        query: str | None = None,
        modality: str = "text",
        filters: dict | None = None,
        limit: int = 10,
        query_image: bytes | None = None,
    ) -> dict:
        payload = {"query": query, "modality": modality, "filters": filters, "limit": limit}
        if query_image is not None:
            payload["query_image_b64"] = base64.b64encode(query_image).decode()
        return self._post("/search", payload)
