"""session_tabs CRUD — client-side TUI tab state in the shared store.

Sync; the TUI wraps these in asyncio.to_thread. The db_uri comes from the
caller — canonically crow_cli.config's Config.db_uri, the same authority
the agent and the MCP surfaces draw from.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session as OrmSession

from crow_cli.memory.db import get_engine
from crow_cli.memory.models import SessionTab


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(tab: SessionTab) -> dict:
    return {
        "id": tab.id,
        "agent": tab.agent,
        "agent_identity": tab.agent_identity,
        "agent_session_id": tab.agent_session_id,
        "title": tab.title,
        "protocol": tab.protocol,
        "prompt_count": tab.prompt_count,
        "created_at": tab.created_at,
        "last_used": tab.last_used,
        "meta_json": tab.meta_json,
    }


def tab_new(
    db_uri: str,
    *,
    title: str,
    agent: str,
    agent_identity: str,
    agent_session_id: str,
    protocol: str = "acp",
    meta_json: str = "{}",
) -> int:
    engine = get_engine(db_uri)
    try:
        with OrmSession(engine) as s:
            tab = SessionTab(
                title=title,
                agent=agent,
                agent_identity=agent_identity,
                agent_session_id=agent_session_id,
                protocol=protocol,
                meta_json=meta_json,
            )
            s.add(tab)
            s.commit()
            return tab.id
    finally:
        engine.dispose()


def tab_get(db_uri: str, id: int) -> dict | None:
    engine = get_engine(db_uri)
    try:
        with OrmSession(engine) as s:
            tab = s.get(SessionTab, id)
            return _row(tab) if tab is not None else None
    finally:
        engine.dispose()


def tab_recent(db_uri: str, limit: int = 100) -> list[dict]:
    engine = get_engine(db_uri)
    try:
        with OrmSession(engine) as s:
            tabs = (
                s.query(SessionTab)
                .order_by(SessionTab.last_used.desc())
                .limit(limit)
                .all()
            )
            return [_row(t) for t in tabs]
    finally:
        engine.dispose()


def tab_touch(db_uri: str, id: int) -> bool:
    engine = get_engine(db_uri)
    try:
        with OrmSession(engine) as s:
            tab = s.get(SessionTab, id)
            if tab is None:
                return False
            tab.last_used = _now()
            s.commit()
            return True
    finally:
        engine.dispose()


def tab_rename(db_uri: str, id: int, title: str) -> bool:
    engine = get_engine(db_uri)
    try:
        with OrmSession(engine) as s:
            tab = s.get(SessionTab, id)
            if tab is None:
                return False
            tab.title = title
            s.commit()
            return True
    finally:
        engine.dispose()
