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
    models    — ORM schema (Prompt, Agent, Task, TaskDelivery, Message)
    ids       — agent_id build/parse (v5 three-part format)
    db        — db_uri normalization, engine factory, create_database
    messages  — image extract/hydrate, searchable text
    writes    — add_message, create_agent, set_agent_mcp_servers,
                launch_task, finish_task, cancel_task, mark_delivered,
                claim_deliveries, lookup_or_create_prompt
    reads     — queries, list_sessions, get_session_mcp_servers,
                get_task, running_tasks, pending_deliveries,
                search_messages
"""

from sqlalchemy.orm import Session

from .db import create_database, get_engine, normalize_db_uri
from .ids import build_agent_id, parse_agent_id, wire_session_id
from .image_store import (
    FsImageStore,
    HybridReadStore,
    ImageStore,
    S3ImageStore,
    resolve_image_store,
)
from .messages import extract_images, hydrate_message, message_text
from .models import (
    Agent,
    Base,
    Message,
    Prompt,
    Task,
    TaskDelivery,
    now_iso,
)
from .reads import (
    agent_index,
    get_agent,
    get_max_agent_idx,
    get_max_fork_idx,
    get_prompt,
    get_session_mcp_servers,
    get_task,
    list_agents,
    list_sessions,
    load_agent_messages,
    load_messages,
    pending_deliveries,
    query_messages,
    running_tasks,
    search_messages,
)
from .writes import (
    add_message,
    claim_deliveries,
    create_agent,
    finish_task,
    launch_task,
    lookup_or_create_prompt,
    mark_delivered,
    set_agent_mcp_servers,
)

__all__ = [
    "Agent",
    "Base",
    "Message",
    "Prompt",
    "Session",
    "Task",
    "TaskDelivery",
    "add_message",
    "agent_index",
    "build_agent_id",
    "claim_deliveries",
    "create_agent",
    "create_database",
    "extract_images",
    "finish_task",
    "FsImageStore",
    "get_agent",
    "get_engine",
    "get_max_agent_idx",
    "get_max_fork_idx",
    "get_prompt",
    "get_session_mcp_servers",
    "get_task",
    "HybridReadStore",
    "hydrate_message",
    "ImageStore",
    "launch_task",
    "list_agents",
    "list_sessions",
    "load_agent_messages",
    "load_messages",
    "lookup_or_create_prompt",
    "mark_delivered",
    "message_text",
    "normalize_db_uri",
    "now_iso",
    "parse_agent_id",
    "pending_deliveries",
    "query_messages",
    "running_tasks",
    "resolve_image_store",
    "S3ImageStore",
    "search_messages",
    "set_agent_mcp_servers",
    "wire_session_id",
]
