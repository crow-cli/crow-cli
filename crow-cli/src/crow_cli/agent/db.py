"""
Database schema v2 - One row = One message.

No more conv_index gymnastics. No more reconstructing messages from
scattered events. Just serialize the message dict, deserialize it back.

Message shapes we actually need:
- system:   {role, content}
- user:     {role, content}
- assistant: {role, content?, reasoning_content?, tool_calls?}
- tool:     {role, tool_call_id, content}
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, create_engine
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

    sessions = relationship("Session", back_populates="prompt")


class Session(Base):
    """
    Session metadata - the "DNA" of the conversation.

    Stores config, but NOT the messages themselves.
    Messages live in the Message table.
    """

    __tablename__ = "sessions"

    session_id = Column(Text, primary_key=True)
    prompt_id = Column(Text, ForeignKey("prompts.id"), nullable=True)
    prompt_args = Column(JSON, nullable=True)
    system_prompt = Column(Text, nullable=False)
    tool_definitions = Column(JSON, nullable=False)
    request_params = Column(JSON, nullable=False)
    model_identifier = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    prompt = relationship("Prompt", back_populates="sessions")
    messages = relationship(
        "Message", back_populates="session", cascade="all, delete-orphan"
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
    session_id = Column(
        Text, ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False
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

    session = relationship("Session", back_populates="messages")


def create_database(db_path: str = "sqlite:///crow.db") -> None:
    """Create the database and tables."""
    engine = create_engine(db_path)
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    create_database()
