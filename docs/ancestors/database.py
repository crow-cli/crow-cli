"""
Database schema for MCP Testing - Local LLM first persistence layer.

This module defines SQLAlchemy models for:
1. SESSIONS table - The "DNA" of the agent (KV cache anchor)
2. EVENTS table - The "Wide" transcript (all conversation turns)
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    create_engine,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Session(Base):
    """
    The "DNA" of the agent. This table anchors your KV cache.
    If a row exists with a specific hash, your local engine can skip the prefill.
    """

    __tablename__ = "sessions"

    session_id = Column(
        Text, primary_key=True, doc="Unique hash of system_prompt + tools"
    )
    system_prompt = Column(
        Text, nullable=False, doc="The static instructions (The 'Crow' persona)"
    )
    tool_definitions = Column(
        JSON, nullable=False, doc="Full JSON schemas of all available MCP tools"
    )
    request_params = Column(
        JSON, nullable=False, doc="temperature, top_p, max_tokens, etc."
    )
    model_identifier = Column(
        Text,
        nullable=False,
        doc="Exact model version (e.g., 'glm-4.7' or 'llama-3-70b')",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        doc="When this agent configuration was first used",
    )

    # Relationship to events
    events = relationship(
        "Event", back_populates="session", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Session(session_id='{self.session_id}', model='{self.model_identifier}')>"


class Event(Base):
    """
    The "Wide" transcript. Every row is a single turn.
    Captures thinking, speaking, and acting without needing to join multiple tables.
    """

    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True, doc="Unique event ID")
    session_id = Column(
        Text,
        ForeignKey("sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        doc="Links back to static session config",
    )
    conv_index = Column(Integer, nullable=False, doc="Linear order of the conversation")
    timestamp = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        doc="Precise timing for latency and log-order analysis",
    )
    role = Column(
        Text, nullable=False, doc="user, assistant, tool, or custom tool_assistant"
    )
    content = Column(
        Text, nullable=True, doc="User: input; Assistant: verbal; Tool: JSON result"
    )
    reasoning_content = Column(
        Text, nullable=True, doc="Internal 'Thinking' tokens (hidden from user)"
    )
    tool_call_id = Column(
        Text, nullable=True, doc="Unique ID linking Assistant's intent to Tool's result"
    )
    tool_call_name = Column(
        Text, nullable=True, doc="Name of the function being executed"
    )
    tool_arguments = Column(
        JSON, nullable=True, doc="Arguments the model generated for the tool"
    )
    prompt_tokens = Column(
        Integer, nullable=True, doc="Input token count from API usage"
    )
    completion_tokens = Column(
        Integer, nullable=True, doc="Output token count from API usage"
    )
    total_tokens = Column(
        Integer, nullable=True, doc="Total token count from API usage"
    )
    event_metadata = Column(
        JSON, nullable=True, doc="Finish reasons, local GPU stats, or other metadata"
    )

    # Relationship to session
    session = relationship("Session", back_populates="events")

    def __repr__(self) -> str:
        return f"<Event(id={self.id}, session_id='{self.session_id}', role='{self.role}', conv_index={self.conv_index})>"


def create_database(db_path: str = "sqlite:///mcp_testing.db") -> None:
    """
    Create the database and tables.

    Args:
        db_path: Database connection string (default: SQLite in current directory)
    """
    engine = create_engine(db_path)
    Base.metadata.create_all(engine)
    print(f"Database created successfully at {db_path}")


def get_session(db_path: str = "sqlite:///mcp_testing.db"):
    """
    Get a new database session.

    Args:
        db_path: Database connection string

    Returns:
        SQLAlchemy session object
    """
    from sqlalchemy.orm import Session as SQLAlchemySession

    engine = create_engine(db_path)
    return SQLAlchemySession(engine)


def save_event(
    session,
    session_id: str,
    conv_index: int,
    role: str,
    content: str | None = None,
    reasoning_content: str | None = None,
    tool_call_id: str | None = None,
    tool_call_name: str | None = None,
    tool_arguments: dict | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    event_metadata: dict | None = None,
):
    """
    Save an event to the database.

    Args:
        session: SQLAlchemy session
        session_id: ID of the session
        conv_index: Conversation turn index
        role: user, assistant, tool
        content: Text content
        reasoning_content: Internal thinking tokens
        tool_call_id: Tool call ID
        tool_call_name: Name of tool called
        tool_arguments: Arguments passed to tool
        prompt_tokens: Input token count
        completion_tokens: Output token count
        total_tokens: Total token count
        event_metadata: Additional metadata as dict
    """
    event = Event(
        session_id=session_id,
        conv_index=conv_index,
        role=role,
        content=content,
        reasoning_content=reasoning_content,
        tool_call_id=tool_call_id,
        tool_call_name=tool_call_name,
        tool_arguments=tool_arguments,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        event_metadata=event_metadata,
    )
    session.add(event)
    session.commit()


if __name__ == "__main__":
    create_database()
