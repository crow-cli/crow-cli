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
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import declarative_base, relationship

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
    file_snapshots = relationship(
        "FileSnapshot", back_populates="agent", cascade="all, delete-orphan"
    )


class FileSnapshot(Base):
    """
    Pre-mutation file content captured by write/edit tool pre-hooks.

    Murder backend reads this to serve content_before to Monaco.
    Monaco handles the actual diff rendering.
    """

    __tablename__ = "file_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(
        Text,
        ForeignKey("agents.agent_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_call_id = Column(Text, nullable=False, index=True)
    tool_name = Column(Text, nullable=False)  # "write" or "edit"
    file_path = Column(Text, nullable=False)
    content_before = Column(Text, nullable=True)  # empty string if new file
    timestamp = Column(DateTime, nullable=False, default=datetime.now)

    agent = relationship("Agent", back_populates="file_snapshots")

    __table_args__ = (
        UniqueConstraint(
            "agent_id", "tool_call_id", "file_path", name="uq_agent_tool_file"
        ),
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
    """Create the database and tables."""
    engine = create_engine(db_uri)
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    create_database()
