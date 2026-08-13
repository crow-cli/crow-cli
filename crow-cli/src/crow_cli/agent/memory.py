"""Memory layer for crow-cli — SQL via crow-memory, images on disk.

The store contract lives in the ``crow-memory`` package (schema v4): this
class only resolves the db_uri from config and wraps the sync helpers in the
async shape session.py / main.py expect. One wrinkle: image blobs never
enter the database. Writes extract inline base64 blocks to
``<db parent>/images/<sha256hex><ext>`` and store ``image_ref`` blocks;
loads with ``hydrate=True`` swap refs back to base64 data URLs for the LLM.

Search is SQLite FTS5 + bm25 (keyword). No embeddings, no HTTP service.

The async interface is preserved so session.py / main.py keep their shape;
sqlite I/O is local and millisecond-fast, so the async methods simply call the
sync db helpers.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import crow_memory as db
from crow_cli.agent.configure import Config

log = logging.getLogger(__name__)

#: Legacy sentinel — call sites pass it positionally; the db lives in config_dir.
DEFAULT_MEMORY_PATH = "~/.agents/crow/crow.db"

_FETCH_ALL = 1_000_000


class MemoryServiceError(Exception):
    """Raised when a memory operation fails (e.g. agent not found)."""

    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"memory error {status}: {detail}")


# ---- records -----------------------------------------------------------------


@dataclass
class AgentRecord:
    agent_id: str
    session_id: str
    agent_idx: int
    cwd: str = "/tmp"
    prompt_id: str | None = None
    prompt_args: dict | None = None
    system_prompt: str = ""
    tool_definitions: list = field(default_factory=list)
    request_params: dict = field(default_factory=dict)
    model_identifier: str = ""
    status: str = "active"
    created_at: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "AgentRecord":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class MessageRecord:
    id: int
    agent_id: str
    session_id: str
    agent_idx: int
    role: str
    created_at: str
    data: dict


@dataclass
class PromptRecord:
    id: str
    name: str
    template: str
    created_at: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "PromptRecord":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class SessionInfo:
    session_id: str
    last_activity: str
    message_count: int
    agent_count: int
    model_identifier: str = ""

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "last_activity": self.last_activity,
            "message_count": self.message_count,
            "agent_count": self.agent_count,
            "model_identifier": self.model_identifier,
        }


@dataclass
class SearchResults:
    messages: list[MessageRecord]
    images: list = field(default_factory=list)


def _agent_record(a: db.Agent) -> AgentRecord:
    return AgentRecord(
        agent_id=a.agent_id,
        session_id=a.session_id,
        agent_idx=a.agent_idx,
        cwd=a.cwd,
        prompt_id=a.prompt_id,
        prompt_args=a.prompt_args,
        system_prompt=a.system_prompt,
        tool_definitions=a.tool_definitions or [],
        request_params=a.request_params or {},
        model_identifier=a.model_identifier,
        status=a.status,
        created_at=a.created_at,
    )


class MemoryClient:
    """crow-memory-backed store. `path` overrides the configured db_uri."""

    def __init__(self, path: str | None = None, config_dir: Path | None = None, **_kwargs):
        cfg = Config.load(config_dir)
        # DEFAULT_MEMORY_PATH is the legacy positional sentinel — it means
        # "whatever the config says", not a literal override.
        override = None if path in (None, DEFAULT_MEMORY_PATH) else path
        self.db_uri = db.normalize_db_uri(override or cfg.db_uri)
        if self.db_uri.startswith("sqlite:///"):
            db_path = Path(self.db_uri.removeprefix("sqlite:///"))
            if db_path.is_dir():
                raise MemoryServiceError(
                    500,
                    f"{db_path} is a directory (leftover lance dataset from the old "
                    "crow-memory service) — remove it so sqlite can own this path",
                )
            self.images_dir = db_path.parent / "images"
        else:
            # Non-file backends (e.g. postgres): images stay beside the config.
            self.images_dir = cfg.config_dir / "images"
        db.create_database(self.db_uri)
        self._engine = db.get_engine(self.db_uri)

    async def close(self):
        self._engine.dispose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    # ---- agents ----

    async def create_agent(
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
        db.create_agent(
            self._engine,
            agent_id=agent_id,
            session_id=session_id,
            agent_idx=agent_idx,
            cwd=cwd,
            prompt_id=prompt_id,
            prompt_args=prompt_args or {},
            system_prompt=system_prompt,
            tool_definitions=tool_definitions or [],
            request_params=request_params or {},
            model_identifier=model_identifier,
        )
        for m in initial_messages or []:
            if m.get("role") != "system":
                await self.add_message(agent_id, m)
        agent = db.get_agent(self._engine, agent_id)
        if agent is None:
            raise MemoryServiceError(500, f"agent '{agent_id}' vanished after create")
        return _agent_record(agent)

    async def load(self, agent_id: str, hydrate: bool = False) -> tuple[AgentRecord, list[dict]]:
        agent = db.get_agent(self._engine, agent_id)
        if agent is None:
            raise MemoryServiceError(404, f"agent '{agent_id}' not found")
        messages = db.load_messages(
            self._engine, agent_id, hydrate=hydrate, images_dir=self.images_dir
        )
        return _agent_record(agent), messages

    async def list_agents(self, session_id: str | None = None) -> list[AgentRecord]:
        return [_agent_record(a) for a in db.list_agents(self._engine, session_id)]

    # ---- messages ----

    async def add_message(self, agent_id: str, message: dict, usage: dict | None = None) -> int:
        return db.add_message(
            self._engine, agent_id, message, images_dir=self.images_dir, usage=usage
        )

    async def save_messages(self, agent_id: str, messages: list[dict]) -> list[int]:
        return [await self.add_message(agent_id, m) for m in messages]

    async def query_messages(
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
            agent_ids = [a.agent_id for a in db.list_agents(self._engine, session_id)]
        else:
            raise MemoryServiceError(400, "query_messages needs session_id or agent_id")
        idx = {a.agent_id: (a.session_id, a.agent_idx) for a in db.list_agents(self._engine)}
        recs = []
        for row in db.query_messages(
            self._engine,
            agent_ids,
            roles=roles,
            after=after,
            before=before,
            order=order,
            limit=limit,
            offset=offset,
        ):
            sid, aidx = idx.get(row.agent_id, ("", 0))
            if agent_idx is not None and aidx != agent_idx:
                continue
            recs.append(
                MessageRecord(
                    id=row.id,
                    agent_id=row.agent_id,
                    session_id=sid,
                    agent_idx=aidx,
                    role=row.role,
                    created_at=row.created_at,
                    data=dict(row.data),
                )
            )
        return recs

    # ---- sessions ----

    async def get_max_agent_idx(self, session_id: str) -> int:
        return db.get_max_agent_idx(self._engine, session_id)

    async def list_sessions(self, limit: int = 50, offset: int = 0) -> list[SessionInfo]:
        return [
            SessionInfo(
                session_id=s["session_id"],
                last_activity=s["last_activity"],
                message_count=s["message_count"],
                agent_count=s["agent_count"],
                model_identifier=s["model_identifier"],
            )
            for s in db.list_sessions(self._engine, limit, offset)
        ]

    # ---- prompts ----

    async def lookup_or_create_prompt(self, template: str, name: str = "crow-default") -> str:
        return db.lookup_or_create_prompt(self._engine, template, name)

    async def get_prompt(self, prompt_id: str) -> PromptRecord:
        p = db.get_prompt(self._engine, prompt_id)
        if p is None:
            raise MemoryServiceError(404, f"prompt '{prompt_id}' not found")
        return PromptRecord(id=p.id, name=p.name, template=p.template, created_at=p.created_at)

    # ---- search ----

    async def search(
        self,
        query: str | None = None,
        modality: str = "text",
        filters: dict | None = None,
        limit: int = 10,
        query_image: bytes | None = None,
    ) -> SearchResults:
        if not query or modality not in ("text", "both"):
            return SearchResults(messages=[])
        hits = db.search_messages(
            self._engine,
            query,
            limit=limit,
            session_id=(filters or {}).get("session_id"),
            agent_idx=(filters or {}).get("agent_idx"),
        )
        return SearchResults(
            messages=[
                MessageRecord(
                    id=h["id"],
                    agent_id=h["agent_id"],
                    session_id=h["session_id"],
                    agent_idx=h["agent_idx"],
                    role=h["role"],
                    created_at=h["created_at"],
                    data=h["data"],
                )
                for h in hits
            ]
        )
