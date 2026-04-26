# Compact & Schema Rewrite - Session → Agent Migration

## Overview

Replaced the `sessions` table with an `agents` table keyed on `agent_id`.
Compaction no longer swaps IDs — it creates a new agent record and `continue`s
the react loop. File snapshots captured via pre-hooks on `write`/`edit` tools.

## Database Schema (v3)

```
agents
├── agent_id (PK)          # "{session_id}-{agent_idx}"
├── session_id (index)     # Logical parent, unchanged across compactions
├── agent_idx              # 1, 2, 3... incremented per compaction
├── prompt_id (FK → prompts)
├── prompt_args (JSON)
├── system_prompt (TEXT)
├── tool_definitions (JSON)
├── request_params (JSON)
├── model_identifier (TEXT)
├── status
├── created_at

file_snapshots
├── id (PK)
├── agent_id (FK → agents, CASCADE)
├── tool_call_id (index)
├── tool_name               # "write" or "edit"
├── file_path
├── content_before (TEXT)   # empty string for new files
├── timestamp

messages
├── id (PK)
├── agent_id (FK → agents, CASCADE)   # was session_id
├── created_at
├── data (JSON)
├── role (index)
├── prompt_tokens / completion_tokens / total_tokens
```

## Key Changes

### 1. `db.py` — Schema Replacement
- `Session` model → `Agent` model
- New `FileSnapshot` model
- `Message` FK: `session_id` → `agent_id`
- `swap_session_id` **deleted** — no more ID gymnastics

### 2. `session.py` — Agent-Centric Session Class
- `Session.__init__` takes `agent_id`, `session_id`, `agent_idx`
- `.session_id` is a property for ACP upstream calls only
- `Session.create()` generates `agent_id = f"{session_id}-{agent_idx}"`
- `Session.load()` loads by `agent_id`
- `swap_session_id` **deleted**
- `update_from` **deleted** — compact returns a fresh Session now

### 3. `compact.py` — Complete Rewrite

**Old approach:** try to summarize the "middle" of the conversation, keep
first/last messages, swap DB IDs in place.

**New approach:**
1. Fill missing tool responses with `"interrupted due to context compaction"`
2. Normalize messages for LLM input
3. Append compaction prompt → send to LLM with `tool_choice="none"`
4. Create **new agent record** with same `session_id`, `agent_idx + 1`
5. Return **new Session** with `[system, user(summary)]`
6. Old agent + all its messages **preserved** in DB — nothing deleted

### 4. `react.py` — Agent ID + Continue After Compact
- `execute_tool_calls(agent_id=..., db_uri="")` — agent_id threading
- `react_loop(agent_id=..., db_uri="")` — same
- After `compact()` returns: **`continue`** back to top of loop
  - LLM gets clean `[system, user]` prompt
  - No stale `tool_call_inputs` executed
  - No "system + assistant" API error

### 5. `tools.py` — Pre-Hook + Agent ID Routing
- `route_to_session_id(agent_id)` strips `-{idx}` suffix for ACP calls
- `capture_file_snapshot()` captures file content before write/edit
- Pre-hook injected into `execute_acp_write` and `execute_acp_edit`
- All function params: `session_id` → `agent_id`
- `conn.session_update()` always uses `session.session_id` (stripped)

### 6. `main.py` (AcpAgent) — Agent ID Everywhere
- `self._agent_id` + `self._session_id` (stripped for upstream)
- All dict keys: `self._sessions[agent_id]`, `self._mcp_clients[agent_id]`, etc.
- `new_session()` generates `agent_id = f"{session_id}-0"`
- `prompt()` resolves ACP `session_id` → `agent_id` for lookups
- `on_compact` callback → `self._sessions[compacted_session.agent_id] = compacted_session`

### 7. `slash.py` — Updated Command Handlers
- All slash commands receive `agent_id` instead of `session_id`
- Dict lookups use `agent_id`

## Internal vs External Keying

| Context | Key Used |
|---------|----------|
| `self._sessions[...]` | `agent_id` |
| `self._mcp_clients[...]` | `agent_id` |
| `self._tools[...]` | `agent_id` |
| `self._cancel_events[...]` | `agent_id` |
| `self._config_values[...]` | `agent_id` |
| `self._state_accumulators[...]` | `agent_id` |
| `self._prompt_tasks[...]` | `agent_id` |
| `conn.session_update(session_id=...)` | `session_id` (stripped) |
| `conn.write_text_file(session_id=...)` | `session_id` (stripped) |
| `NewSessionResponse(session_id=...)` | `session_id` (stripped) |

## Compaction Flow

```
react_loop detects token threshold exceeded
    → compact(session, llm, cwd)
        → fill missing tool responses
        → send to LLM with tool_choice="none"
        → create new Agent record (idx+1, same session_id)
        → return new Session([system, user(summary)])
    → session = await compact(...)
    → continue  ← back to top of loop
    → send_request() → LLM gets [system, user(summary)]
    → LLM responds → react loop continues
    → on_compact callback updates self._sessions dict
```

**Nothing is ever deleted.** Old agent records and their messages remain in the
DB as full history. The new agent record is a fresh start with compressed context.

## Murder Backend Integration

- `GET /api/snapshots/{agent_id}/{tool_call_id}/{file_path:path}` returns `content_before`
- Monaco handles diff rendering — we just serve the pre-mutation content
- Agent's `db_uri` exposed via agent config so Murder can read snapshots

## Testing

9 fixtures generated from real conversation data (`crow-new.db`):

| Fixture | Messages | Missing Tool Responses |
|---------|----------|----------------------|
| case_01_system_user_only | 2 | 0 |
| case_02_reasoning_only | 3 | 0 |
| case_03_content_only | 3 | 0 |
| case_04_unexecuted_tools | 3 | 2 |
| case_05_mid_conversation_all_responded | 7 | 1 |
| case_06_partial_tool_responses | 6 | 2 |
| case_07_complete_turn | 9 | 0 |
| case_08_reasoning_ending | 9 | 0 |
| case_09_content_ending | 9 | 0 |

All tested with **real LLM** (no mocks) — `tool_choice="none"` works correctly,
summaries are coherent, no phantom tool calls, no empty `tool_calls` arrays.

Run: `cd sandbox/repl-agent && uv --project . run test_compact_run.py case_04_unexecuted_tools`
Run all: `uv --project . run test_compact_run.py --all`
