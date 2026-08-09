"""Memory layer for crow-cli — client for the crow-memory HTTP service.

Was: in-process LanceDB via the crow-memory package (a ~2GB dataset mmap per
process). Now: talks to the shared crow-memory service (default
http://127.0.0.1:27697, override with CROW_MEMORY_URL) through
crow-memory-sdk's sync client. The agent process no longer opens LanceDB.

Interface is unchanged so session.py / main.py keep their shape; records come
back as pydantic models (AgentRecord, MessageRecord, SessionInfo, ...). The
old `path` positional (a LanceDB directory) is accepted and ignored — kept
for call-site compat during transition.
"""

import logging

from crow_memory_sdk import (
    AgentRecord,
    ImageRecord,
    MemoryApiError,
    MessageRecord,
    PromptRecord,
    SearchResults,
    SessionInfo,
    SyncMemoryClient,
)

log = logging.getLogger(__name__)

#: Legacy sentinel. Memory lives in the crow-memory service now, not a path.
DEFAULT_MEMORY_PATH = "~/.crow/memory.lance (unused — see CROW_MEMORY_URL)"

#: Server-side query cap; filtering happens client-side above this.
_FETCH_ALL = 1_000_000


class MemoryServiceError(Exception):
    """Raised when a memory operation fails (e.g. agent not found)."""

    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"memory error {status}: {detail}")


class MemoryClient:
    """Adapter over the crow-memory HTTP service (sync, pydantic out).

    `path` is ignored (kept positionally for compat).
    """

    def __init__(self, path: str | None = None, **_kwargs):
        self._sdk = SyncMemoryClient()

    def close(self):
        self._sdk.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _call(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except MemoryApiError as e:
            raise MemoryServiceError(e.status, e.error) from e

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
    ) -> AgentRecord:
        self._call(
            self._sdk.create_agent,
            agent_id=agent_id,
            session_id=session_id,
            agent_idx=agent_idx,
            cwd=cwd,
            prompt_id=prompt_id or "",
            prompt_args=prompt_args or {},
            system_prompt=system_prompt,
            tool_definitions=tool_definitions or [],
            request_params=request_params or {},
            model_identifier=model_identifier,
        )
        for m in (initial_messages or []):
            if m.get("role") != "system":
                self._call(self._sdk.add_message, agent_id, m)
        agent = self._call(self._sdk.get_agent, agent_id)
        if agent is None:
            raise MemoryServiceError(500, f"agent '{agent_id}' vanished after create")
        return agent

    def load(self, agent_id: str, hydrate: bool = False) -> tuple[AgentRecord, list[dict]]:
        agent = self._call(self._sdk.get_agent, agent_id)
        if agent is None:
            raise MemoryServiceError(404, f"agent '{agent_id}' not found")
        messages = self._call(self._sdk.load_messages, agent_id, hydrate)
        return agent, messages

    def list_agents(self, session_id: str | None = None) -> list[AgentRecord]:
        return self._call(self._sdk.list_agents, session_id)

    # ---- messages ----

    def add_message(self, agent_id: str, message: dict, usage: dict | None = None) -> int:
        return self._call(self._sdk.add_message, agent_id, message, usage)

    def save_messages(self, agent_id: str, messages: list[dict]) -> list[int]:
        return [self._call(self._sdk.add_message, agent_id, m) for m in messages]

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
        limit: int = _FETCH_ALL,
        offset: int = 0,
    ) -> list[MessageRecord]:
        if agent_id is not None:
            agent_ids = [agent_id]
        elif session_id is not None:
            agent_ids = [a.agent_id for a in self._call(self._sdk.list_agents, session_id)]
        else:
            raise MemoryServiceError(400, "query_messages needs session_id or agent_id")

        recs: list[MessageRecord] = []
        for aid in agent_ids:
            for r in self._call(
                self._sdk.query_messages_by_agent, aid, order_asc=True, limit=_FETCH_ALL
            ):
                if agent_idx is not None and r.agent_idx != agent_idx:
                    continue
                if after is not None and r.created_at < after:
                    continue
                if before is not None and r.created_at > before:
                    continue
                if roles is not None and r.role not in roles:
                    continue
                recs.append(r)
        recs.sort(key=lambda r: r.created_at, reverse=(order != "asc"))
        return recs[offset : offset + limit]

    # ---- sessions ----

    def get_max_agent_idx(self, session_id: str) -> int:
        return self._call(self._sdk.get_max_agent_idx, session_id)

    def list_sessions(self, limit: int = 50, offset: int = 0) -> list[SessionInfo]:
        return self._call(self._sdk.list_sessions, limit, offset)

    # ---- prompts ----

    def lookup_or_create_prompt(self, template: str, name: str = "crow-default") -> str:
        return self._call(self._sdk.lookup_or_create_prompt, template, name)

    def get_prompt(self, prompt_id: str) -> PromptRecord:
        p = self._call(self._sdk.get_prompt, prompt_id)
        if p is None:
            raise MemoryServiceError(404, f"prompt '{prompt_id}' not found")
        return p

    # ---- images ----

    def get_image(self, image_id: str) -> ImageRecord:
        img = self._call(self._sdk.get_image, image_id)
        if img is None:
            raise MemoryServiceError(404, f"image '{image_id}' not found")
        return img

    # ---- search ----

    def search(
        self,
        query: str | None = None,
        modality: str = "text",
        filters: dict | None = None,
        limit: int = 10,
        query_image: bytes | None = None,
    ) -> SearchResults:
        messages: list[MessageRecord] = []
        if modality in ("text", "both") and query:
            # The service searches globally; session/agent scoping is a
            # client-side post-filter (overfetch x4 like the Rust MCP tools).
            hits = self._call(self._sdk.search_messages, query, limit * 4)
            f_session = (filters or {}).get("session_id")
            f_idx = (filters or {}).get("agent_idx")
            for h in hits:
                if f_session is not None and h.session_id != f_session:
                    continue
                if f_idx is not None and h.agent_idx != f_idx:
                    continue
                messages.append(h)
        # Image search: the service has no image index (the images table is
        # unwired upstream too). Nothing to return.
        return SearchResults(messages=messages[:limit], images=[])
