"""query_memory MCP tool — backed by the crow-memory service (LanceDB + ColBERT).

Semantic search is the primary discovery mechanism. Keyword (substring) search
is available via search_type="keyword" or "both". Browse mode (session_id only,
no query) uses the filtered message endpoint — this is the critical
message-passing path that must stay fast and correct.
"""

import json
import os
from datetime import datetime
from enum import Enum

import httpx

from crow_mcp.server.main import mcp

MEMORY_URL = os.environ.get("CROW_MEMORY_URL", "http://localhost:8901")
_http = httpx.Client(base_url=MEMORY_URL, timeout=120.0)


def _post(path: str, payload: dict) -> dict | list:
    r = _http.post(path, json=payload)
    r.raise_for_status()
    return r.json()


def _get(path: str, params: dict | None = None) -> dict | list:
    r = _http.get(path, params=params)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Content modes (unchanged)
# ---------------------------------------------------------------------------

class ContentMode(str, Enum):
    CONVERSATION = "conversation"
    WITH_THINKING = "with_thinking"
    WITH_TOOLS = "with_tools"
    FULL = "full"


class SearchType(str, Enum):
    SEMANTIC = "semantic"
    KEYWORD = "keyword"
    BOTH = "both"


# ---------------------------------------------------------------------------
# Formatting helpers (unchanged — pure Python over message dicts)
# ---------------------------------------------------------------------------

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
    messages: list[dict],
    match_indices: set[int],
    context: int,
) -> list[dict]:
    """Return messages within `context` messages of any match index."""
    if not match_indices or context <= 0:
        return [messages[i] for i in sorted(match_indices)]

    included = set()
    for idx in match_indices:
        for i in range(max(0, idx - context), min(len(messages), idx + context + 1)):
            included.add(i)
    return [messages[i] for i in sorted(included)]


# ---------------------------------------------------------------------------
# Role filters per mode
# ---------------------------------------------------------------------------

_MODE_ROLES = {
    ContentMode.CONVERSATION: ["user", "assistant"],
    ContentMode.WITH_THINKING: ["user", "assistant"],
    ContentMode.WITH_TOOLS: ["user", "assistant", "tool"],
    ContentMode.FULL: None,  # no filter
}


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------

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
    search_type: SearchType = SearchType.SEMANTIC,
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
        search_type: How to match `query`. "semantic" (default) uses ColBERT
            MaxSim embedding similarity. "keyword" does substring matching.
            "both" merges semantic + keyword results (deduplicated).

    Returns:
        Markdown-formatted results — table for discovery, transcript for deep dive.
    """
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)

    # Resolve agent_idx default (most recent) when session_id given
    if session_id and agent_idx is None:
        try:
            max_idx = _get(f"/sessions/{session_id}/max-idx")["max_agent_idx"]
            if max_idx >= 0:
                agent_idx = max_idx
        except Exception:
            pass

    roles = _MODE_ROLES.get(mode)

    # ------------------------------------------------------------------
    # BROWSE MODE: session_id, no query
    # ------------------------------------------------------------------
    if session_id and not query:
        recs = _post("/messages/query", {
            "session_id": session_id,
            "agent_idx": agent_idx,
            "roles": roles,
            "after": after,
            "before": before,
            "order": "desc",
            "limit": limit,
            "offset": offset,
        })
        if not recs:
            return "No messages found."

        lines = [f"## Session: {session_id}"]
        if agent_idx is not None:
            lines[0] += f" | Agent: {agent_idx}"
        lines.append("")

        for rec in recs:
            data = rec["data"]
            data["_created_at"] = rec.get("created_at", "")[:19].split("T")[-1] if rec.get("created_at") else ""
            formatted = _format_message(data, mode)
            if formatted:
                lines.append(formatted)
                lines.append("")

        lines.append(f"*Showing {len(recs)} messages*")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # DISCOVERY MODE: query, no session_id
    # ------------------------------------------------------------------
    if query and not session_id:
        if search_type == SearchType.KEYWORD:
            return "Keyword search without session_id is not supported yet. Use semantic search or provide a session_id."

        # Semantic search across all sessions
        hits = _post("/search", {
            "query": query,
            "modality": "text",
            "limit": limit + offset,
        })["messages"]

        # Apply role filter
        if roles:
            hits = [h for h in hits if h["role"] in roles]

        hits = hits[offset:offset + limit]
        if not hits:
            return "No matches found."

        lines = [
            "| session_id | agent | time | role | score | excerpt |",
            "|---|---|---|---|---|---|",
        ]
        for h in hits:
            ts = h.get("created_at", "")[:19].replace("T", " ")
            excerpt = _build_excerpt(h["data"], query).replace("|", "\\|")
            lines.append(
                f"| {h['session_id']} | {h['agent_idx']} | {ts} | {h['role']} "
                f"| {h['score']:.2f} | {excerpt} |"
            )
        lines.append(f"\n*Showing {len(hits)} semantic matches*")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # DEEP DIVE MODE: session_id + query
    # ------------------------------------------------------------------
    # Fetch the full ordered message list for context window + keyword
    all_recs = _post("/messages/query", {
        "session_id": session_id,
        "agent_idx": agent_idx,
        "roles": roles,
        "after": after,
        "before": before,
        "order": "asc",
        "limit": 1_000_000,
        "offset": 0,
    })

    match_indices: set[int] = set()

    # Semantic search
    if search_type in (SearchType.SEMANTIC, SearchType.BOTH):
        sem_hits = _post("/search", {
            "query": query,
            "modality": "text",
            "filters": {
                "session_id": session_id,
                **({"agent_idx": agent_idx} if agent_idx is not None else {}),
            },
            "limit": limit * 2,
        })["messages"]
        if roles:
            sem_hits = [h for h in sem_hits if h["role"] in roles]
        # Map semantic hits to positions in all_recs by message id
        id_to_idx = {r["id"]: i for i, r in enumerate(all_recs)}
        for h in sem_hits:
            idx = id_to_idx.get(h["id"])
            if idx is not None:
                match_indices.add(idx)

    # Keyword search
    if search_type in (SearchType.KEYWORD, SearchType.BOTH):
        q_lower = query.lower()
        for i, rec in enumerate(all_recs):
            text = _extract_searchable_text(rec["data"])
            if q_lower in text.lower():
                match_indices.add(i)

    if not match_indices:
        return "No matches found."

    # Apply context window
    if context > 0:
        messages = _apply_context_window(all_recs, match_indices, context)
    else:
        messages = [all_recs[i] for i in sorted(match_indices)]

    # Reverse for newest-first, then paginate
    messages.reverse()
    total = len(messages)
    messages = messages[offset:offset + limit]

    if not messages:
        return "No messages found."

    # Format as transcript
    lines = [f"## Session: {session_id}"]
    if agent_idx is not None:
        lines[0] += f" | Agent: {agent_idx}"
    lines.append("")

    for rec in messages:
        data = rec["data"]
        data["_created_at"] = rec.get("created_at", "")[:19].split("T")[-1] if rec.get("created_at") else ""
        formatted = _format_message(data, mode)
        if formatted:
            lines.append(formatted)
            lines.append("")

    lines.append(f"*Showing {len(messages)} of {total} messages*")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
