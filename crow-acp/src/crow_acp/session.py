"""
Session management - persistence layer for conversation state.

Encapsulates:
- In-memory conversation state (messages, conv_index)
- Database persistence
- Session creation/loading
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SQLAlchemySession

from .db import Base, Event, Prompt
from .db import Session as SessionModel
from .prompt import render_template

logger = logging.getLogger(__name__)

# Path to the system prompt template
_PROMPTS_DIR = Path(__file__).parent / "prompts"


def ensure_database(db_path: str = "sqlite:///mcp_testing.db") -> None:
    """
    Ensure database tables exist and the crow-v1 prompt is seeded.

    Safe to call on every startup — idempotent.
    """
    engine = create_engine(db_path)
    Base.metadata.create_all(engine)

    db = SQLAlchemySession(engine)
    try:
        # Load the real template from disk
        template_path = _PROMPTS_DIR / "system_prompt.jinja2"
        template_content = template_path.read_text()

        existing = db.query(Prompt).filter_by(id="crow-v1").first()
        if existing:
            # Update template if it changed on disk
            if existing.template != template_content:
                existing.template = template_content
                db.commit()
                logger.info("Updated crow-v1 prompt template from disk")
        else:
            prompt = Prompt(
                id="crow-v1",
                name="Crow Default Prompt",
                template=template_content,
            )
            db.add(prompt)
            db.commit()
            logger.info("Seeded crow-v1 prompt into database")
    finally:
        db.close()


def lookup_or_create_prompt(
    template: str,
    name: str,
    db_path: str = "sqlite:///mcp_testing.db",
) -> str:
    """
    Lookup existing prompt by template content, or create new one if not found.

    This implements the simple direct lookup pattern:
    1. Try to find prompt by exact template match
    2. If found, return its ID
    3. If not found, create new prompt with generated ID

    Args:
        template: Template string content
        name: Display name for the prompt
        db_path: Database connection string

    Returns:
        Prompt ID (existing or newly created)
    """
    db = SQLAlchemySession(create_engine(db_path))

    try:
        # Try to find existing prompt by template content
        existing = db.query(Prompt).filter_by(template=template).first()

        if existing:
            db.close()
            return existing.id

        # Create new prompt with generated ID
        import json

        prompt_id = f"prompt-{hashlib.sha256(template.encode()).hexdigest()[:12]}"

        new_prompt = Prompt(
            id=prompt_id,
            name=name,
            template=template,
        )
        db.add(new_prompt)
        db.commit()
        db.close()

        return prompt_id
    finally:
        db.close()


class Session:
    """
    Manages conversation state and persistence.

    Responsibilities:
    - Build and maintain conversation messages (in-memory)
    - Persist events to database
    - Reconstruct conversation from database
    """

    def __init__(self, session_id: str, db_path: str = "sqlite:///mcp_testing.db"):
        """
        Initialize session with ID and database path.

        Args:
            session_id: Unique session identifier
            db_path: Database connection string
        """
        self.session_id = session_id
        self.db_path = db_path
        self.messages = []
        self.conv_index = 0
        self._db = None
        self._model = None  # SQLAlchemy model instance

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

    def add_message(
        self,
        role: str,
        content: str | None = None,
        reasoning_content: str | None = None,
        tool_call_id: str | None = None,
        tool_call_name: str | None = None,
        tool_arguments: dict | None = None,
        **kwargs,
    ):
        """
        Add message to in-memory messages AND persist to database.

        Args:
            role: Message role (user, assistant, tool, system)
            content: Text content
            reasoning_content: Thinking tokens (for reasoning models)
            tool_call_id: Tool call ID
            tool_call_name: Name of tool called
            tool_arguments: Arguments passed to tool
            **kwargs: Additional message fields
        """
        # Build message for LLM
        msg = {"role": role}
        if content is not None:
            msg["content"] = content
        if reasoning_content is not None:
            msg["reasoning_content"] = reasoning_content
        if tool_call_id is not None:
            msg["tool_call_id"] = tool_call_id
        if tool_call_name is not None:
            msg["tool_call_name"] = tool_call_name
        if tool_arguments is not None:
            msg["tool_arguments"] = tool_arguments
        msg.update(kwargs)
        self.messages.append(msg)

        # Persist to database
        self._save_event(
            role=role,
            content=content,
            reasoning_content=reasoning_content,
            tool_call_id=tool_call_id,
            tool_call_name=tool_call_name,
            tool_arguments=tool_arguments,
        )

    def add_assistant_response(
        self,
        thinking: list[str],
        content: list[str],
        tool_call_inputs: list[dict],
        tool_results: list[dict],
    ):
        """
        Handle complex assistant message building + tool calls + results.

        This replaces the add_response_to_messages function but as a method
        with access to all session state.

        Args:
            thinking: List of thinking tokens
            content: List of content tokens
            tool_call_inputs: Tool calls from assistant
            tool_results: Results from tool execution
        """
        # Save assistant response with token counts
        if len(content) > 0 or len(thinking) > 0:
            self.add_message(
                role="assistant",
                content="".join(content) if content else None,
                reasoning_content="".join(thinking) if thinking else None,
            )

        # Build assistant message for LLM (with thinking and content)
        if len(content) > 0 and len(thinking) > 0:
            self.messages.append(
                {
                    "role": "assistant",
                    "content": "".join(content),
                    "reasoning_content": "".join(thinking),
                }
            )
        elif len(thinking) > 0:
            self.messages.append(
                {"role": "assistant", "reasoning_content": "".join(thinking)}
            )
        elif len(content) > 0:
            self.messages.append({"role": "assistant", "content": "".join(content)})

        # Add tool calls and save them
        if len(tool_call_inputs) > 0:
            self.messages.append({"role": "assistant", "tool_calls": tool_call_inputs})
            # Save each tool call
            for tool_call in tool_call_inputs:
                self._save_event(
                    role="assistant",
                    tool_call_id=tool_call["id"],
                    tool_call_name=tool_call["function"]["name"],
                    tool_arguments=json.loads(tool_call["function"]["arguments"]),
                )

        # Add tool results and save them
        if len(tool_results) > 0:
            self.messages.extend(tool_results)
            for tool_result in tool_results:
                self._save_event(
                    role="tool",
                    tool_call_id=tool_result["tool_call_id"],
                    content=tool_result["content"],
                )

    def _save_event(
        self,
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
        Save event to database (internal method).

        Args:
            role: Event role
            content: Text content
            reasoning_content: Thinking tokens
            tool_call_id: Tool call ID
            tool_call_name: Tool name
            tool_arguments: Tool arguments
            prompt_tokens: Input token count
            completion_tokens: Output token count
            total_tokens: Total token count
            event_metadata: Additional metadata
        """
        event = Event(
            session_id=self.session_id,
            conv_index=self.conv_index,
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
        self.db.add(event)
        self.db.commit()
        self.conv_index += 1

    @classmethod
    def create(
        cls,
        prompt_id: str,
        prompt_args: dict[str, Any],
        tool_definitions: list[dict],
        request_params: dict[str, Any],
        model_identifier: str,
        db_path: str = "sqlite:///mcp_testing.db",
    ) -> "Session":
        """
        Factory method to create a new session.

        Renders prompt template, creates session_id, sets up DB record.

        Args:
            prompt_id: ID of prompt template to use
            prompt_args: Arguments to render template with
            tool_definitions: List of tool definitions
            request_params: LLM request parameters
            model_identifier: Model identifier string
            db_path: Database connection string

        Returns:
            New Session instance
        """
        # Load prompt template
        db = SQLAlchemySession(create_engine(db_path))
        prompt = db.query(Prompt).filter_by(id=prompt_id).first()
        if not prompt:
            raise ValueError(f"Prompt '{prompt_id}' not found")

        # Render system prompt
        system_prompt = render_template(prompt.template, **prompt_args)

        # Generate unique session ID (UUID-based, like everyone else)
        import uuid

        session_id = f"sess_{uuid.uuid4().hex[:16]}"

        # Create new session model
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

        # Create Session instance with system message
        session = cls(session_id, db_path)
        session.messages = [{"role": "system", "content": system_prompt}]

        return session

    @classmethod
    def load(
        cls, session_id: str, db_path: str = "sqlite:///mcp_testing.db"
    ) -> "Session":
        """
        Factory method to load existing session from database.

        Reconstructs conversation from events.

        Args:
            session_id: Session ID to load
            db_path: Database connection string

        Returns:
            Loaded Session instance
        """
        session = cls(session_id, db_path)

        # Load session model
        if session.model is None:
            raise ValueError(f"Session '{session_id}' not found")

        # Reconstruct messages from events
        events = (
            session.db.query(Event)
            .filter_by(session_id=session_id)
            .order_by(Event.conv_index)
            .all()
        )

        session.messages = [{"role": "system", "content": session.model.system_prompt}]

        for event in events:
            msg = {"role": event.role}

            if event.content:
                msg["content"] = event.content
            if event.reasoning_content:
                msg["reasoning_content"] = event.reasoning_content
            if event.tool_call_id and event.tool_call_name:
                # Tool call or tool result
                if event.role == "assistant":
                    # Reconstruct tool call
                    if "tool_calls" not in session.messages[-1]:
                        session.messages.append({"role": "assistant", "tool_calls": []})
                    session.messages[-1]["tool_calls"].append(
                        {
                            "id": event.tool_call_id,
                            "type": "function",
                            "function": {
                                "name": event.tool_call_name,
                                "arguments": __import__("json").dumps(
                                    event.tool_arguments
                                ),
                            },
                        }
                    )
                    continue
                elif event.role == "tool":
                    msg["tool_call_id"] = event.tool_call_id

            if msg:  # Only append if we have content
                session.messages.append(msg)

        session.conv_index = len(events)

        return session
