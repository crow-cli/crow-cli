"""Read path: agents, prompts, messages, sessions, keyword search."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import fts
from .ids import build_agent_id, parse_agent_id
from .image_store import ImageStore
from .messages import hydrate_message
from .models import Agent, Message, Prompt, SubtoolCall, Task, TaskDelivery


def get_agent(engine, agent_id: str) -> Agent | None:
    with Session(engine) as db:
        return db.query(Agent).filter_by(agent_id=agent_id).first()


def list_agents(engine, session_id: str | None = None) -> list[Agent]:
    with Session(engine) as db:
        q = db.query(Agent)
        if session_id is not None:
            q = q.filter_by(session_id=session_id)
        return q.order_by(Agent.agent_idx).all()


def agent_index(engine) -> dict[str, tuple[str, int]]:
    """agent_id -> (session_id, agent_idx) for EVERY agent, reading only
    the id columns — full Agent rows carry each agent's system prompt and
    tool definitions, which is hundreds of MB across the table."""
    with Session(engine) as db:
        rows = db.query(Agent.agent_id, Agent.session_id, Agent.agent_idx).all()
    return {a.agent_id: (a.session_id, a.agent_idx) for a in rows}


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


def delegation_tool_call_ids(
    engine, wire_id: str, tools: tuple[str, ...] = ("rlm",)
) -> set[str]:
    """The LLM tool-call ids of every in-cell delegation this session made.

    A delegation made INSIDE an execute cell does not appear in the message
    history as a call named "rlm" — the history holds one ``execute`` call
    and whatever the cell printed. What links the two is the subtool
    register: one subtool_calls row per in-cell tool call, carrying the
    PARENT execute call's ACP id. TurnCtx.tcid is ``f"{turn_id}/{llm_id}"``,
    so the last path segment is the LLM's own tool_call_id — exactly what
    the persisted assistant message carries in ``tool_calls[].id``. Matching
    on that is precise; grepping the cell's source for "rlm(" is not (it
    hits comments, strings, and this docstring).

    ``wire_id`` is a trunk's bare session_id or a fork's full agent_id; both
    are matched, because the register stores whichever the agent injected.
    """
    try:
        bare, _, _ = parse_agent_id(wire_id)
    except ValueError:
        bare = wire_id
    with Session(engine) as db:
        rows = (
            db.query(SubtoolCall.parent_tool_call_id)
            .filter(
                SubtoolCall.session_id.in_({wire_id, bare}),
                SubtoolCall.tool.in_(tools),
            )
            .all()
        )
    return {r[0].rsplit("/", 1)[-1] for r in rows if r[0]}


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


def count_tasks(engine, owner_session: str | None = None) -> int:
    """Total tasks ever launched — globally (the task-N numbering, whose
    UNIQUE constraint is global) or by one session."""
    with Session(engine) as db:
        query = db.query(Task)
        if owner_session is not None:
            query = query.filter_by(owner_session=owner_session)
        return query.count()


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
    engine, agent, hydrate: bool = False, store: ImageStore | None = None,
) -> list[dict]:
    """Message VIEW for an agent row.

    The trunk (fork_idx=1) sees its own rows. A fork sees the trunk's PREFIX
    rows (id <= forked_at) followed by its own rows — the prefix is shared,
    never copied.
    """
    session_id, agent_idx, fork_idx = parse_agent_id(agent.agent_id)
    if fork_idx == 1:
        return load_messages(engine, agent.agent_id, hydrate, store)
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
    if hydrate and store:
        msgs = [hydrate_message(m, store) for m in msgs]
    return msgs


def load_messages(
    engine, agent_id: str, hydrate: bool = False, store: ImageStore | None = None,
) -> list[dict]:
    with Session(engine) as db:
        rows = db.query(Message).filter_by(agent_id=agent_id).order_by(Message.id).all()
        msgs = [dict(r.data) for r in rows]
    if hydrate and store:
        msgs = [hydrate_message(m, store) for m in msgs]
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
        agent_q = db.query(Agent.session_id, Agent.model_identifier)
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
    roles: list[str] | None = None,
    include_forks: bool = True,
) -> list[dict]:
    """Keyword search over message text (FTS5/bm25 on sqlite,
    tsvector/ts_rank on postgres — see memory/fts.py). Returns
    {message fields + session_id/agent_idx + score} dicts, best match first.
    ``score`` is lower = better on both backends.

    Filters are pushed INTO the query (fts.search_rows joins messages and
    agents), so ``limit`` is the number of matches returned rather than the
    number of global top hits that happened to survive a Python-side filter.
    """
    with engine.connect() as conn:
        return fts.search_rows(
            conn,
            engine,
            query,
            limit,
            roles=roles,
            session_id=session_id,
            agent_idx=agent_idx,
            agent_ids=agent_ids,
            include_forks=include_forks,
        )
