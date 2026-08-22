"""Read path: agents, prompts, messages, sessions, FTS5 keyword search."""

from pathlib import Path

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from .messages import hydrate_message
from .models import Agent, Message, Prompt


def get_agent(engine, agent_id: str) -> Agent | None:
    with Session(engine) as db:
        return db.query(Agent).filter_by(agent_id=agent_id).first()


def list_agents(engine, session_id: str | None = None) -> list[Agent]:
    with Session(engine) as db:
        q = db.query(Agent)
        if session_id is not None:
            q = q.filter_by(session_id=session_id)
        return q.order_by(Agent.agent_idx).all()


def get_prompt(engine, prompt_id: str) -> Prompt | None:
    with Session(engine) as db:
        return db.query(Prompt).filter_by(id=prompt_id).first()


def get_max_agent_idx(engine, session_id: str) -> int:
    with Session(engine) as db:
        rows = db.query(Agent.agent_idx).filter_by(session_id=session_id).all()
    return max((r[0] for r in rows), default=1)


def load_messages(
    engine, agent_id: str, hydrate: bool = False, images_dir: Path | None = None,
) -> list[dict]:
    with Session(engine) as db:
        rows = db.query(Message).filter_by(agent_id=agent_id).order_by(Message.id).all()
        msgs = [dict(r.data) for r in rows]
    if hydrate and images_dir:
        msgs = [hydrate_message(m, images_dir) for m in msgs]
    return msgs


def query_messages(
    engine,
    agent_ids: list[str],
    roles: list[str] | None = None,
    after: str | None = None,
    before: str | None = None,
    order: str = "asc",
    limit: int = 1_000_000,
    offset: int = 0,
) -> list[Message]:
    with Session(engine) as db:
        q = db.query(Message).filter(Message.agent_id.in_(agent_ids))
        if roles is not None:
            q = q.filter(Message.role.in_(roles))
        if after is not None:
            q = q.filter(Message.created_at > after)
        if before is not None:
            q = q.filter(Message.created_at < before)
        q = q.order_by(Message.id.asc() if order == "asc" else Message.id.desc())
        return q.offset(offset).limit(limit).all()


def list_sessions(engine, limit: int = 50, offset: int = 0) -> list[dict]:
    """Sessions ordered by most recent message activity (desc)."""
    with Session(engine) as db:
        rows = (
            db.query(
                Agent.session_id,
                func.max(Message.created_at),
                func.count(func.distinct(Message.id)),
                func.count(func.distinct(Agent.agent_id)),
            )
            .join(Message, Message.agent_id == Agent.agent_id, isouter=True)
            .group_by(Agent.session_id)
            .order_by(func.max(Message.created_at).desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        models = {}
        for a in db.query(Agent).all():
            models.setdefault(a.session_id, a.model_identifier)
    return [
        {
            "session_id": sid,
            "last_activity": last or "",
            "message_count": n_msg,
            "agent_count": n_agent,
            "model_identifier": models.get(sid, ""),
        }
        for sid, last, n_msg, n_agent in rows
    ]


def search_messages(
    engine,
    query: str,
    limit: int = 20,
    session_id: str | None = None,
    agent_idx: int | None = None,
    agent_ids: set[str] | None = None,
) -> list[dict]:
    """BM25 keyword search over message text (SQLite FTS5). Returns
    {message fields + session_id/agent_idx + score} dicts, best match first.
    ``score`` is the raw bm25 rank (lower = better)."""
    idx = {}
    with Session(engine) as db:
        for a in db.query(Agent).all():
            idx[a.agent_id] = (a.session_id, a.agent_idx)
    # Quote each token so arbitrary user input stays a valid FTS5 query
    # (implicit AND of phrases).
    match = " ".join(f'"{t}"' for t in query.split() if t)
    if not match:
        return []
    with engine.connect() as conn:
        hits = conn.execute(
            text(
                "SELECT rowid, bm25(messages_fts) AS rank FROM messages_fts "
                "WHERE messages_fts MATCH :q ORDER BY rank LIMIT :lim"
            ),
            {"q": match, "lim": limit * 4},
        ).fetchall()
    with Session(engine) as db:
        rows = db.query(Message).filter(Message.id.in_([h[0] for h in hits])).all()
    by_id = {r.id: r for r in rows}
    out = []
    for rid, rank in hits:
        row = by_id.get(rid)
        if row is None:
            continue
        sid, aidx = idx.get(row.agent_id, ("", 0))
        if session_id is not None and sid != session_id:
            continue
        if agent_idx is not None and aidx != agent_idx:
            continue
        if agent_ids is not None and row.agent_id not in agent_ids:
            continue
        out.append(
            {
                "id": row.id,
                "agent_id": row.agent_id,
                "session_id": sid,
                "agent_idx": aidx,
                "role": row.role,
                "created_at": row.created_at,
                "data": dict(row.data),
                "score": rank,
            }
        )
        if len(out) >= limit:
            break
    return out
