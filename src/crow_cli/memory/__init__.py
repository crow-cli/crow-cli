"""
crow_cli.memory — the one memory contract for crow.

SQLAlchemy over a caller-supplied ``db_uri`` — sqlite by default,
PostgreSQL supported (``postgresql+psycopg://``) for multi-machine shared
state. Dialect-specifics live in exactly two places: ``fts`` (FTS5/bm25 on
sqlite, tsvector/GIN on postgres, same lower=better contract) and
``get_ro_engine`` (mode=ro URI vs session READ ONLY).

This package reads NO config. Apps resolve their own db_uri and pass it in:

    engine = crow_cli.memory.get_engine("sqlite:///~/.agents/crow/crow.db")

Schema v5: one row = one message, agent-centric, fork-aware.
agent_id = "{session_id}-{agent_idx}-{fork_idx}" is the primary key (all
1-based; the trunk carries fork_idx=1); session_id is the logical parent
(multiple agents per session, multiple forks per agent_idx).

Search is keyword-only (no embeddings, no service, no lance): FTS5 + bm25
on sqlite, tsvector + ts_rank on postgres — see ``fts``.

Module map:
    models    — ORM schema (Prompt, Agent, Task, TaskDelivery, Goal, Message)
                and the GOAL_* status vocabulary
    ids       — agent_id build/parse (v5 three-part format)
    db        — db_uri normalization, engine factories, create_database
    fts       — the full-text-search seam (sqlite FTS5 / postgres tsvector)
    messages  — image extract/hydrate, searchable text, a transcript's
                final answer
    writes    — add_message, create_agent, set_agent_mcp_servers,
                set_agent_model, launch_task, launch_next_task, finish_task,
                cancel_task, mark_delivered, claim_deliveries,
                lookup_or_create_prompt, queue_delivery, set_goal,
                update_goal_status, clear_goal, account_goal_usage
    reads     — queries, list_sessions, get_session_mcp_servers,
                get_task, running_tasks, owner_tasks, pending_deliveries,
                get_goal, active_goal, search_messages, session_title
"""

from sqlalchemy.orm import Session

from .db import create_database, get_engine, get_ro_engine, normalize_db_uri
from .ids import build_agent_id, parse_agent_id, wire_session_id
from .image_store import (
    FsImageStore,
    HybridReadStore,
    ImageStore,
    S3ImageStore,
    resolve_image_store,
)
from .messages import extract_images, hydrate_message, last_assistant_text, message_text
from .models import (
    GOAL_ACTIVE,
    GOAL_BLOCKED,
    GOAL_BUDGET_LIMITED,
    GOAL_COMPLETE,
    GOAL_PAUSED,
    Agent,
    Base,
    Goal,
    Message,
    Prompt,
    Task,
    TaskDelivery,
    now_iso,
)
from .reads import (
    active_goal,
    agent_index,
    delegation_tool_call_ids,
    get_agent,
    get_goal,
    get_max_agent_idx,
    get_max_fork_idx,
    get_prompt,
    get_session_mcp_servers,
    get_task,
    list_agents,
    list_session_infos,
    list_sessions,
    load_agent_messages,
    load_messages,
    owner_tasks,
    pending_deliveries,
    query_messages,
    running_tasks,
    search_messages,
    session_exists,
    session_title,
)
from .writes import (
    account_goal_usage,
    add_message,
    claim_deliveries,
    clear_goal,
    create_agent,
    finish_task,
    launch_next_task,
    launch_task,
    lookup_or_create_prompt,
    mark_delivered,
    queue_delivery,
    set_agent_mcp_servers,
    set_agent_model,
    set_goal,
    update_goal_status,
)

__all__ = [
    "Agent",
    "Base",
    "Message",
    "Prompt",
    "Session",
    "Task",
    "TaskDelivery",
    "account_goal_usage",
    "active_goal",
    "add_message",
    "agent_index",
    "build_agent_id",
    "claim_deliveries",
    "clear_goal",
    "create_agent",
    "create_database",
    "delegation_tool_call_ids",
    "extract_images",
    "finish_task",
    "FsImageStore",
    "get_agent",
    "get_engine",
    "get_goal",
    "get_ro_engine",
    "get_max_agent_idx",
    "get_max_fork_idx",
    "get_prompt",
    "get_session_mcp_servers",
    "get_task",
    "Goal",
    "GOAL_ACTIVE",
    "GOAL_BLOCKED",
    "GOAL_BUDGET_LIMITED",
    "GOAL_COMPLETE",
    "GOAL_PAUSED",
    "HybridReadStore",
    "hydrate_message",
    "ImageStore",
    "last_assistant_text",
    "launch_next_task",
    "launch_task",
    "list_agents",
    "list_session_infos",
    "list_sessions",
    "load_agent_messages",
    "load_messages",
    "lookup_or_create_prompt",
    "mark_delivered",
    "message_text",
    "normalize_db_uri",
    "now_iso",
    "owner_tasks",
    "parse_agent_id",
    "pending_deliveries",
    "query_messages",
    "queue_delivery",
    "running_tasks",
    "resolve_image_store",
    "S3ImageStore",
    "search_messages",
    "session_exists",
    "session_title",
    "set_agent_mcp_servers",
    "set_agent_model",
    "set_goal",
    "update_goal_status",
    "wire_session_id",
]
