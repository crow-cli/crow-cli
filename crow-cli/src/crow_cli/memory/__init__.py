"""
crow_cli.memory — the one memory contract for crow.

SQLAlchemy over a caller-supplied ``db_uri`` (sqlite by default; the schema
is plain SQLAlchemy so postgres is a seam away — except FTS5 keyword search,
which is sqlite-specific and lives behind ``search_messages``).

This package reads NO config. Apps resolve their own db_uri and pass it in:

    engine = crow_cli.memory.get_engine("sqlite:///~/.agents/crow/crow.db")

Schema v4: one row = one message, agent-centric. agent_id = "{session_id}-{idx}"
is the primary key; session_id is the logical parent (multiple agents per
session).

Search is SQLite FTS5 + bm25 (keyword). No embeddings, no service, no lance.

Module map:
    models    — ORM schema (Prompt, Agent, Message)
    db        — db_uri normalization, engine factory, create_database
    messages  — image extract/hydrate, searchable text
    writes    — add_message, create_agent, lookup_or_create_prompt
    reads     — queries, list_sessions, search_messages
"""

from sqlalchemy.orm import Session

from .db import create_database, get_engine, normalize_db_uri
from .messages import extract_images, hydrate_message, message_text
from .models import Agent, Base, Message, Prompt, now_iso
from .reads import (
    get_agent,
    get_max_agent_idx,
    get_prompt,
    list_agents,
    list_sessions,
    load_messages,
    query_messages,
    search_messages,
)
from .writes import add_message, create_agent, lookup_or_create_prompt

__all__ = [
    "Agent",
    "Base",
    "Message",
    "Prompt",
    "Session",
    "add_message",
    "create_agent",
    "create_database",
    "extract_images",
    "get_agent",
    "get_engine",
    "get_max_agent_idx",
    "get_prompt",
    "hydrate_message",
    "list_agents",
    "list_sessions",
    "load_messages",
    "lookup_or_create_prompt",
    "message_text",
    "normalize_db_uri",
    "now_iso",
    "query_messages",
    "search_messages",
]
