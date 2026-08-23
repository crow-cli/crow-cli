"""Write path: messages, agents, prompts."""

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from .ids import parse_agent_id
from .messages import extract_images, message_text
from .models import Agent, Message, Prompt, Task, TaskDelivery, now_iso


def add_message(
    engine, agent_id: str, message: dict, images_dir: Path | None = None,
    usage: dict | None = None,
) -> int:
    """Persist one message. Inline images are extracted to disk first, so the
    row carries image_ref blocks. fork_idx is derived from the agent_id
    (schema v5 three-part format). Returns the new message id."""
    _, _, fork_idx = parse_agent_id(agent_id)
    stored = extract_images(message, images_dir) if images_dir else message
    usage = usage or {}
    with Session(engine) as db:
        row = Message(
            agent_id=agent_id,
            fork_idx=fork_idx,
            data=stored,
            role=message.get("role", ""),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
        db.add(row)
        db.flush()
        db.execute(
            text(
                "INSERT INTO messages_fts(rowid, agent_id, role, fork_idx, text) "
                "VALUES (:r, :a, :role, :f, :t)"
            ),
            {
                "r": row.id,
                "a": agent_id,
                "role": row.role,
                "f": fork_idx,
                "t": message_text(stored),
            },
        )
        db.commit()
        return row.id


def create_agent(engine, **fields) -> None:
    with Session(engine) as db:
        db.add(Agent(**fields))
        db.commit()


def set_agent_mcp_servers(engine, agent_id: str, servers: list) -> None:
    """Store the client-defined mcpServers (wire JSON dicts) on the agent
    row that was provisioned with them — no separate table.

    An explicit [] means EXPLICITLY toolless — it overwrites, it is not
    'unknown'. The row must already exist (it is created by the same
    session/new, load or fork that carries the mcpServers).
    """
    with Session(engine) as db:
        row = db.query(Agent).filter_by(agent_id=agent_id).first()
        if row is None:
            raise ValueError(f"no agent row '{agent_id}' to store mcpServers on")
        row.mcp_servers = list(servers)
        db.commit()


def launch_task(
    engine,
    *,
    task_id: str,
    owner_session: str,
    kind: str = "subagent",
    tool_call_id: str | None = None,
    sub_session: str | None = None,
    prompt: str = "",
    model: str | None = None,
    priority: str = "low",
) -> None:
    """Register a launched task — the RUNNING state exists in sqlite from
    launch time, so a fast completion can never outrun the record."""
    with Session(engine) as db:
        db.add(
            Task(
                task_id=task_id,
                kind=kind,
                owner_session=owner_session,
                tool_call_id=tool_call_id,
                sub_session=sub_session,
                prompt=prompt,
                model=model,
                priority=priority,
            )
        )
        db.commit()


def set_task_sub_session(engine, task_id: str, sub_session: str) -> None:
    """Record the child's wire session id on the task row (after the
    driver's session/new lands)."""
    with Session(engine) as db:
        task = db.query(Task).filter_by(task_id=task_id).first()
        if task is not None:
            task.sub_session = sub_session
            db.commit()


def reopen_task(engine, task_id: str) -> bool:
    """Terminal -> running again (re-prompt of an ended/cancelled session).
    False when the task is missing or ALREADY running — callers must not
    double-launch on one task row."""
    with Session(engine) as db:
        task = db.query(Task).filter_by(task_id=task_id).first()
        if task is None or task.status == "running":
            return False
        task.status = "running"
        task.finished_at = None
        db.commit()
        return True


def finish_task(
    engine,
    task_id: str,
    *,
    result: str | None,
    status: str = "completed",
    content: str = "",
) -> bool:
    """STATE FIRST: flip the task to terminal AND land its delivery in the
    owner's mailbox, in ONE commit. Idempotent — a task already terminal
    (cancel racing completion, crash-retry) returns False and delivers
    nothing a second time."""
    with Session(engine) as db:
        task = db.query(Task).filter_by(task_id=task_id).first()
        if task is None or task.status != "running":
            return False
        task.status = status
        task.result = result
        task.finished_at = now_iso()
        db.add(
            TaskDelivery(
                session_id=task.owner_session,
                task_id=task_id,
                priority=task.priority,
                content=content,
            )
        )
        db.commit()
        return True


def cancel_task(engine, task_id: str) -> bool:
    """Flip a running task to cancelled with NO delivery — the cancel was
    a synchronous tool call by the owner, so a "was cancelled" message in
    its mailbox would just tell it what it did. Idempotent like
    finish_task: an already-terminal task returns False."""
    with Session(engine) as db:
        task = db.query(Task).filter_by(task_id=task_id).first()
        if task is None or task.status != "running":
            return False
        task.status = "cancelled"
        task.finished_at = now_iso()
        db.commit()
        return True


def mark_delivered(engine, delivery_ids: list[int]) -> None:
    with Session(engine) as db:
        rows = db.query(TaskDelivery).filter(TaskDelivery.id.in_(delivery_ids)).all()
        stamp = now_iso()
        for row in rows:
            row.status = "delivered"
            row.delivered_at = stamp
        db.commit()


def claim_deliveries(
    engine, session_id: str, priority: str | None = None
) -> list[dict]:
    """Atomically drain the mailbox, claiming each row EXACTLY ONCE.

    One UPDATE ... RETURNING: sqlite's write lock serializes concurrent
    claimers (the in-loop consult vs the quiescent watcher, or two
    processes sharing the db), and WHERE status='pending' guarantees a
    delivery is injected by exactly one of them. With priority set, only
    matching rows are claimed (the mid-turn breakpoint takes highs and
    leaves lows pending for end of turn). Returns dicts in arrival order.
    """
    sql = (
        "UPDATE task_deliveries "
        "SET status = 'delivered', delivered_at = :stamp "
        "WHERE session_id = :sid AND status = 'pending'"
    )
    params: dict = {"stamp": now_iso(), "sid": session_id}
    if priority is not None:
        sql += " AND priority = :priority"
        params["priority"] = priority
    sql += " RETURNING id, task_id, priority, content"
    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    claimed = [dict(r._mapping) for r in rows]
    claimed.sort(key=lambda d: d["id"])
    return claimed


def lookup_or_create_prompt(engine, template: str, name: str = "crow-default") -> str:
    from coolname import generate_slug

    with Session(engine) as db:
        existing = db.query(Prompt).filter_by(template=template).first()
        if existing:
            return existing.id
        prompt_id = generate_slug(4)
        db.add(Prompt(id=prompt_id, name=name, template=template))
        db.commit()
        return prompt_id
