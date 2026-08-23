"""ORM schema — v5: one row = one message, agent-centric, fork-aware.

agent_id = "{session_id}-{agent_idx}-{fork_idx}" is the primary key;
session_id is the logical parent (multiple agents per session, multiple
forks per agent_idx). Trunk rows carry fork_idx=1; a forked agent records
its origin message id in forked_at.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import declarative_base

Base = declarative_base()


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
    """One async task (Phase 1: subagents only). Status lives in sqlite,
    not in a process — a completion is REGISTERED the moment it arrives,
    which is what makes the old delegate hang structurally impossible."""

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
