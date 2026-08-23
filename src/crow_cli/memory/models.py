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
    request_params = Column(JSON, nullable=False, default=dict)
    model_identifier = Column(Text, nullable=False, default="")
    status = Column(Text, nullable=False, default="active")
    created_at = Column(Text, nullable=False, default=now_iso)


class SessionMcpServers(Base):
    """Client-defined mcpServers per session, persisted for cross-process reads.

    MCP tools (e.g. the task tool that launches delegated agents) run in a
    SEPARATE process from the ACP agent; the coupling between them is this
    table, not in-process state. The agent writes whatever mcpServers the
    client sent on session/new, session/load or fork (wire JSON dicts); the
    tool process reads them to pass through to the child's session/new.
    """

    __tablename__ = "session_mcp_servers"

    session_id = Column(Text, primary_key=True)
    servers = Column(JSON, nullable=False, default=list)
    updated_at = Column(Text, nullable=False, default=now_iso)


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
