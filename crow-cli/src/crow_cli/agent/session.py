"""
Agent session management - persistence layer for conversation state.

One row = One message. No conv_index gymnastics. No reconstruction headaches.
Just serialize the message dict, deserialize it back.

Agent owns the session. agent_id = "{session_id}-{agent_idx}" is the PK.
session_id is derived from agent_id for ACP upstream routing.
"""

import json
import os
from logging import Logger
from pathlib import Path
from typing import Any

from coolname import generate_slug
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session as SQLAlchemySession

from crow_cli.agent.db import Agent as AgentModel
from crow_cli.agent.db import (
    Message,
    Prompt,
    create_database,
    get_schemas,
)
from crow_cli.agent.prompt import render_template
from crow_cli.agent.context import get_directory_tree

from crow_cli.agent.configure import Config

def get_session_by_cwd(cwd, db_uri):
    """
    Lookup agents by working directory.

    Returns list of session info dicts with session_id, title, updated_at.
    """
    db = SQLAlchemySession(create_engine(db_uri))
    try:
        agents = db.query(AgentModel).all()
        result = []
        for agent in agents:
            # Parse prompt_args from JSON string to dict
            prompt_args = agent.prompt_args
            if isinstance(prompt_args, str):
                try:
                    prompt_args = json.loads(prompt_args)
                except json.JSONDecodeError, TypeError:
                    prompt_args = {}

            # Check if workspace matches
            if not prompt_args or prompt_args.get("workspace") != cwd:
                continue

            # Get message count and title
            msgs = (
                db.query(Message)
                .filter_by(agent_id=agent.agent_id)
                .order_by(Message.id)
                .all()
            )
            if len(msgs) > 2:
                # Get content from second message (index 1, after system message)
                try:
                    data = msgs[1].data
                    if isinstance(data, str):
                        data = json.loads(data)
                    title = data.get("content", "")[:50] if data else "Untitled Chat"
                except json.JSONDecodeError, AttributeError, TypeError:
                    title = "Untitled Chat"
            else:
                title = "Untitled Chat"

            result.append(
                {
                    "cwd": cwd,
                    "session_id": agent.session_id,
                    "agent_id": agent.agent_id,
                    "title": title,
                    "updated_at": agent.created_at.isoformat(),
                }
            )
        return result
    finally:
        db.close()


def get_coolname() -> str:
    """Generate a memorable slug"""
    return generate_slug(4)


def lookup_or_create_prompt(
    template: str,
    name: str,
    db_uri: str = "sqlite:///crow.db",
) -> str:
    """
    Lookup existing prompt by template content, or create new one if not found.
    """
    # Ensure database tables exist
    create_database(db_uri)

    db = SQLAlchemySession(create_engine(db_uri))
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


class AgentSession:
    """
    Manages conversation state and persistence.

    agent_id = "{session_id}-{agent_idx}" is the DB key.
    session_id is derived for ACP upstream routing only.

    Two databases:
    - db_uri: session data (agents, messages, prompts)
    """

    def __init__(
        self,
        agent_id: str,
        session_id: str,
        agent_idx: int = 0,
        db_uri: str = "sqlite:///crow.db",
        cwd: str = "/tmp",
    ):
        self.agent_id = agent_id
        self.session_id = session_id
        self.agent_idx = agent_idx
        self.db_uri = db_uri
        self.cwd = cwd
        self.messages: list[dict] = []
        self._db = None
        self._model = None
        self.model_identifier = None

    @property
    def db(self) -> SQLAlchemySession:
        """Lazy-load database connection with WAL mode for concurrent reads."""
        if self._db is None:
            engine = create_engine(self.db_uri)
            self._db = SQLAlchemySession(engine)
        return self._db

    @property
    def model(self) -> AgentModel:
        """Lazy-load agent model from database"""
        if self._model is None:
            self._model = (
                self.db.query(AgentModel).filter_by(agent_id=self.agent_id).first()
            )
        return self._model

    def add_message(self, msg: dict, usage: dict | None = None):
        """
        Add message to in-memory list AND persist to database.

        Args:
            msg: Full message dict (role, content, tool_calls, etc.)
            usage: Token usage dict with prompt_tokens, completion_tokens, total_tokens
        """
        self.messages.append(msg)

        # Persist - one row = one message
        db_msg = Message(
            agent_id=self.agent_id,
            data=msg,
            role=msg.get("role", "unknown"),
            prompt_tokens=usage.get("prompt_tokens") if usage else None,
            completion_tokens=usage.get("completion_tokens") if usage else None,
            total_tokens=usage.get("total_tokens") if usage else None,
        )
        self.db.add(db_msg)
        self.db.commit()

    def add_tool_response(
        self,
        tool_results: list[dict],
        logger: Logger,
    ):
        for tool_result in tool_results:
            logger.info(f"TOOL RESULT: {tool_result}")
            self.add_message(tool_result)

    def add_assistant_response(
        self,
        thinking: list[str],
        content: list[str],
        tool_call_inputs: list[dict],
        logger: Logger,
        usage: dict | None = None,
    ):
        """
        Handle complex react message building + tool calls + results.

        Args:
            thinking: List of thinking tokens
            content: List of content tokens
            tool_call_inputs: Tool calls from assistant
            logger: Logger instance
            usage: Token usage dict with prompt_tokens, completion_tokens, total_tokens
        """
        # Build react message
        # if it's just thinking tokens don't add that shit
        if len(content) > 0 or len(tool_call_inputs) > 0:
            thinking_text = "".join(thinking) if thinking else ""
            content_text = "".join(content) if content else ""
            msg = {"role": "assistant", "content": content_text}
            if thinking_text and thinking_text != "":
                msg["reasoning_content"] = thinking_text
            if tool_call_inputs:
                msg["tool_calls"] = tool_call_inputs

            logger.info(f"Adding message: {msg}")
            logger.info(f"Message usage: {usage}")
            # Add to database/list
            self.add_message(msg, usage)

    def _save_messages(self, messages: list[dict]):
        """Batch save messages to database."""
        for msg in messages:
            db_msg = Message(
                agent_id=self.agent_id,
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
        db_uri: str = "sqlite:///crow.db",
        cwd: str = "/tmp",
        agent_idx: int = 0,
        session_id: str | None = None,
        initial_messages: list[dict[str, Any]] | None = None,
    ) -> "AgentSession":
        """Factory method to create a new agent session."""
        # Ensure both databases exist
        create_database(db_uri)

        db = SQLAlchemySession(create_engine(db_uri))

        # Load and render prompt
        prompt = db.query(Prompt).filter_by(id=prompt_id).first()
        if not prompt:
            db.close()
            raise ValueError(f"Prompt '{prompt_id}' not found")

        system_prompt = render_template(prompt.template, **prompt_args)
        if session_id is None:
            session_id = get_coolname()
        agent_id = f"{session_id}-{agent_idx}"

        # Create agent record
        agent_model = AgentModel(
            agent_id=agent_id,
            session_id=session_id,
            agent_idx=agent_idx,
            cwd=cwd,
            prompt_id=prompt_id,
            prompt_args=prompt_args,
            system_prompt=system_prompt,
            tool_definitions=tool_definitions,
            request_params=request_params,
            model_identifier=model_identifier,
        )
        db.add(agent_model)
        db.commit()
        db.close()

        # Build session instance
        session = cls(agent_id, session_id, agent_idx, db_uri, cwd=cwd)
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
    def get_max_agent_idx(
        cls,
        session_id: str,
        db_uri: str = "sqlite:///crow.db",
    ) -> int:
        """Return the highest agent_idx for a given session_id."""
        db = SQLAlchemySession(create_engine(db_uri))
        try:
            result = (
                db.query(AgentModel.agent_idx)
                .filter_by(session_id=session_id)
                .order_by(AgentModel.agent_idx.desc())
                .first()
            )
            return result[0] if result else -1
        finally:
            db.close()

    @classmethod
    def load(
        cls,
        agent_id: str,
        db_uri: str = "sqlite:///crow.db",
    ) -> "AgentSession":
        """Factory method to load existing agent session from database."""
        db = SQLAlchemySession(create_engine(db_uri))
        agent_model = db.query(AgentModel).filter_by(agent_id=agent_id).first()
        if not agent_model:
            db.close()
            raise ValueError(f"Agent '{agent_id}' not found")

        session = cls(
            agent_id=agent_model.agent_id,
            session_id=agent_model.session_id,
            agent_idx=agent_model.agent_idx,
            db_uri=db_uri,
            cwd=agent_model.cwd,
        )
        session.model_identifier = agent_model.model_identifier
        session.tools = agent_model.tool_definitions
        session.request_params = agent_model.request_params
        session.prompt_id = agent_model.prompt_id
        session.prompt_args = agent_model.prompt_args

        # Load messages - just deserialize the data column
        messages = (
            db.query(Message).filter_by(agent_id=agent_id).order_by(Message.id).all()
        )
        db.close()
        session.messages = [m.data for m in messages]

        return session

    def close(self):
        """Close database connections."""
        if self._db is not None:
            self._db.close()
        self._db = None
        self._model = None


def make_agent_session(
    config: Config,
    tools: list[dict],
    model_id: str,
    cwd: str,
    session_id: str | None = None,
    agent_idx: int | None = None,
):
    if not config.system_prompt:
        template_path = config.config_dir / "prompts" / "system_prompt.jinja2"
        template = template_path.read_text()
    else:
        template = config.system_prompt
    prompt_id = lookup_or_create_prompt(
        template, name="crow-default", db_uri=config.db_uri
    )
    display_tree = get_directory_tree(cwd)
    agent_path = os.path.join(cwd, "AGENTS.md")
    if os.path.exists(agent_path):
        with open(agent_path, "r") as f:
            agents_content = f.read()
    else:
        agents_content = "No AGENTS.md found"
    if session_id is None:
        session_id = get_coolname()
    if agent_idx is None:
        agent_idx = 1
    return AgentSession.create(
        prompt_id=prompt_id,
        prompt_args={
            "workspace": cwd,
            "display_tree": display_tree,
            "agents_content": agents_content,
            "session_id": session_id,
        },
        tool_definitions=tools,
        request_params={"temperature": 0.2},
        model_identifier=model_id,
        db_uri=config.db_uri,
        cwd=cwd,
        agent_idx=agent_idx,
        session_id=session_id,
    )
