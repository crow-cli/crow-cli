# crow-task-mcp

Per-session orchestration tools — the "manage your own session" toolset that
**every** agent (workers and orchestrators) loads.

## Tools

| Tool | Backend ext_method | Purpose |
|------|-------------------|---------|
| `send_prompt` | `_send` | Fire-and-forget prompt to another session. Returns immediately; retrieve the response later via `query_session(session_id)`. |
| `task_read` | `_task/read` | Read this session's task list. |
| `task_write` | `_task/write` | Create / update / delete tasks in this session's task list. |

## Architecture

These are **schema-only** definitions for the LLM (`raise NotImplementedError`).
Real execution lives in `crow-cli`:

1. `react.py` dispatches by bare tool name → `execute_orchestration_*` in `tools.py`
2. `tools.py` calls `conn.ext_method(method=...)` over ACP
3. The sidex client routes the ext_method to the `sidex-acp` backend
4. Backend handler: `sidex/crates/sidex-acp/src/tools/orchestration_3.rs`

> `task_send` (batch delegation + completion callback) is **not** here — it
> lives in [`crow-orchestrator-mcp`](../crow-orchestrator-mcp) and is only
> loaded by orchestrator agents. This keeps workers from advertising a
> delegation tool they shouldn't use, and avoids a duplicate-tool-name
> collision when an orchestrator loads both servers.

## Run

```bash
uvx crow-task-mcp
```
