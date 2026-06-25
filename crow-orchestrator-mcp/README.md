# crow-orchestrator-mcp

Orchestrator-only delegation tool. Loaded **in addition to**
[`crow-task-mcp`](../crow-task-mcp) by orchestrator agents; not loaded by
workers.

## Tools

| Tool | Backend ext_method | Purpose |
|------|-------------------|---------|
| `task_send` | `_task/send` | Delegate a batch of tasks to another session. Populates the target's task list, records the caller, and kicks off the target's task loop. On normal completion the backend sends a canned message back to the caller telling it to `query_memory` for the target's final summary. |

## Why a separate server

`task_send` is a delegation capability — it sets up a completion callback
(`set_caller` + `notify_caller_done`) and spawns the target's task loop.
Only orchestrators should advertise it. Keeping it out of `crow-task-mcp`
means:

- workers don't get a delegation tool they shouldn't use
- no duplicate `task_send` schema when an orchestrator loads both servers

Orchestrator agents load **both** servers:

- `crow-task-mcp` → `send_prompt`, `task_read`, `task_write` (manage own session)
- `crow-orchestrator-mcp` → `task_send` (delegate to others)

## Architecture

Schema-only definition for the LLM (`raise NotImplementedError`). Real
execution: `react.py` → `execute_orchestration_task_send` in `tools.py` →
`conn.ext_method(method="task/send")` → sidex client → `sidex-acp` backend
(`orchestration_3.rs::task_send`).

## Run

```bash
uvx crow-orchestrator-mcp
```
