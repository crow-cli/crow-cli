"""Read path: agents, prompts, messages, sessions, FTS5 keyword search."""

from pathlib import Path

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from .ids import build_agent_id, parse_agent_id
from .messages import hydrate_message
from .models import Agent, Message, Prompt, Task, TaskDelivery


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


def get_session_mcp_servers(engine, wire_id: str) -> list:
    """The session's client-defined mcpServers (wire JSON dicts); [] when
    nothing was ever supplied. Cross-process read: this is how a separate
    MCP server process sees what the client gave the agent.

    Storage rides the agents table (no table of its own): the servers live
    on the row provisioned with them. wire_id is the trunk's bare
    session_id or a fork's full agent_id; the read scans that wire
    session's agent chain (newest first) and returns the most recent
    provisioning. Compaction rows carry NULL and are skipped.
    """
    try:
        session_id, _, fork_idx = parse_agent_id(wire_id)
    except ValueError:
        session_id, fork_idx = wire_id, 1
    with Session(engine) as db:
        rows = (
            db.query(Agent)
            .filter_by(session_id=session_id, fork_idx=fork_idx)
            .order_by(Agent.agent_idx.desc())
            .all()
        )
        for row in rows:
            if row.mcp_servers is not None:
                return list(row.mcp_servers)
        return []


def get_task(engine, task_id: str) -> Task | None:
    with Session(engine) as db:
        return db.query(Task).filter_by(task_id=task_id).first()


def task_by_sub_session(engine, sub_session: str) -> Task | None:
    """The task that owns a child session (latest, if several re-opened)."""
    with Session(engine) as db:
        return (
            db.query(Task)
            .filter_by(sub_session=sub_session)
            .order_by(Task.created_at.desc())
            .first()
        )


def count_tasks(engine, owner_session: str) -> int:
    """Total tasks ever launched by a session — the task-N numbering."""
    with Session(engine) as db:
        return db.query(Task).filter_by(owner_session=owner_session).count()


def running_tasks(engine, owner_session: str) -> list[Task]:
    with Session(engine) as db:
        return (
            db.query(Task)
            .filter_by(owner_session=owner_session, status="running")
            .order_by(Task.created_at)
            .all()
        )


def pending_deliveries(engine, session_id: str) -> list[TaskDelivery]:
    """The session's undelivered completions, in ARRIVAL order."""
    with Session(engine) as db:
        return (
            db.query(TaskDelivery)
            .filter_by(session_id=session_id, status="pending")
            .order_by(TaskDelivery.id)
            .all()
        )


def get_max_agent_idx(engine, session_id: str, fork_idx: int | None = 1) -> int:
    """Highest agent_idx for a session. fork_idx=1 (default) follows the
    trunk; None scans all forks."""
    with Session(engine) as db:
        q = db.query(Agent.agent_idx).filter_by(session_id=session_id)
        if fork_idx is not None:
            q = q.filter_by(fork_idx=fork_idx)
        rows = q.all()
    return max((r[0] for r in rows), default=1)


def get_max_fork_idx(engine, session_id: str, agent_idx: int) -> int:
    """Highest fork_idx for a (session_id, agent_idx) pair — 1 when only the
    trunk exists."""
    with Session(engine) as db:
        rows = (
            db.query(Agent.fork_idx)
            .filter_by(session_id=session_id, agent_idx=agent_idx)
            .all()
        )
    return max((r[0] for r in rows), default=1)


def load_agent_messages(
    engine, agent, hydrate: bool = False, images_dir: Path | None = None,
) -> list[dict]:
    """Message VIEW for an agent row.

    The trunk (fork_idx=1) sees its own rows. A fork sees the trunk's PREFIX
    rows (id <= forked_at) followed by its own rows — the prefix is shared,
    never copied.
    """
    session_id, agent_idx, fork_idx = parse_agent_id(agent.agent_id)
    if fork_idx == 1:
        return load_messages(engine, agent.agent_id, hydrate, images_dir)
    trunk_id = build_agent_id(session_id, agent_idx, 1)
    anchor = int(agent.forked_at) if agent.forked_at is not None else None
    with Session(engine) as db:
        q = db.query(Message).filter_by(agent_id=trunk_id).order_by(Message.id)
        if anchor is not None:
            q = q.filter(Message.id <= anchor)
        msgs = [dict(r.data) for r in q.all()]
        msgs += [
            dict(r.data)
            for r in db.query(Message)
            .filter_by(agent_id=agent.agent_id)
            .order_by(Message.id)
            .all()
        ]
    if hydrate and images_dir:
        msgs = [hydrate_message(m, images_dir) for m in msgs]
    return msgs


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


def list_sessions(engine, limit: int = 50, offset: int = 0, include_forks: bool = False) -> list[dict]:
    """Sessions ordered by most recent message activity (desc).

    include_forks=False (default) hides the fork dimension entirely: only
    trunk agent rows (fork_idx=1) are counted, and since fork messages are
    keyed by their fork agent_id, dropping the fork agent rows drops their
    messages from the join too.
    """
    with Session(engine) as db:
        q = db.query(
            Agent.session_id,
            func.max(Message.created_at),
            func.count(func.distinct(Message.id)),
            func.count(func.distinct(Agent.agent_id)),
        ).join(Message, Message.agent_id == Agent.agent_id, isouter=True)
        if not include_forks:
            q = q.filter(Agent.fork_idx == 1)
        rows = (
            q.group_by(Agent.session_id)
            .order_by(func.max(Message.created_at).desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        models = {}
        agent_q = db.query(Agent)
        if not include_forks:
            agent_q = agent_q.filter(Agent.fork_idx == 1)
        for a in agent_q.all():
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
            idx[a.agent_id] = (a.session_id, a.agent_idx, a.fork_idx)
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
        sid, aidx, fidx = idx.get(row.agent_id, ("", 0, 1))
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
                "fork_idx": fidx,
                "role": row.role,
                "created_at": row.created_at,
                "data": dict(row.data),
                "score": rank,
            }
        )
        if len(out) >= limit:
            break
    return out
