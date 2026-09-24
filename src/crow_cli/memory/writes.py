"""Write path: messages, agents, prompts, goals."""

import uuid

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import fts
from .ids import parse_agent_id
from .image_store import ImageStore
from .messages import extract_images, message_text
from .models import (
    GOAL_ACTIVE,
    GOAL_BLOCKED,
    GOAL_BUDGET_LIMITED,
    Agent,
    Goal,
    Message,
    Prompt,
    Task,
    TaskDelivery,
    now_iso,
)
from .reads import count_tasks, get_goal


def add_message(
    engine, agent_id: str, message: dict, store: ImageStore | None = None,
    usage: dict | None = None,
) -> int:
    """Persist one message. Inline images are extracted to the store first, so
    the row carries image_ref blocks. fork_idx is derived from the agent_id
    (schema v5 three-part format). Returns the new message id."""
    _, _, fork_idx = parse_agent_id(agent_id)
    stored = extract_images(message, store) if store else message
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
        fts.insert_fts(db, engine, row.id, agent_id, row.role, fork_idx, message_text(stored))
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


def set_agent_model(engine, agent_id: str, model_identifier: str) -> None:
    """Record a model choice on an agent row that already exists.

    ``create_agent`` writes ``model_identifier`` once, at birth, and
    ``AgentSession.load`` reads it back — so without this the model a client
    picked over ``session/set_config_option`` lived exactly as long as the
    process it was picked in, and a restart resumed the session on the model
    it was BORN with. Same shape as :func:`set_agent_mcp_servers`: one column
    on one row, and the row must already exist.

    Which row is the caller's business, and it matters: a session's history is
    one row per generation, and the model belongs on the generation that is
    current, because that is the one ``get_max_agent_idx`` will resolve to
    after a restart.
    """
    with Session(engine) as db:
        row = db.query(Agent).filter_by(agent_id=agent_id).first()
        if row is None:
            raise ValueError(f"no agent row '{agent_id}' to store a model on")
        row.model_identifier = model_identifier
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
    """Register a launched task — the RUNNING state exists in the database
    from launch time, so a fast completion can never outrun the record."""
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


def launch_next_task(
    engine,
    *,
    owner_session: str,
    kind: str = "subagent",
    tool_call_id: str | None = None,
    sub_session: str | None = None,
    prompt: str = "",
    model: str | None = None,
    priority: str = "low",
) -> str:
    """Insert a running task under the next free ``task-N`` and return the id.

    The numbering is GLOBAL because the constraint is: ``task_id`` is UNIQUE
    across the database, so a per-owner counter collides the moment a second
    session launches its first task. Counting and then inserting is still a
    race — two processes can read the same count — so the retry is not
    defensive padding, it is the other half of the allocation. It also absorbs
    the gaps deleted rows leave behind.

    Two callers and no more, which is why this lives here rather than in
    either: the ``task`` subtool, and a scheduled wake. Both need the same id
    space, because both write rows the same mailbox delivers from and the same
    owner reads with the same ``task_read()``.
    """
    n = count_tasks(engine) + 1
    while True:
        task_id = f"task-{n}"
        try:
            launch_task(
                engine,
                task_id=task_id,
                owner_session=owner_session,
                kind=kind,
                tool_call_id=tool_call_id,
                sub_session=sub_session,
                prompt=prompt,
                model=model,
                priority=priority,
            )
            return task_id
        except IntegrityError:
            n += 1


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
    deliver: bool = True,
) -> bool:
    """STATE FIRST: flip the task to terminal AND land its delivery in the
    owner's mailbox, in ONE commit. Idempotent — a task already terminal
    (cancel racing completion, crash-retry) returns False and delivers
    nothing a second time.

    ``deliver=False`` closes the row without a mailbox message, for the one
    case where the owner already knows: a launch that failed synchronously
    and raised at the caller. The row still has to go terminal — a task
    left "running" is a task the owner will park on forever — but a
    delivery would tell it the same thing twice, once as the exception it
    just caught and once as a wake it did not ask for.
    """
    with Session(engine) as db:
        task = db.query(Task).filter_by(task_id=task_id).first()
        if task is None or task.status != "running":
            return False
        task.status = status
        task.result = result
        task.finished_at = now_iso()
        if deliver:
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


def queue_delivery(
    engine,
    session_id: str,
    *,
    task_id: str,
    content: str,
    priority: str = "low",
) -> int:
    """Land one row in a session's mailbox and return its id.

    The primitive underneath ``finish_task``'s delivery, exposed because a task
    is not the only thing with a reason to wake a session. A goal continuation
    is a deferred "keep going" with no task row behind it at all, and ACP_V2.md
    §5.4's state-triggered wake needs somewhere to put it. ``task_id`` has no
    foreign key, so it names whatever the wake is about — honestly, and without
    a goal having to pretend to be a task.

    Nothing is poked here, deliberately. The row is the truth and the driver's
    backstop poll reads it; a caller that wants the wake now rather than within
    ``PARK_BACKSTOP_S`` publishes its own :class:`~crow_cli.wake.Poke`. The goal
    continuation does not, because it writes the row from inside the driver that
    would receive the poke — the loop re-iterates on the row directly, which is
    §5.3's whole argument for why this never wanted a clock or a worker.
    """
    with Session(engine) as db:
        row = TaskDelivery(
            session_id=session_id,
            task_id=task_id,
            priority=priority,
            content=content,
        )
        db.add(row)
        db.commit()
        return row.id


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

    One UPDATE ... RETURNING: WHERE status='pending' plus the single atomic
    UPDATE guarantees a delivery is claimed by EXACTLY ONE consumer — on
    sqlite the whole-db write lock serializes claimers (the loop's several
    consult breakpoints, or two processes sharing the db); on postgres the
    same holds at row level, even across machines. With priority set, only
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


# -- goals --------------------------------------------------------------------
#
# The status vocabulary and the reason it is shaped that way live in
# .models, next to the row. What follows is the discipline around writing it.


def set_goal(
    engine,
    session_id: str,
    objective: str,
    *,
    token_budget: int | None = None,
) -> str:
    """Upsert this session's goal and return its fresh ``goal_id``.

    ALWAYS a fresh id and zeroed counters, with no special case for setting
    the objective that is already there. One rule rather than two, and the
    honest one: a new objective is new work, so the old work's spending must
    not budget it, and re-setting an objective is a restart gesture that would
    be a no-op if it preserved a spent budget. The fresh id is what makes the
    reset safe rather than merely intended — see :class:`.models.Goal`.
    """
    goal_id = uuid.uuid4().hex
    stamp = now_iso()
    with Session(engine) as db:
        row = db.query(Goal).filter_by(session_id=session_id).first()
        if row is None:
            row = Goal(session_id=session_id, created_at=stamp)
            db.add(row)
        row.goal_id = goal_id
        row.objective = objective
        row.status = GOAL_ACTIVE
        row.blocked_reason = None
        row.token_budget = token_budget
        row.tokens_used = 0
        row.time_used_seconds = 0
        row.turns_used = 0
        row.updated_at = stamp
        db.commit()
    return goal_id


def update_goal_status(
    engine,
    session_id: str,
    status: str,
    *,
    expected_goal_id: str | None = None,
    blocked_reason: str | None = None,
) -> bool:
    """Move the goal to ``status``. False when there is nothing to move.

    ``expected_goal_id`` is the stale-write guard, and the callers that need it
    are the automatic ones: a turn that errored five minutes ago should not
    block the goal the user set four minutes ago. A writer that read the row
    passes the id it read; a writer that is only obeying the user passes None
    and means whatever is there now.
    """
    with Session(engine) as db:
        row = db.query(Goal).filter_by(session_id=session_id).first()
        if row is None:
            return False
        if expected_goal_id is not None and row.goal_id != expected_goal_id:
            return False
        row.status = status
        row.blocked_reason = blocked_reason if status == GOAL_BLOCKED else None
        row.updated_at = now_iso()
        db.commit()
        return True


def clear_goal(engine, session_id: str) -> bool:
    """Delete the row. False when there was none — the caller says so to the
    user, and "there was nothing to clear" is a different answer than "done"."""
    with Session(engine) as db:
        row = db.query(Goal).filter_by(session_id=session_id).first()
        if row is None:
            return False
        db.delete(row)
        db.commit()
        return True


def account_goal_usage(
    engine,
    session_id: str,
    *,
    goal_id: str,
    tokens: int = 0,
    seconds: int = 0,
    turns: int = 0,
) -> Goal | None:
    """Add to the counters and enforce the budget, in ONE statement.

    The budget flip is a ``CASE`` inside the same UPDATE rather than a read,
    a compare and a write, because the alternative has a window in it: two
    turns finishing together both read under-budget, both write, and the goal
    sails past its ceiling while marked active — which is the one failure the
    ceiling exists to prevent. Here the arithmetic and the transition are the
    same atomic act, and the row that comes back is the row the database
    decided on.

    ``goal_id`` is not optional and not a filter for tidiness: an accounting
    write for a goal the user has since replaced charges nothing, which is
    correct, because the tokens were spent on work that is no longer the goal.
    Returns None when the write did not land, so a caller can tell "no goal"
    from "goal unchanged".
    """
    tokens = max(0, tokens)
    seconds = max(0, seconds)
    turns = max(0, turns)
    stamp = now_iso()
    sql = (
        "UPDATE goals SET "
        "tokens_used = tokens_used + :tokens, "
        "time_used_seconds = time_used_seconds + :seconds, "
        "turns_used = turns_used + :turns, "
        "status = CASE "
        "  WHEN status = :active AND token_budget IS NOT NULL "
        "       AND tokens_used + :tokens >= token_budget "
        "  THEN :budget_limited ELSE status END, "
        "updated_at = :stamp "
        "WHERE session_id = :sid AND goal_id = :goal_id"
    )
    with engine.begin() as conn:
        result = conn.execute(
            text(sql),
            {
                "tokens": tokens,
                "seconds": seconds,
                "turns": turns,
                "active": GOAL_ACTIVE,
                "budget_limited": GOAL_BUDGET_LIMITED,
                "stamp": stamp,
                "sid": session_id,
                "goal_id": goal_id,
            },
        )
        if result.rowcount == 0:
            return None
    return get_goal(engine, session_id)
