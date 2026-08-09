"""Memory MCP tools — client of the crow-memory HTTP service.

Was: in-process LanceDB + ColBERT via the crow-memory package. Now: talks to
the shared crow-memory service through crow-memory-sdk's async client, so the
MCP server process carries no dataset state at all.

Three tools, split along the backend's own seams:

- list_sessions: sessions ordered by last message activity (who's working now).
- query_memory:  semantic discovery ACROSS all sessions (query required).
- query_session: read/search WITHIN one session, across all its agents by
  default so delegated agents' history is never lost.

query_session's browse path (no query) is the critical message-passing path
that must stay fast and correct.
"""

import json
from enum import Enum

from crow_memory_sdk import MemoryClient, MessageRecord

from crow_mcp.server.main import mcp

#: One process-wide client; the service is local and the tools are chatty.
_client: MemoryClient | None = None


def client() -> MemoryClient:
    global _client
    if _client is None:
        _client = MemoryClient()
    return _client


#: Client-side fetch cap; the server takes a limit, we filter above it.
_FETCH_ALL = 1_000_000


# ---------------------------------------------------------------------------
# Content modes
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
# Formatting helpers (pure Python over message data dicts)
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
    aidx = data.get("_agent_idx")
    if ts and aidx is not None:
        prefix = f"**[{ts} · a{aidx}]** "
    elif ts:
        prefix = f"**[{ts}]** "
    elif aidx is not None:
        prefix = f"**[a{aidx}]** "
    else:
        prefix = ""

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
    messages: list[MessageRecord],
    match_indices: set[int],
    context: int,
) -> list[MessageRecord]:
    """Return messages within `context` messages of any match index."""
    if not match_indices or context <= 0:
        return [messages[i] for i in sorted(match_indices)]

    included = set()
    for idx in match_indices:
        for i in range(max(0, idx - context), min(len(messages), idx + context + 1)):
            included.add(i)
    return [messages[i] for i in sorted(included)]


def _fmt_when(iso: str) -> str:
    """Trim an ISO timestamp to 'YYYY-MM-DD HH:MM' for compact tables."""
    return iso[:16].replace("T", " ") if iso else "—"


def _snippet(data: dict | None, role: str | None, max_len: int = 60) -> str:
    """One-line, pipe-escaped snippet of a message for the sessions table."""
    if not data:
        return "—"
    text = _extract_display_text(data)
    if not text and isinstance(data.get("content"), str):
        text = data["content"]
    text = " ".join(text.split())
    if not text:
        return f"({role or '?'})"
    if len(text) > max_len:
        text = text[:max_len] + "…"
    return text.replace("|", "\\|")


def _render_transcript(
    session_id: str,
    agent_idx: int | None,
    recs: list[MessageRecord],
    mode: ContentMode,
    note: str,
) -> str:
    """Render message records as a markdown transcript, tagged by agent_idx."""
    header = f"## Session: {session_id}"
    if agent_idx is not None:
        header += f" | Agent: {agent_idx}"
    lines = [header, ""]
    for rec in recs:
        data = rec.data if isinstance(rec.data, dict) else {"content": str(rec.data)}
        data = dict(data)  # never mutate the record's payload in place
        data["_created_at"] = rec.created_at[:19].split("T")[-1] if rec.created_at else ""
        data["_agent_idx"] = rec.agent_idx
        formatted = _format_message(data, mode)
        if formatted:
            lines.append(formatted)
            lines.append("")
    lines.append(note)
    return "\n".join(lines)


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
# Session-scoped fetch (the service has no session-scoped query endpoint)
# ---------------------------------------------------------------------------

async def _session_records(
    session_id: str,
    agent_idx: int | None,
    roles: list[str] | None,
    after: str | None,
    before: str | None,
) -> list[MessageRecord]:
    """All of a session's messages (ascending), filtered, across its agents."""
    agents = await client().list_agents(session_id)
    recs: list[MessageRecord] = []
    for a in agents:
        if agent_idx is not None and a.agent_idx != agent_idx:
            continue
        for r in await client().query_messages_by_agent(
            a.agent_id, order_asc=True, limit=_FETCH_ALL
        ):
            if after is not None and r.created_at < after:
                continue
            if before is not None and r.created_at > before:
                continue
            if roles is not None and r.role not in roles:
                continue
            recs.append(r)
    recs.sort(key=lambda r: r.created_at)
    return recs


# ---------------------------------------------------------------------------
# Tool 1: list_sessions
# ---------------------------------------------------------------------------

@mcp.tool
async def list_sessions(limit: int = 50, offset: int = 0) -> str:
    """List agent sessions, most-recently-active first.

    A session can contain multiple agents (delegation). Sessions are ordered by
    their most recent MESSAGE (last activity), not creation time — so this
    answers "who has been working, and when." Dig into one with
    query_session(session_id).

    Args:
        limit: Max sessions to return (default 50, hard cap 200).
        offset: Pagination offset.

    Returns:
        Markdown table: session_id, last active, agent count, message count,
        a snippet of the most recent message, and model / cwd.
    """
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    sessions = await client().list_sessions(limit=limit, offset=offset)
    if not sessions:
        return "No sessions found."

    lines = [
        "| session_id | last active | agents | msgs | last message | model / cwd |",
        "|---|---|---|---|---|---|",
    ]
    for s in sessions:
        if len(s.agent_idxs) > 1:
            agents = f"{s.agent_count} (a{s.agent_idxs[0]}–a{s.agent_idxs[-1]})"
        else:
            agents = str(s.agent_count)
        lm = s.last_message
        snippet = _snippet(lm.data if lm else None, lm.role if lm else s.last_role)
        model_cwd = f"{s.model_identifier or '—'} / {s.cwd or '—'}"
        lines.append(
            f"| {s.session_id} | {_fmt_when(s.last_activity)} | {agents} "
            f"| {s.message_count} | {snippet} | {model_cwd} |"
        )
    lines.append(f"\n*Showing {len(sessions)} sessions*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 2: query_memory (cross-session discovery)
# ---------------------------------------------------------------------------

@mcp.tool
async def query_memory(
    query: str,
    mode: ContentMode = ContentMode.CONVERSATION,
    search_type: SearchType = SearchType.SEMANTIC,
    limit: int = 20,
    offset: int = 0,
) -> str:
    """Search conversation history ACROSS all sessions (discovery).

    Semantic (ColBERT) search over every session. Use this to find WHICH session
    discussed something, then dig in with query_session(session_id). To browse a
    known session or search within one, use query_session.

    Args:
        query: Search term (required).
        mode: ContentMode controlling which message types match and display.
        search_type: "semantic" (default, ColBERT MaxSim) or "both". Pure
            "keyword" is not supported across all sessions — use query_session
            for keyword search within a session.
        limit: Max matches (default 20, hard cap 200).
        offset: Pagination offset.

    Returns:
        Markdown table of matches: session_id, agent, time, role, score, excerpt.
    """
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)

    if search_type == SearchType.KEYWORD:
        return (
            "Keyword search across all sessions is not supported. Use semantic "
            "search here, or query_session(session_id, search_type='keyword') "
            "for keyword search within a session."
        )

    roles = _MODE_ROLES.get(mode)
    hits = await client().search_messages(query, limit=limit + offset)
    if roles:
        hits = [h for h in hits if h.role in roles]
    hits = hits[offset:offset + limit]
    if not hits:
        return "No matches found."

    lines = [
        "| session_id | agent | time | role | score | excerpt |",
        "|---|---|---|---|---|---|",
    ]
    for h in hits:
        ts = h.created_at[:19].replace("T", " ")
        excerpt = _build_excerpt(h.data, query).replace("|", "\\|")
        score = h.score if h.score is not None else 0.0
        lines.append(
            f"| {h.session_id} | {h.agent_idx} | {ts} | {h.role} "
            f"| {score:.2f} | {excerpt} |"
        )
    lines.append(f"\n*Showing {len(hits)} semantic matches*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 3: query_session (read/search within one session)
# ---------------------------------------------------------------------------

@mcp.tool
async def query_session(
    session_id: str,
    query: str | None = None,
    agent_idx: int | None = None,
    mode: ContentMode = ContentMode.CONVERSATION,
    order: str = "desc",
    context: int = 0,
    after: str | None = None,
    before: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    search_type: SearchType = SearchType.SEMANTIC,
) -> str:
    """Read or search a single session's conversation history.

    Spans ALL agents in the session by default (delegation means a session can
    have many agents) — so older agents' messages are never lost. agent_idx is
    shown on every message in the output; pass it as input only to narrow to one
    agent.

    Two ways to use it:
    - Browse (no query): returns recent messages. A bare call returns just the
      tail (the latest message) so you aren't drowned — raise `limit` for more,
      or set order="asc" to start from the first message of the session. Use
      `offset` / `after` / `before` to dig backwards in time.
    - Search (query given): semantic / keyword search within the session across
      all agents, with an optional context window.

    Args:
        session_id: The session to read (required).
        query: Optional search term. None = browse recent messages.
        agent_idx: Optional — narrow to one agent. Default None = all agents.
        mode: ContentMode controlling what message types to show.
        order: "desc" (default) = newest-first (tail); "asc" = oldest-first (head).
        context: Messages around each search match (like grep -C). Search only.
        after: ISO datetime — only messages after this time.
        before: ISO datetime — only messages before this time.
        limit: Max messages. Browse default = 1 (the tail); search default = 20.
            Hard cap 200.
        offset: Pagination offset (into the past when order="desc").
        search_type: "semantic" (default), "keyword", or "both". Search only.

    Returns:
        Markdown transcript (newest-first by default), each message tagged with
        its agent_idx.
    """
    order = "asc" if order == "asc" else "desc"
    offset = max(offset, 0)
    roles = _MODE_ROLES.get(mode)

    if query:
        return await _search_session(
            session_id, query, agent_idx, mode, roles, order,
            context, after, before, limit, offset, search_type,
        )
    return await _browse_session(
        session_id, agent_idx, mode, roles, order, after, before, limit, offset,
    )


async def _browse_session(session_id, agent_idx, mode, roles, order,
                          after, before, limit, offset) -> str:
    if limit is None:
        limit = 1  # bare call = the tail peek, don't drown the agent
    limit = min(max(limit, 1), 200)
    recs = await _session_records(session_id, agent_idx, roles, after, before)
    if order == "desc":
        recs.reverse()
    recs = recs[offset:offset + limit]
    if not recs:
        return "No messages found."
    return _render_transcript(
        session_id, agent_idx, recs, mode,
        note=f"*Showing {len(recs)} messages*",
    )


async def _search_session(session_id, query, agent_idx, mode, roles, order,
                          context, after, before, limit, offset, search_type) -> str:
    if limit is None:
        limit = 20
    limit = min(max(limit, 1), 200)

    # Full ordered list for the context window + keyword matching.
    all_recs = await _session_records(session_id, agent_idx, roles, after, before)

    match_indices: set[int] = set()

    if search_type in (SearchType.SEMANTIC, SearchType.BOTH):
        # The service searches globally; scope to this session's agents
        # client-side (overfetch x4, same trick as the Rust MCP tools).
        agent_ids = {r.agent_id for r in all_recs}
        sem_hits = await client().search_messages(query, limit=limit * 4)
        if roles:
            sem_hits = [h for h in sem_hits if h.role in roles]
        id_to_idx = {r.id: i for i, r in enumerate(all_recs)}
        for h in sem_hits:
            if h.agent_id not in agent_ids:
                continue
            idx = id_to_idx.get(h.id)
            if idx is not None:
                match_indices.add(idx)

    if search_type in (SearchType.KEYWORD, SearchType.BOTH):
        q_lower = query.lower()
        for i, rec in enumerate(all_recs):
            if q_lower in _extract_searchable_text(rec.data).lower():
                match_indices.add(i)

    if not match_indices:
        return "No matches found."

    if context > 0:
        messages = _apply_context_window(all_recs, match_indices, context)
    else:
        messages = [all_recs[i] for i in sorted(match_indices)]

    if order == "desc":
        messages.reverse()
    total = len(messages)
    messages = messages[offset:offset + limit]
    if not messages:
        return "No messages found."

    return _render_transcript(
        session_id, agent_idx, messages, mode,
        note=f"*Showing {len(messages)} of {total} matches*",
    )


if __name__ == "__main__":
    mcp.run()
