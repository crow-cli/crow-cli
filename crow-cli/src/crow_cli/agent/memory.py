"""
HTTP SDK for the crow-memory service.

This is crow-cli's persistence layer. It replaces SQLAlchemy/db.py for the live
ACP path: instead of opening a sqlite database, AgentSession talks to the
crow-memory FastAPI service over HTTP. Pure httpx — no torch, no lancedb, no
ORM. The heavy ML + LanceDB live server-side; crow-cli stays light.

The service URL comes from config (`Config.memory_url`, a config.yaml key — we
do NOT do env vars). `DEFAULT_MEMORY_URL` is just the standard local fallback.

Robustness contract: if the memory service is up AT ALL, the client will reach
it. Connection-class errors (stale keep-alive, service restart, network blip)
trigger an automatic client rebuild + retry with backoff. Application errors
(non-2xx) are never retried — those are intentional failures.
"""

import base64
import logging
import time

import httpx

DEFAULT_MEMORY_URL = "http://localhost:8901"

log = logging.getLogger(__name__)

# Connection-class errors that mean "the transport is broken, rebuild and retry."
# These are distinct from application errors (non-2xx) which should propagate.
_RETRYABLE = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
    httpx.CloseError,
    ConnectionResetError,
    BrokenPipeError,
    OSError,
)

DEFAULT_TIMEOUT = 10.0  # per-attempt; total budget = timeout * retries
DEFAULT_RETRIES = 3
RETRY_BACKOFF = 0.25  # seconds; doubles each attempt


class MemoryServiceError(Exception):
    """Raised when the crow-memory service returns a non-2xx response."""

    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"crow-memory service error {status}: {detail}")


class MemoryClient:
    """Thin HTTP client mirroring the AgentSession persistence interface.

    Automatically rebuilds the underlying httpx.Client on connection errors
    and retries with exponential backoff. If the service is reachable, the
    call succeeds — stale sockets, service restarts, and transient network
    blips are transparent.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_MEMORY_URL,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
    ):
        self.base_url = (base_url or DEFAULT_MEMORY_URL).rstrip("/")
        self._timeout = timeout
        self._retries = retries
        self._http = self._build_client()

    def _build_client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            timeout=self._timeout,
            transport=httpx.HTTPTransport(retries=1),
        )

    def _rebuild(self):
        """Close the current client and build a fresh one."""
        try:
            self._http.close()
        except Exception:
            pass
        self._http = self._build_client()

    def close(self):
        try:
            self._http.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- low-level with retry ----

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Execute an HTTP request with automatic reconnect + retry.

        Connection-class errors rebuild the client and retry with backoff.
        Application errors (non-2xx) raise MemoryServiceError immediately.
        """
        last_exc: Exception | None = None
        backoff = RETRY_BACKOFF

        for attempt in range(1, self._retries + 1):
            try:
                r = self._http.request(method, path, **kwargs)
                r.raise_for_status()
                return r
            except httpx.HTTPStatusError as e:
                # Application error — do NOT retry.
                raise MemoryServiceError(
                    e.response.status_code, e.response.text
                ) from e
            except _RETRYABLE as e:
                last_exc = e
                log.warning(
                    "memory service %s %s failed (attempt %d/%d): %s — rebuilding client",
                    method.upper(),
                    path,
                    attempt,
                    self._retries,
                    e,
                )
                self._rebuild()
                if attempt < self._retries:
                    time.sleep(backoff)
                    backoff *= 2

        raise ConnectionError(
            f"crow-memory service unreachable after {self._retries} attempts: {last_exc}"
        ) from last_exc

    def _post(self, path: str, json: dict) -> dict:
        return self._request("POST", path, json=json).json()

    def _get(self, path: str, params: dict | None = None) -> dict:
        return self._request("GET", path, params=params).json()

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

    def list_sessions(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """Sessions ordered by most-recent message activity (desc)."""
        return self._get("/sessions", {"limit": limit, "offset": offset})

    # ---- prompts (lookup_or_create_prompt) ----
    def lookup_or_create_prompt(self, template: str, name: str = "crow-default") -> str:
        """Look up a prompt by template content, else mint one. Returns the id."""
        return self._post("/prompts", {"template": template, "name": name})["id"]

    def get_prompt(self, prompt_id: str) -> dict:
        """Return {id, name, template, created}. Raises MemoryServiceError(404) if absent."""
        return self._get(f"/prompts/{prompt_id}")

    # ---- images ----
    def get_image(self, image_id: str) -> tuple[bytes, str]:
        r = self._request("GET", f"/images/{image_id}")
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
