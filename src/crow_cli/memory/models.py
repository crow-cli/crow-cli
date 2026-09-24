"""ORM schema — v5: one row = one message, agent-centric, fork-aware.

agent_id = "{session_id}-{agent_idx}-{fork_idx}" is the primary key;
session_id is the logical parent (multiple agents per session, multiple
forks per agent_idx). Trunk rows carry fork_idx=1; a forked agent records
its origin message id in forked_at.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, Integer, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# -- goal statuses -----------------------------------------------------------
#
# Free text on the row, the way Task.status is, and for the same reason: a new
# way of stopping costs no migration, and a reader that has never heard of one
# still renders the goal. Only GOAL_ACTIVE continues. The others differ in WHO
# decided — "complete" and "blocked" are the model's claim, "paused" the
# user's, "budget_limited" the arithmetic's. Keeping the last separate from
# "complete" is the point: a goal that ran out of budget is not a goal that was
# achieved, and a summary that cannot tell them apart is not a summary.
#
# These live here rather than in writes.py because reads.py needs them too and
# writes.py imports reads — a constant either module may not reach is a
# constant one of them will hardcode.

GOAL_ACTIVE = "active"
GOAL_PAUSED = "paused"
GOAL_BLOCKED = "blocked"
GOAL_BUDGET_LIMITED = "budget_limited"
GOAL_COMPLETE = "complete"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Prompt(Base):
    """System prompt templates - versioned, reusable."""

    __tablename__ = "prompts"

    id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    template = Column(Text, nullable=False)
    created_at = Column(Text, nullable=False, default=now_iso)


class Agent(Base):
    """A running agent instance. agent_id = "{session_id}-{agent_idx}-{fork_idx}"
    is the PK; fork_idx=1 is the trunk, forked_at anchors a fork to the
    message id it branched from."""

    __tablename__ = "agents"

    agent_id = Column(Text, primary_key=True)
    session_id = Column(Text, nullable=False, index=True)
    agent_idx = Column(Integer, nullable=False, default=1)
    fork_idx = Column(Integer, nullable=False, default=1)
    forked_at = Column(Text, nullable=True)
    cwd = Column(Text, nullable=False, default="/tmp")
    prompt_id = Column(Text, nullable=True)
    prompt_args = Column(JSON, nullable=True)
    system_prompt = Column(Text, nullable=False, default="")
    tool_definitions = Column(JSON, nullable=False, default=list)
    # Client-defined mcpServers (wire JSON dicts) for the session this agent
    # belongs to, stored on the row that was provisioned with them.
    # Cross-process coupling: a separate MCP server process (e.g. the task
    # tool) reads them to pass through to a subagent's session/new.
    # NULL = never supplied; [] = EXPLICITLY toolless.
    mcp_servers = Column(JSON, nullable=True)
    request_params = Column(JSON, nullable=False, default=dict)
    model_identifier = Column(Text, nullable=False, default="")
    status = Column(Text, nullable=False, default="active")
    created_at = Column(Text, nullable=False, default=now_iso)


class Task(Base):
    """One async task (Phase 1: subagents only). Status lives in the
    database, not in a process — a completion is REGISTERED the moment it
    arrives, which is what makes the old delegate hang structurally
    impossible."""

    __tablename__ = "tasks"

    task_id = Column(Text, primary_key=True)
    kind = Column(Text, nullable=False, default="subagent")
    owner_session = Column(Text, nullable=False, index=True)  # wire id
    tool_call_id = Column(Text, nullable=True)
    sub_session = Column(Text, nullable=True, index=True)  # child wire id
    prompt = Column(Text, nullable=False, default="")
    model = Column(Text, nullable=True)
    priority = Column(Text, nullable=False, default="low")  # high | low
    status = Column(Text, nullable=False, default="running")
    result = Column(Text, nullable=True)
    created_at = Column(Text, nullable=False, default=now_iso)
    finished_at = Column(Text, nullable=True)


class TaskDelivery(Base):
    """Durable mailbox: completions land here THE MOMENT they arrive
    (inserted in the SAME commit as the task's status flip). The agent
    process drains it — at end-turn (held lows), on prompt start (idle
    arrivals), or as cancel->prompt (high priority). Survives process
    death."""

    __tablename__ = "task_deliveries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Text, nullable=False, index=True)  # owner mailbox
    task_id = Column(Text, nullable=False, index=True)
    priority = Column(Text, nullable=False, default="low")
    content = Column(Text, nullable=False)  # the synthetic message text
    status = Column(Text, nullable=False, default="pending")  # pending|delivered
    created_at = Column(Text, nullable=False, default=now_iso)
    delivered_at = Column(Text, nullable=True)


class Goal(Base):
    """One persisted objective per wire session, and the reason a turn ending
    is not the end.

    Keyed by ``session_id`` — the WIRE id — for the reason ``agent/slash.py``
    states: ``agent_id`` names a generation and changes under compaction, so
    anything keyed by it is silently orphaned the first time the session
    compacts. A goal is exactly the thing that has to survive compaction;
    that is most of what makes it worth having.

    One row per session, not a history. A goal that is replaced is gone — the
    objective, the counters and the status all reset together, because a
    counter that outlives the objective it measured would budget the new work
    with the old work's spending. ``goal_id`` is what makes that safe: it is
    minted fresh on every set, and a writer that carries the id it read is
    telling the truth about which goal it means. An accounting write from a
    turn that was already running when the user replaced the goal carries the
    OLD id, loses the compare, and charges nothing to the new one. Without it
    the two are indistinguishable and the new goal inherits a spent budget.

    ``status`` is the whole mechanism. Only ``active`` continues; every other
    value is a way of stopping, and the driver asks this column rather than
    asking the model. ``turns_used`` counts continuations, not user turns, and
    exists because a goal with no ceiling is a token fire — the model decides
    when it is done, and "done" is a claim the loop must be able to refuse.
    """

    __tablename__ = "goals"

    session_id = Column(Text, primary_key=True)  # wire id
    goal_id = Column(Text, nullable=False, index=True)
    objective = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="active")
    blocked_reason = Column(Text, nullable=True)
    token_budget = Column(Integer, nullable=True)
    tokens_used = Column(Integer, nullable=False, default=0)
    time_used_seconds = Column(Integer, nullable=False, default=0)
    turns_used = Column(Integer, nullable=False, default=0)
    created_at = Column(Text, nullable=False, default=now_iso)
    updated_at = Column(Text, nullable=False, default=now_iso)


class SessionTab(Base):
    """Client-side tab state for a TUI session (title, resume meta).

    The server-side session record lives on Agent (agents.session_id);
    this table is what the TUI's tab bar and resume modal need, kept in
    the shared store so the package has one state database."""

    __tablename__ = "session_tabs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent = Column(Text, nullable=False)
    agent_identity = Column(Text, nullable=False)
    agent_session_id = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    protocol = Column(Text, nullable=False, default="acp")
    prompt_count = Column(Integer, nullable=False, default=0)
    created_at = Column(Text, nullable=False, default=now_iso)
    last_used = Column(Text, nullable=False, default=now_iso)
    meta_json = Column(Text, nullable=False, default="{}")


class Message(Base):
    """One row = One message; the message dict serialized into `data`."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Text, nullable=False, index=True)
    fork_idx = Column(Integer, nullable=False, default=1)
    created_at = Column(Text, nullable=False, default=now_iso)
    data = Column(JSON, nullable=False)
    role = Column(Text, nullable=False, index=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)


class SubtoolCall(Base):
    """One tool call made inside an execute cell — a subtool of the omni-tool.

    Written through from the in-kernel register (crow_cli.tools.register) at
    call time; the server-side drain (agent/tools.py _emit_subtool_calls)
    selects unemitted rows by parent_tool_call_id, renders acp_payload into
    sibling ACP tool calls, and flips emitted. The table is the queue: rows
    survive a wedged kernel. Heavy bytes (images) never land here — they go
    to the ImageStore by content-addressed key and llm_images holds refs.
    """

    __tablename__ = "subtool_calls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Text, nullable=True, index=True)
    agent_id = Column(Text, nullable=True)
    parent_tool_call_id = Column(Text, nullable=True, index=True)
    cell_seq = Column(Integer, nullable=True)
    tool = Column(Text, nullable=False)
    mode = Column(Text, nullable=True)
    args = Column(JSON, nullable=False, default=dict)
    status = Column(Text, nullable=False)  # completed | failed
    result_kind = Column(Text, nullable=False, default="text")  # diff|image|text|error
    acp_payload = Column(JSON, nullable=True)
    llm_images = Column(JSON, nullable=False, default=list)  # ImageStore refs
    error = Column(Text, nullable=True)
    emitted = Column(Integer, nullable=False, default=0)
    created_at = Column(Text, nullable=False, default=now_iso)
