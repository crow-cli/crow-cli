"""Read-mostly accessor for the crow memory database, built on crow-memory.

crow-mcp never imports crow-cli (MCP is a runtime protocol boundary); the
shared contract is the crow-memory package — one schema, one FTS5
implementation, no drift. The db_uri resolves from: CROW_DB_URI env (URI) ->
CROW_MEMORY_DB env (path) -> config.yaml db_uri/memory_path -> default.
Search is FTS5 + bm25 (keyword).
"""

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import crow_memory as cm
from sqlalchemy import func

DEFAULT_DB = "~/.agents/crow/crow.db"
CONFIG = "~/.agents/crow/config.yaml"


def db_uri() -> str:
    if env := os.environ.get("CROW_DB_URI"):
        return cm.normalize_db_uri(env)
    if env := os.environ.get("CROW_MEMORY_DB"):
        return cm.normalize_db_uri(env)
    cfg = Path(os.path.expanduser(CONFIG))
    if cfg.exists():
        for line in cfg.read_text().splitlines():
            for key in ("db_uri:", "memory_path:"):
                if line.startswith(key):
                    return cm.normalize_db_uri(line.split(":", 1)[1].strip())
    return cm.normalize_db_uri(DEFAULT_DB)


@lru_cache(maxsize=1)
def _cached_engine(uri: str):
    return cm.get_engine(uri)


def _ro_engine():
    """Read-only engine, or None when a sqlite file doesn't exist yet."""
    uri = db_uri()
    if uri.startswith("sqlite:///"):
        path = Path(uri.removeprefix("sqlite:///"))
        if not path.exists():
            return None
        uri = f"sqlite:///file:{path}?mode=ro&uri=true"
    return _cached_engine(uri)


@dataclass
class Msg:
    id: int
    agent_id: str
    session_id: str
    agent_idx: int
    role: str
    created_at: str
    data: dict
    score: float | None = None


@dataclass
class SessionRow:
    session_id: str
    last_activity: str
    message_count: int
    agent_count: int
    agent_idxs: list[int] = field(default_factory=list)
    model_identifier: str = ""
    cwd: str = ""
    last_role: str = ""
    last_message: Msg | None = None


def _msg(row, amap: dict[str, tuple[str, int]], score: float | None = None) -> Msg:
    sid, aidx = amap.get(row.agent_id, ("", 0))
    return Msg(
        id=row.id,
        agent_id=row.agent_id,
        session_id=sid,
        agent_idx=aidx,
        role=row.role,
        created_at=row.created_at,
        data=dict(row.data),
        score=score,
    )


def list_sessions(limit: int = 50, offset: int = 0) -> list[SessionRow]:
    engine = _ro_engine()
    if engine is None:
        return []
    with cm.Session(engine) as s:
        rows = (
            s.query(
                cm.Agent.session_id,
                func.max(cm.Message.created_at),
                func.count(func.distinct(cm.Message.id)),
                func.count(func.distinct(cm.Agent.agent_id)),
            )
            .join(cm.Message, cm.Message.agent_id == cm.Agent.agent_id, isouter=True)
            .group_by(cm.Agent.session_id)
            .order_by(func.max(cm.Message.created_at).desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        agents = s.query(cm.Agent).all()
        amap = {a.agent_id: (a.session_id, a.agent_idx) for a in agents}
        out = []
        for sid, last, n_msg, n_agent in rows:
            mine = sorted((a for a in agents if a.session_id == sid), key=lambda a: a.agent_idx)
            last_row = None
            if mine:
                last_row = (
                    s.query(cm.Message)
                    .filter(cm.Message.agent_id.in_([a.agent_id for a in mine]))
                    .order_by(cm.Message.id.desc())
                    .first()
                )
            out.append(
                SessionRow(
                    session_id=sid,
                    last_activity=last or "",
                    message_count=n_msg,
                    agent_count=n_agent,
                    agent_idxs=[a.agent_idx for a in mine],
                    model_identifier=mine[0].model_identifier if mine else "",
                    cwd=mine[0].cwd if mine else "",
                    last_role=last_row.role if last_row else "",
                    last_message=_msg(last_row, amap) if last_row else None,
                )
            )
        return out


def session_records(
    session_id: str,
    agent_idx: int | None = None,
    roles: list[str] | None = None,
    after: str | None = None,
    before: str | None = None,
) -> list[Msg]:
    engine = _ro_engine()
    if engine is None:
        return []
    with cm.Session(engine) as s:
        agents = s.query(cm.Agent).filter_by(session_id=session_id).all()
    aids = [a.agent_id for a in agents if agent_idx is None or a.agent_idx == agent_idx]
    if not aids:
        return []
    amap = {a.agent_id: (a.session_id, a.agent_idx) for a in agents}
    rows = cm.query_messages(engine, aids, roles=roles, after=after, before=before)
    return [_msg(r, amap) for r in rows]


def search(query: str, limit: int = 20, agent_ids: set[str] | None = None) -> list[Msg]:
    """BM25 keyword search, best match first. Quoted tokens = implicit AND."""
    engine = _ro_engine()
    if engine is None:
        return []
    hits = cm.search_messages(engine, query, limit=limit, agent_ids=agent_ids)
    return [
        Msg(
            id=h["id"],
            agent_id=h["agent_id"],
            session_id=h["session_id"],
            agent_idx=h["agent_idx"],
            role=h["role"],
            created_at=h["created_at"],
            data=h["data"],
            score=h["score"],
        )
        for h in hits
    ]
