"""Async facade over the session_tabs table in the shared store.

The TUI no longer keeps a private sqlite: tab state lives in crow.db
(crow_cli.memory's session_tabs) beside sessions/messages. The db_uri is
resolved from crow_cli.config — the same authority the agent and the MCP
surfaces draw from.
"""

import asyncio
import json
from typing import TypedDict, cast


class Session(TypedDict):
    """Agent session fields."""

    id: int
    """Primary key."""
    agent: str
    """Title of the agent."""
    agent_identity: str
    """Agent identity."""
    agent_session_id: str
    """Agent's session id."""
    title: str
    """Title of session."""
    protocol: str
    """Protocol used."""
    promot_count: int
    """Number of prompts sent."""
    created_at: str
    """Time session was created."""
    last_used: str
    """Time sesison was last used."""
    meta_json: str
    """Text field containing JSON meta."""


class DB:
    """Session-tab store facade; the shared crow.db is the authority."""

    def __init__(self, db_uri: str | None = None):
        if db_uri is None:
            from crow_cli.config import Config

            db_uri = Config.load().db_uri
        self.db_uri = db_uri

    async def create(self) -> bool:
        """Create the tables if required."""
        from crow_cli.memory.db import create_database

        try:
            await asyncio.to_thread(create_database, self.db_uri)
        except Exception:
            return False
        return True

    async def session_new(
        self,
        title: str,
        agent: str,
        agent_identity: str,
        agent_session_id: str,
        protocol: str = "acp",
        meta: dict[str, object] | None = None,
    ) -> int | None:
        from crow_cli.memory import session_tabs

        return await asyncio.to_thread(
            session_tabs.tab_new,
            self.db_uri,
            title=title,
            agent=agent,
            agent_identity=agent_identity,
            agent_session_id=agent_session_id,
            protocol=protocol,
            meta_json=json.dumps(meta or {}),
        )

    async def session_update_last_used(self, id: int) -> bool:
        """Update the last used timestamp."""
        from crow_cli.memory import session_tabs

        return await asyncio.to_thread(session_tabs.tab_touch, self.db_uri, id)

    async def session_update_title(self, id: int, title: str) -> bool:
        """Rename a session tab."""
        from crow_cli.memory import session_tabs

        return await asyncio.to_thread(session_tabs.tab_rename, self.db_uri, id, title)

    async def session_get(self, id: int) -> Session | None:
        """Get a session from its ID (PK, not the agent_session_id)."""
        from crow_cli.memory import session_tabs

        row = await asyncio.to_thread(session_tabs.tab_get, self.db_uri, id)
        return cast(Session, row) if row is not None else None

    async def session_get_recent(self, max_results: int = 100) -> list[Session] | None:
        """Get the most recent sessions."""
        from crow_cli.memory import session_tabs

        rows = await asyncio.to_thread(
            session_tabs.tab_recent, self.db_uri, max_results
        )
        return [cast(Session, row) for row in rows]
