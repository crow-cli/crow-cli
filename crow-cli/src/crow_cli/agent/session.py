"""
Session management - persistence layer for conversation state.

One row = One message. No conv_index gymnastics. No reconstruction headaches.
Just serialize the message dict, deserialize it back.
"""

from typing import Any
from uuid import uuid4

from coolname import generate_slug
from crow_cli.agent.db import Base, Message, Prompt, create_database
from crow_cli.agent.db import Session as SessionModel
from crow_cli.agent.prompt import render_template
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SQLAlchemySession


def get_coolname() -> str:
    """Generate a memorable slug with UUID suffix."""
    return "-".join((generate_slug(4), uuid4().hex[:6]))


def lookup_or_create_prompt(
    template: str,
    name: str,
    db_path: str = "sqlite:///crow.db",
) -> str:
    """
    Lookup existing prompt by template content, or create new one if not found.
    """
    # Ensure database tables exist
    create_database(db_path)

    db = SQLAlchemySession(create_engine(db_path))
    try:
        existing = db.query(Prompt).filter_by(template=template).first()
        if existing:
            return existing.id

        prompt_id = get_coolname()
        new_prompt = Prompt(id=prompt_id, name=name, template=template)
        db.add(new_prompt)
        db.commit()
        return prompt_id
    finally:
        db.close()


class Session:
    """
    Manages conversation state and persistence.

    Simple model: messages live in memory as list[dict],
    persisted to db as one row per message.
    """

    def __init__(
        self,
        session_id: str,
        db_path: str = "sqlite:///crow.db",
        cwd: str = "/tmp",
    ):
        self.session_id = session_id
        self.db_path = db_path
        self.cwd = cwd
        self.messages: list[dict] = []
        self._db = None
        self._model = None
        self.model_identifier = None

    @property
    def db(self) -> SQLAlchemySession:
        """Lazy-load database connection"""
        if self._db is None:
            engine = create_engine(self.db_path)
            self._db = SQLAlchemySession(engine)
        return self._db

    @property
    def model(self) -> SessionModel:
        """Lazy-load session model from database"""
        if self._model is None:
            self._model = (
                self.db.query(SessionModel)
                .filter_by(session_id=self.session_id)
                .first()
            )
        return self._model

    def add_message(self, msg: dict):
        """
        Add message to in-memory list AND persist to database.

        Args:
            msg: Full message dict (role, content, tool_calls, etc.)
        """
        self.messages.append(msg)

        # Persist - one row = one message
        db_msg = Message(
            session_id=self.session_id,
            data=msg,
            role=msg.get("role", "unknown"),
        )
        self.db.add(db_msg)
        self.db.commit()

    def add_assistant_response(
        self,
        thinking: list[str],
        content: list[str],
        tool_call_inputs: list[dict],
        tool_results: list[dict],
        usage: dict | None = None,
    ):
        """
        Handle complex assistant message building + tool calls + results.

        Args:
            thinking: List of thinking tokens
            content: List of content tokens
            tool_call_inputs: Tool calls from assistant
            tool_results: Results from tool execution
            usage: Token usage dict
        """
        # Build assistant message
        assistant_msg = {"role": "assistant"}
        thinking_text = "".join(thinking) if thinking else None
        content_text = "".join(content) if content else None

        if thinking_text:
            assistant_msg["reasoning_content"] = thinking_text
        if content_text:
            assistant_msg["content"] = content_text

        # Add assistant message (with or without tool_calls)
        if tool_call_inputs:
            assistant_msg["tool_calls"] = tool_call_inputs

        if len(assistant_msg) > 1:  # More than just role
            self.add_message(assistant_msg)

        # Add tool results
        for tool_result in tool_results:
            self.add_message(tool_result)

    def _save_messages(self, messages: list[dict]):
        """Batch save messages to database."""
        for msg in messages:
            db_msg = Message(
                session_id=self.session_id,
                data=msg,
                role=msg.get("role", "unknown"),
            )
            self.db.add(db_msg)
        self.db.commit()

    @classmethod
    def create(
        cls,
        prompt_id: str,
        prompt_args: dict[str, Any],
        tool_definitions: list[dict],
        request_params: dict[str, Any],
        model_identifier: str,
        db_path: str = "sqlite:///crow.db",
        cwd: str = "/tmp",
        initial_messages: list[dict[str, Any]] | None = None,
    ) -> "Session":
        """Factory method to create a new session."""
        db = SQLAlchemySession(create_engine(db_path))

        # Load and render prompt
        prompt = db.query(Prompt).filter_by(id=prompt_id).first()
        if not prompt:
            db.close()
            raise ValueError(f"Prompt '{prompt_id}' not found")

        system_prompt = render_template(prompt.template, **prompt_args)
        session_id = get_coolname()

        # Create session record
        session_model = SessionModel(
            session_id=session_id,
            prompt_id=prompt_id,
            prompt_args=prompt_args,
            system_prompt=system_prompt,
            tool_definitions=tool_definitions,
            request_params=request_params,
            model_identifier=model_identifier,
        )
        db.add(session_model)
        db.commit()
        db.close()

        # Build session instance
        session = cls(session_id, db_path, cwd=cwd)
        session.model_identifier = model_identifier
        session.tools = tool_definitions
        session.request_params = request_params
        session.prompt_id = prompt_id
        session.prompt_args = prompt_args

        # Start with system message
        session.messages = [{"role": "system", "content": system_prompt}]
        session._save_messages(session.messages)

        # Add initial messages if provided
        if initial_messages:
            for msg in initial_messages:
                if msg.get("role") != "system":  # Skip system messages
                    session.add_message(msg)

        return session

    @classmethod
    def load(cls, session_id: str, db_path: str = "sqlite:///crow.db") -> "Session":
        """Factory method to load existing session from database."""
        session = cls(session_id, db_path)

        if session.model is None:
            raise ValueError(f"Session '{session_id}' not found")

        session.model_identifier = session.model.model_identifier
        session.tools = session.model.tool_definitions
        session.request_params = session.model.request_params
        session.prompt_id = session.model.prompt_id
        session.prompt_args = session.model.prompt_args

        # Load messages - just deserialize the data column
        messages = (
            session.db.query(Message)
            .filter_by(session_id=session_id)
            .order_by(Message.id)
            .all()
        )
        session.messages = [m.data for m in messages]

        return session

    @classmethod
    def swap_session_id(
        cls,
        old_session_id: str,
        new_session_id: str,
        db_path: str = "sqlite:///crow.db",
    ) -> str:
        """
        Atomically swap session IDs for compaction.

        old_session_id -> archive_id (preserves full history)
        new_session_id -> old_session_id (compacted session takes over)
        """
        archive_id = f"sess_archive_{uuid4().hex}"

        db = SQLAlchemySession(create_engine(db_path))
        try:
            # Move old session to archive
            old_session = (
                db.query(SessionModel).filter_by(session_id=old_session_id).first()
            )
            if not old_session:
                raise ValueError(f"Session '{old_session_id}' not found")
            old_session.session_id = archive_id
            db.query(Message).filter_by(session_id=old_session_id).update(
                {"session_id": archive_id}
            )

            # Move new session to old_session_id
            new_session = (
                db.query(SessionModel).filter_by(session_id=new_session_id).first()
            )
            if not new_session:
                raise ValueError(f"Session '{new_session_id}' not found")
            new_session.session_id = old_session_id
            db.query(Message).filter_by(session_id=new_session_id).update(
                {"session_id": old_session_id}
            )

            db.commit()
            return archive_id
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def update_from(self, other: "Session") -> None:
        """Update this session's state from another session in-place."""
        self.session_id = other.session_id
        self.db_path = other.db_path
        self.cwd = other.cwd
        self.messages = other.messages
        self.model_identifier = other.model_identifier
        self.tools = other.tools
        self.request_params = other.request_params
        self.prompt_id = other.prompt_id
        self.prompt_args = other.prompt_args

        if self._db is not None:
            self._db.close()
        self._db = None
        self._model = None
