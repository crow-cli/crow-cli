---
title: Memory Tool Design
---

# Memory Tool Design

## Status: Design Phase

The `query_memory` MCP tool is the primary interface agents have for introspecting their own conversation history. It's used for context recovery, debugging, and cross-session learning. This document collects pain points, design constraints, and proposals for improvement.

---

## Current API

`query_memory` is a single tool with progressive disclosure:

```python
query_memory(
    query: str | None = None,       # Text search term
    session_id: str | None = None,  # Filter to session
    agent_idx: int | None = None,   # Filter to agent within session
    mode: ContentMode = "conversation",  # conversation | with_thinking | with_tools | full
    context: int = 0,               # Messages around each match (grep -C)
    after: str | None = None,       # ISO datetime lower bound
    before: str | None = None,      # ISO datetime upper bound
    limit: int = 50,                # Max results
    offset: int = 0,                # Pagination
) -> str  # Markdown output
```

Three modes of operation:

| Mode | Parameters | Output |
|------|-----------|--------|
| Discovery | `query` only | Table of matching messages across all sessions |
| Browse | `session_id` only | Transcript of messages in session |
| Deep dive | `session_id` + `query` | Search within session, optional context window |

### Database Schema

```
agents (PK: agent_id)
├── agent_id       TEXT     -- "{session_id}-{idx}"
├── session_id     TEXT     -- Logical parent session
├── agent_idx      INTEGER  -- Agent number within session
├── cwd            TEXT     -- Working directory
├── prompt_id      TEXT     -- FK to prompts
├── prompt_args    JSON     -- Template variables
├── system_prompt  TEXT     -- Rendered system prompt
├── tool_definitions JSON   -- Available tools
├── request_params JSON     -- Model params
├── model_identifier TEXT   -- Model used
├── status         TEXT     -- "active", etc.
└── created_at     DATETIME

messages (PK: id, FK: agent_id)
├── data             JSON   -- Full message dict
├── role             TEXT   -- "system" | "user" | "assistant" | "tool"
├── prompt_tokens    INTEGER
├── completion_tokens INTEGER
├── total_tokens     INTEGER
└── created_at       DATETIME
```

---

## Pain Points (from real usage)

### 1. No way to discover sessions

There is no `list_sessions` tool. To find what sessions exist, you need to already know a session_id or search for a term you hope is unique enough. The discovery mode returns *messages*, not *sessions* — so you get duplicate session_ids in the results and no sense of what each session was about.

**Real scenario:** "I worked on something last week, what was it?" → No way to answer this. You can't browse sessions chronologically, search by working directory, or see a title.

### 2. Session metadata is invisible to agents

The `agents` table contains rich metadata: `model_identifier`, `cwd`, `system_prompt`, `tool_definitions`, `created_at`. None of this is surfaced by `query_memory`. An agent browsing a session has no idea what model was used, what tools were available, or what the working directory was.

### 3. No session titles or summaries

Sessions are identified by coolname slugs (`amusing-fragrant-sawfish-of-satiation`). The first user prompt (which is effectively the session title) is buried in message #2 of the `messages` table. There's no denormalized title column and no tool to get one.

### 4. "Show me the last N messages" is awkward

To see the most recent messages in a session, you either:
- Browse the whole session and hope `limit` cuts off at the right place (it doesn't — it's a head, not a tail)
- Guess an `after` timestamp
- Use `offset` with a large value, hoping you know the approximate message count

There's no `last_n`, `tail`, or reverse chronological ordering.

### 5. Mode naming is confusing

The `ContentMode` enum suggests mutual exclusivity but the semantics are additive:

```
conversation    = user + assistant
with_thinking   = user + assistant + reasoning_content  (no tools)
with_tools      = user + assistant + tool_results       (no thinking)
full            = everything
```

If you want thinking *and* tools, you need `full`. There's no `with_thinking_and_tools`. This forces agents to either get too much (`full`) or too little.

### 6. Tool results are truncated at 500 characters with no control

```python
if len(content) > 500:
    content = content[:500] + f"\n... [{len(content) - 500} chars truncated]"
```

Sometimes the tool result *is* the thing you're searching for. A failed build output, an error message, a JSON response — truncation destroys signal.

### 7. Context window is unpredictable

`context=N` expands each match to include N messages before and after. With multiple matches that overlap, results can balloon. There's no way to cap the total output or control deduplication of overlapping context windows.

### 8. Search is substring-only

`_extract_searchable_text` does a simple `query.lower() in text.lower()`. No fuzzy matching, no regex, no field-specific search. You can't search "only in tool calls" or "only in thinking content" or use a regex pattern.

---

## Design Tension: Specific Tools vs Generic API

There are two directions we can take this:

### Direction A: More specific tools

Add purpose-built tools for each use case:

```python
list_sessions(cwd, limit, after, order="desc")
session_summary(session_id)
tail(session_id, last_n=10)
search_tools(session_id, tool_name)
```

**Pros:**
- Each tool is simple and well-documented
- Easy for agents to discover and use correctly
- Output format is predictable
- Low cognitive load per tool

**Cons:**
- Tool sprawl — every new need is a new tool
- Each tool needs its own docstring (token cost in system prompt)
- Agents still can't compose queries ("sessions with >100 messages where tool X failed")
- Maintenance burden on the tool surface

### Direction B: Generic query API

Expose the table structure and let agents compose queries:

```python
query_db(
    table: str,
    columns: list[str],
    where: dict,
    order_by: str,
    limit: int,
)
```

Or go all the way to GraphQL.

**Pros:**
- Composability — any query is possible
- Single tool to learn
- Agents with good reasoning can do complex things

**Cons:**
- **Agents are terrible at this.** A real agent spent ~50k tokens trying to read a single session because it couldn't formulate the right query. It kept hitting the wall of "I don't know the schema" and "I don't know what columns exist" and "I don't know how to join these tables."
- Schema exposure is a surface area problem
- No guardrails against expensive queries
- The output is raw data — agents still need to format/interpret it
- GraphQL adds a runtime, schema definition, and learning curve

### Proposed Middle Ground: Structured queries over pre-canned views

Don't expose raw tables. Instead, expose a small set of *views* (pre-joined, pre-aggregated queries) with a simple filter/sort API:

```python
query_memory(
    view: str = "messages",      # "messages" | "sessions" | "agents" | "tool_calls"
    filters: dict | None = None, # {session_id: "...", role: "assistant", ...}
    order: str = "asc",          # "asc" | "desc"
    limit: int = 50,
    include: list[str] | None = None,  # ["thinking", "tools", "metadata"]
)
```

The views are defined server-side:

- **`sessions`**: One row per session. Columns: session_id, first_prompt, model, agent_count, message_count, total_tokens, created_at, last_activity, cwd, status.
- **`agents`**: One row per agent. Columns: agent_id, session_id, agent_idx, model, cwd, created_at, status, message_count.
- **`messages`**: Current behavior. One row per message.
- **`tool_calls`**: One row per tool call. Columns: session_id, agent_idx, tool_name, arguments, result_summary, success, created_at.

**Benefits:**
- Agents can discover what's available: "what views exist?" → documented list
- Each view has a known schema → no guessing
- `order: "desc"` solves the tail problem
- `include: ["thinking", "tools"]` solves the mode problem
- `filters` is simpler than SQL but more flexible than fixed parameters
- No GraphQL runtime, no schema exposure
- Server-side views can be optimized with indexes

---

## Proposed Changes (prioritized)

### P0 — Must have before the tool is useful for self-introspection

1. **`view: "sessions"`** — List sessions with metadata, ordered by last activity (desc by default). This is the single most important missing capability.
2. **`order: "desc"`** — Reverse chronological ordering for all views. The default should be desc for sessions (newest first), asc for messages (chronological transcript).
3. **`include: list[str]`** replace `mode: ContentMode` — Additive inclusion of `thinking`, `tools`, `metadata`. No more guessing that you need `full` to get both thinking and tools.

### P1 — Important for practical usage

4. **`last_n: int`** — Return the last N messages in a session. Simpler than offset arithmetic.
5. **`tool_result_max_len: int`** — Configurable truncation, default 500, agent can override.
6. **`view: "tool_calls"`** — Search tool calls by name, filter by success/failure.
7. **Session metadata in message output** — When browsing a session, include a header with model, cwd, agent count, message count.

### P2 — Nice to have

8. **`view: "agents"`** — List agents within sessions with their metadata.
9. **`field: str`** — Restrict text search to a specific field (thinking, tool_name, tool_result, user_content).
10. **`regex: bool`** — Enable regex matching for the query parameter.
11. **Context deduplication** — When `context` produces overlapping windows, merge them.
12. **Token budget in output** — Include approximate token cost of the returned data so agents can decide if they need more.

---

## The Session Listing Problem

Listing sessions is harder than it sounds because:

1. **Sessions can have multiple agents** — A session is a logical group of agents. Each agent has its own message stream. Listing sessions means aggregating across agents.

2. **What's the "last activity"?** — It's the `max(created_at)` across all messages for all agents in the session. This is an aggregation query, not a simple SELECT.

3. **What's the title?** — The first user message (typically message id=2, after the system message). This requires a subquery or join.

4. **Inverse chronological order** — Sessions should be listed newest-first by default, but messages within a session should be chronological. The default ordering depends on the view.

5. **Working directory grouping** — Agents often work in the same `cwd`. It would be useful to group or filter by workspace, but `cwd` lives on the agent row, not the session row, and multiple agents in the same session could theoretically have different `cwd` values.

6. **Status** — The `status` column on agents ("active", etc.) is per-agent, not per-session. A session is "active" if any agent in it is active.

The `sessions` view would need to be a proper SQL aggregation:

```sql
SELECT
    a.session_id,
    a.model_identifier,
    a.cwd,
    MIN(a.created_at) as created_at,
    MAX(m.created_at) as last_activity,
    COUNT(DISTINCT a.agent_id) as agent_count,
    COUNT(m.id) as message_count,
    SUM(m.total_tokens) as total_tokens,
    MAX(a.status) as status  -- "active" > other statuses
FROM agents a
LEFT JOIN messages m ON a.agent_id = m.agent_id
GROUP BY a.session_id
ORDER BY last_activity DESC
```

This is why a raw table query won't work — agents can't write this. But a pre-canned view can.

---

## Backward Compatibility

The current `query_memory` signature should remain functional. The view-based approach adds a `view` parameter that defaults to `"messages"`, preserving current behavior. Deprecated parameters (`mode`) can coexist with new ones (`include`) during a transition period.

---

## Feedback Collection

This document is a living record. Update it as:
- New pain points emerge from agent usage
- Performance issues are discovered (large sessions, many agents)
- New query patterns are identified
- The implementation reveals constraints not visible in design

### Known agent anti-patterns to watch for

- Agents browsing entire sessions to find a single fact (should use search)
- Agents re-reading the same session multiple times across conversations (should summarize once)
- Agents failing to paginate and hitting limits silently
- Agents confusing session_id with agent_id
