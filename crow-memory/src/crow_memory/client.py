"""Thin HTTP client for the crow-memory service.

This is what crow-cli's session.py and crow-mcp's query_memory import instead
of touching SQLAlchemy / LanceDB directly. Mirrors the AgentSession interface
plus search. Shares schemas with the server so the contract can't drift.
"""

import base64

import httpx

DEFAULT_URL = "http://localhost:8901"


class MemoryClient:
    def __init__(self, base_url: str = DEFAULT_URL, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _post(self, path, json):
        r = self._http.post(path, json=json)
        r.raise_for_status()
        return r.json()

    def _get(self, path, params=None):
        r = self._http.get(path, params=params)
        r.raise_for_status()
        return r.json()

    def health(self) -> dict:
        return self._get("/health")

    # ---- agents (replaces AgentSession.create / .load) ----
    def create_agent(self, *, agent_id, session_id, agent_idx=1, cwd="/tmp",
                     prompt_id=None, prompt_args=None, system_prompt="",
                     tool_definitions=None, request_params=None,
                     model_identifier="", initial_messages=None) -> dict:
        return self._post("/agents", {
            "agent_id": agent_id, "session_id": session_id, "agent_idx": agent_idx,
            "cwd": cwd, "prompt_id": prompt_id, "prompt_args": prompt_args or {},
            "system_prompt": system_prompt, "tool_definitions": tool_definitions or [],
            "request_params": request_params or {}, "model_identifier": model_identifier,
            "initial_messages": initial_messages or [],
        })

    def load(self, agent_id: str, hydrate: bool = False) -> tuple[dict, list[dict]]:
        data = self._get(f"/agents/{agent_id}", params={"hydrate": hydrate})
        return data["agent"], data["messages"]

    # ---- messages (replaces add_message / _save_messages) ----
    def add_message(self, agent_id: str, message: dict, usage: dict | None = None) -> dict:
        return self._post(f"/agents/{agent_id}/messages", {"message": message, "usage": usage})

    def save_messages(self, agent_id: str, messages: list[dict]) -> dict:
        return self._post(f"/agents/{agent_id}/messages/batch", {"messages": messages})

    # ---- sessions ----
    def get_max_agent_idx(self, session_id: str) -> int:
        return self._get(f"/sessions/{session_id}/max-idx")["max_agent_idx"]

    # ---- prompts (replaces lookup_or_create_prompt) ----
    def upsert_prompt(self, prompt_id: str, name: str, template: str) -> dict:
        return self._post("/prompts", {"id": prompt_id, "name": name, "template": template})

    # ---- images ----
    def get_image(self, image_id: str) -> tuple[bytes, str]:
        r = self._http.get(f"/images/{image_id}")
        r.raise_for_status()
        return r.content, r.headers.get("content-type", "image/png")

    # ---- search (replaces query_memory) ----
    def search(self, query: str | None = None, modality: str = "text",
               filters: dict | None = None, limit: int = 10,
               query_image: bytes | None = None) -> dict:
        payload = {"query": query, "modality": modality, "filters": filters, "limit": limit}
        if query_image is not None:
            payload["query_image_b64"] = base64.b64encode(query_image).decode()
        return self._post("/search", payload)
