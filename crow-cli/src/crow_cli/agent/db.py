"""
Database schema v3 - One row = One message. Agent-centric.

No more conv_index gymnastics. No more reconstructing messages from
scattered events. Just serialize the message dict, deserialize it back.

Agents own sessions. Multiple agents can share a logical session_id.
agent_id = "{session_id}-{idx}" is the primary key.

Message shapes we actually need:
- system:   {role, content}
- user:     {role, content}
- assistant: {role, content?, reasoning_content?, tool_calls?}
- tool:     {role, tool_call_id, content}
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.dialects import sqlite
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.schema import CreateTable

Base = declarative_base()


class Prompt(Base):
    """System prompt templates - versioned, reusable"""

    __tablename__ = "prompts"

    id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    template = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    agents = relationship("Agent", back_populates="prompt")


class Agent(Base):
    """
    Agent (formerly Session) - the "DNA" of a running agent instance.

    agent_id = "{session_id}-{agent_idx}" is the PK.
    session_id is the logical parent session (for ACP upstream routing).
    """

    __tablename__ = "agents"

    agent_id = Column(Text, primary_key=True)
    session_id = Column(Text, nullable=False, index=True)
    agent_idx = Column(Integer, nullable=False, default=1)
    cwd = Column(Text, nullable=False, default="/tmp")
    prompt_id = Column(Text, ForeignKey("prompts.id"), nullable=True)
    prompt_args = Column(JSON, nullable=True)
    system_prompt = Column(Text, nullable=False)
    tool_definitions = Column(JSON, nullable=False)
    request_params = Column(JSON, nullable=False)
    model_identifier = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="active")
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    prompt = relationship("Prompt", back_populates="agents")
    messages = relationship(
        "Message", back_populates="agent", cascade="all, delete-orphan"
    )


class Message(Base):
    """
    One row = One message.

    Just store the message dict as JSON. No normalization headaches.

    Examples:
        system:   {role: "system", content: "You are..."}
        user:     {role: "user", content: "fix the bug"}
        assistant: {role: "assistant", content: "ok", reasoning_content: "...", tool_calls: [...]}
        tool:     {role: "tool", tool_call_id: "call_123", content: "result..."}
    """

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(
        Text, ForeignKey("agents.agent_id", ondelete="CASCADE"), nullable=False
    )
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    # The message itself - just dump it here
    data = Column(JSON, nullable=False)

    # Convenience columns for querying (optional, but handy)
    role = Column(Text, nullable=False, index=True)

    # Token tracking (only on assistant messages)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)

    agent = relationship("Agent", back_populates="messages")


def create_database(db_uri: str = "sqlite:///crow.db") -> None:
    """Create the session database (agents, messages, prompts)."""
    engine = create_engine(db_uri)
    Base.metadata.create_all(engine)


def view_agent_schema(model: Base) -> str:
    create_statement = CreateTable(model.__table__).compile(dialect=sqlite.dialect())
    return create_statement.__str__()


def get_schemas() -> str:
    schemas = []
    for table in [Prompt, Agent, Message]:
        schemas.append(view_agent_schema(table))
    return "\n\n".join(schemas)
