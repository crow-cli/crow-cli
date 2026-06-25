import json
import os
from datetime import datetime
from enum import Enum

from fastmcp import FastMCP
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base

DB_PATH = os.path.expanduser("~/.crow/crow.db")
engine = create_engine(f"sqlite:///{DB_PATH}")

Base = declarative_base()

from crow_mcp.server.main import mcp


class Agent(Base):
    __tablename__ = "agents"
    agent_id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    agent_idx = Column(Integer, nullable=False)
    cwd = Column(Text, nullable=False)
    prompt_id = Column(String, ForeignKey("prompts.id"))
    prompt_args = Column(JSON)
    system_prompt = Column(Text, nullable=False)
    tool_definitions = Column(JSON, nullable=False)
    request_params = Column(JSON, nullable=False)
    model_identifier = Column(String, nullable=False)
    status = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    agent_id = Column(
        String,
        ForeignKey("agents.agent_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(DateTime, nullable=False)
    data = Column(JSON, nullable=False)
    role = Column(String, nullable=False, index=True)
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    total_tokens = Column(Integer)


class ContentMode(str, Enum):
    CONVERSATION = "conversation"
    WITH_THINKING = "with_thinking"
    WITH_TOOLS = "with_tools"
    FULL = "full"


def _extract_searchable_text(data: dict) -> str:
    """Extract all searchable text from a message data dict."""
    parts = []
    role = data.get("role")

    if role == "user":
        content = data.get("content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
        elif isinstance(content, str):
            parts.append(content)

    elif role == "assistant":
        if data.get("content"):
            parts.append(data["content"])
        if data.get("reasoning_content"):
            parts.append(data["reasoning_content"])
        for tc in data.get("tool_calls", []):
            fn = tc.get("function", {})
            parts.append(fn.get("name", ""))
            parts.append(fn.get("arguments", ""))

    elif role == "tool":
        parts.append(data.get("content", ""))
        parts.append(data.get("tool_call_id", ""))

    return " ".join(parts)


def _extract_display_text(data: dict) -> str:
    """Extract the primary display text from a message."""
    role = data.get("role")

    if role == "user":
        content = data.get("content", "")
        if isinstance(content, list):
            texts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            return " ".join(texts)
        return content if isinstance(content, str) else ""

    if role == "assistant":
        return data.get("content", "")

    if role == "tool":
        return data.get("content", "")

    return ""


def _format_message(data: dict, mode: ContentMode) -> str | None:
    """Format a single message for display. Returns None if skipped."""
    role = data.get("role")
    ts = data.get("_created_at", "")
    prefix = f"**[{ts}]** " if ts else ""

    if role == "user":
        text = _extract_display_text(data)
        if not text:
            return None
        return f"{prefix}**USER**\n{text}"

    if role == "assistant":
        lines = []
        if mode in (ContentMode.WITH_THINKING, ContentMode.FULL):
            thinking = data.get("reasoning_content", "")
            if thinking:
                lines.append(f"{prefix}**ASSISTANT** *(thinking)*\n{thinking}")
        content = data.get("content", "")
        if content:
            lines.append(f"{prefix}**ASSISTANT**\n{content}")
        if mode in (ContentMode.WITH_TOOLS, ContentMode.FULL):
            for tc in data.get("tool_calls", []):
                fn = tc.get("function", {})
                name = fn.get("name", "unknown")
                args = fn.get("arguments", "")
                lines.append(f"{prefix}**TOOL_CALL** `{name}({args})`")
        if not lines:
            return None
        return "\n\n".join(lines)

    if role == "tool":
        if mode in (ContentMode.WITH_TOOLS, ContentMode.FULL):
            content = data.get("content", "")
            if len(content) > 500:
                content = content[:500] + f"\n... [{len(content) - 500} chars truncated]"
            return f"{prefix}**TOOL_RESULT**\n{content}"
        return None

    return f"{prefix}**{role.upper()}**\n{json.dumps(data, default=str)}"


def _build_excerpt(data: dict, query: str, max_len: int = 120) -> str:
    """Build a short excerpt highlighting the query term."""
    text = _extract_searchable_text(data)
    idx = text.lower().find(query.lower())
    if idx == -1:
        return text[:max_len] + "..." if len(text) > max_len else text
    start = max(0, idx - 40)
    end = min(len(text), idx + len(query) + 40)
    excerpt = text[start:end]
    if start > 0:
        excerpt = "..." + excerpt
    if end < len(text):
        excerpt = excerpt + "..."
    return excerpt


def _apply_context_window(
    messages: list[Message],
    match_indices: set[int],
    context: int,
) -> list[Message]:
    """Return messages within `context` messages of any match index."""
    if not match_indices or context <= 0:
        return [messages[i] for i in sorted(match_indices)]

    included = set()
    for idx in match_indices:
        for i in range(max(0, idx - context), min(len(messages), idx + context + 1)):
            included.add(i)
    return [messages[i] for i in sorted(included)]


@mcp.tool
async def query_memory(
    query: str | None = None,
    session_id: str | None = None,
    agent_idx: int | None = None,
    mode: ContentMode = ContentMode.CONVERSATION,
    context: int = 0,
    after: str | None = None,
    before: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> str:
    """Query agent conversation history from the crow database.

    Results are returned newest-first (most recent messages at the top).
    Use `limit` to get the N most recent messages for a session — this is
    the common case for an agent checking what just happened.

    Progressive disclosure:
    - query only (no session_id): discovery mode — search across all sessions
    - session_id only: browse mode — most recent messages in that session
    - session_id + query: deep dive — search within session with context window

    Args:
        query: Search term. None means no text filter.
        session_id: Filter to a specific session. None = search all sessions.
        agent_idx: Filter to a specific agent within a session. If omitted with
            a session_id, defaults to the most recent agent_idx (highest). Pass
            None explicitly to search all agents.
        mode: ContentMode enum controlling what message types to show.
        context: Number of messages around each match (like grep -C). Only applies with session_id.
        after: ISO datetime string. Only messages after this time.
        before: ISO datetime string. Only messages before this time.
        limit: Max results to return (default 50, hard cap 200). Since results
            are newest-first, this is effectively "the N most recent messages."
        offset: Pagination offset (into the past). offset=50 skips the 50 most
            recent messages and returns the next batch.

    Returns:
        Markdown-formatted results — table for discovery, transcript for deep dive.
    """
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)

    with Session(engine) as db:
        # Build base query joining agents for session filtering
        q = db.query(Message, Agent.session_id, Agent.agent_idx).join(
            Agent, Message.agent_id == Agent.agent_id
        )

        if session_id:
            q = q.filter(Agent.session_id == session_id)
            # Default to the most recent agent_idx when not specified.
            # After compaction, a new agent_idx is created — the old one's
            # messages are stale. Without this, queries mix all agents together.
            if agent_idx is not None:
                q = q.filter(Agent.agent_idx == agent_idx)
            else:
                max_idx = db.query(Agent.agent_idx).filter(
                    Agent.session_id == session_id
                ).order_by(Agent.agent_idx.desc()).first()
                if max_idx is not None:
                    q = q.filter(Agent.agent_idx == max_idx[0])
        if after:
            try:
                dt = datetime.fromisoformat(after)
                q = q.filter(Message.created_at >= dt)
            except ValueError:
                return f"Error: Invalid `after` datetime: {after}"
        if before:
            try:
                dt = datetime.fromisoformat(before)
                q = q.filter(Message.created_at <= dt)
            except ValueError:
                return f"Error: Invalid `before` datetime: {before}"

        # Role filtering based on mode
        if mode == ContentMode.CONVERSATION:
            q = q.filter(Message.role.in_(["user", "assistant"]))
        elif mode == ContentMode.WITH_THINKING:
            q = q.filter(Message.role.in_(["user", "assistant"]))
        elif mode == ContentMode.WITH_TOOLS:
            q = q.filter(Message.role.in_(["user", "assistant", "tool"]))
        # FULL: no role filter

        # Order chronologically within each session/agent
        q = q.order_by(Message.id)
        all_results = q.all()

        # If query provided, filter by text content in Python
        # (SQLite JSON search is limited; this keeps us dialect-agnostic)
        if query:
            match_indices = set()
            for i, (msg, _, _) in enumerate(all_results):
                text = _extract_searchable_text(msg.data)
                if query.lower() in text.lower():
                    match_indices.add(i)
            if not match_indices:
                return "No matches found."

            if session_id and context > 0:
                # Deep dive with context window
                messages = _apply_context_window(
                    [r[0] for r in all_results], match_indices, context
                )
            else:
                # Discovery or no context
                messages = [all_results[i][0] for i in sorted(match_indices)]
        else:
            messages = [r[0] for r in all_results]

        # Reverse for newest-first display. Context window was computed in
        # chronological order above; now we flip so the most recent messages
        # come first. offset/limit then paginate backward in time.
        messages.reverse()

        total = len(messages)
        messages = messages[offset : offset + limit]

        if not messages:
            return "No messages found."

        # Discovery mode: markdown table
        if not session_id:
            lines = [
                "| session_id | agent | time | role | excerpt |",
                "|---|---|---|---|---|",
            ]
            for msg in messages:
                # Find the agent info from the joined results
                agent_info = next(
                    (r for r in all_results if r[0].id == msg.id),
                    (None, "?", "?"),
                )
                sess = agent_info[1]
                idx = agent_info[2]
                ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S") if msg.created_at else ""
                role = msg.role
                excerpt = _build_excerpt(msg.data, query or "")
                # Escape pipe chars in excerpt
                excerpt = excerpt.replace("|", "\\|")
                lines.append(f"| {sess} | {idx} | {ts} | {role} | {excerpt} |")
            lines.append(f"\n*Showing {len(messages)} of {total} matches*")
            return "\n".join(lines)

        # Deep dive / browse mode: conversation transcript
        lines = []
        if session_id:
            header = f"## Session: {session_id}"
            if agent_idx is not None:
                header += f" | Agent: {agent_idx}"
            lines.append(header)
            lines.append("")

        for msg in messages:
            # Inject created_at into data for formatting
            msg.data["_created_at"] = (
                msg.created_at.strftime("%H:%M:%S") if msg.created_at else ""
            )
            formatted = _format_message(msg.data, mode)
            if formatted:
                lines.append(formatted)
                lines.append("")

        lines.append(f"*Showing {len(messages)} of {total} messages*")
        return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
