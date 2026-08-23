"""
crow_cli.memory — the one memory contract for crow.

SQLAlchemy over a caller-supplied ``db_uri`` (sqlite by default; the schema
is plain SQLAlchemy so postgres is a seam away — except FTS5 keyword search,
which is sqlite-specific and lives behind ``search_messages``).

This package reads NO config. Apps resolve their own db_uri and pass it in:

    engine = crow_cli.memory.get_engine("sqlite:///~/.agents/crow/crow.db")

Schema v5: one row = one message, agent-centric, fork-aware.
agent_id = "{session_id}-{agent_idx}-{fork_idx}" is the primary key (all
1-based; the trunk carries fork_idx=1); session_id is the logical parent
(multiple agents per session, multiple forks per agent_idx).

Search is SQLite FTS5 + bm25 (keyword). No embeddings, no service, no lance.

Module map:
    models    — ORM schema (Prompt, Agent, SessionMcpServers, Message)
    ids       — agent_id build/parse (v5 three-part format)
    db        — db_uri normalization, engine factory, create_database
    messages  — image extract/hydrate, searchable text
    writes    — add_message, create_agent, set_session_mcp_servers,
                lookup_or_create_prompt
    reads     — queries, list_sessions, get_session_mcp_servers,
                search_messages
"""

from sqlalchemy.orm import Session

from .db import create_database, get_engine, normalize_db_uri
from .ids import build_agent_id, parse_agent_id, wire_session_id
from .messages import extract_images, hydrate_message, message_text
from .models import Agent, Base, Message, Prompt, SessionMcpServers, now_iso
from .reads import (
    get_agent,
    get_max_agent_idx,
    get_max_fork_idx,
    get_prompt,
    get_session_mcp_servers,
    list_agents,
    list_sessions,
    load_agent_messages,
    load_messages,
    query_messages,
    search_messages,
)
from .writes import (
    add_message,
    create_agent,
    lookup_or_create_prompt,
    set_session_mcp_servers,
)

__all__ = [
    "Agent",
    "Base",
    "Message",
    "Prompt",
    "Session",
    "SessionMcpServers",
    "add_message",
    "build_agent_id",
    "create_agent",
    "create_database",
    "extract_images",
    "get_agent",
    "get_engine",
    "get_max_agent_idx",
    "get_max_fork_idx",
    "get_prompt",
    "get_session_mcp_servers",
    "hydrate_message",
    "list_agents",
    "list_sessions",
    "load_agent_messages",
    "load_messages",
    "lookup_or_create_prompt",
    "message_text",
    "normalize_db_uri",
    "now_iso",
    "parse_agent_id",
    "query_messages",
    "search_messages",
    "set_session_mcp_servers",
    "wire_session_id",
]
