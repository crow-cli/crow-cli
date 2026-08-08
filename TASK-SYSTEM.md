# TASK-SYSTEM — async background tasks with wake-on-completion

Design note. Status: agreed in conversation 2026-08-08, not yet built.
The prior sketch in `~/.crow/notes/dev/crow-cli-critique-sprint-compaction.md`
is superseded by this file.

## Problem

An agent launches long-running work (build, test suite, subagent). Today the
`terminal` tool blocks until the command exits — the agent is stuck inside a
tool call, not promptable, doing nothing. Requirement: launch returns
immediately, the agent goes **idle and stays fully promptable**, and on task
exit an update is delivered to the calling agent that **wakes it**.

## What was rejected (and why)

- **Synchronous blocking wait** (`task_wait` etc.) — the exact opposite of
  the requirement. An agent waiting on background work is idle and must stay
  promptable; the completion event wakes it.
- **Blocking `session/prompt`** while background work runs — backwards, same
  reason.
- **MCP-side callback / MCP-over-HTTP for this.** MCP `2026-07-28` (the
  largest revision since launch) moves deliberately toward a **stateless
  core**: `initialize`/`Mcp-Session-Id` retired, server-initiated requests
  (sampling/elicitation) replaced by Multi Round-Trip Requests, explicitly
  "removing the need for constantly open bidirectional streams". Push/wake
  is being *removed* from MCP's future, not added. Their blessed pattern is
  "mint an explicit handle from a tool and have the model pass it back".
  The new **Tasks extension** (`tasks/get`/`tasks/result`) is
  requestor-driven *polling*, experimental, and rmcp 3.x-only (we're on
  2.2).
- **Internal spawn** (daemon starts the wake turn itself, no prompt on the
  wire). The agent would begin emitting a turn with no record of why — no
  `session/prompt` exists, resume replay can't show it, a second attached
  client sees the agent talking to itself. Doesn't fit.

## Protocol basis (ACP v2)

Source: `~/src/crow-team/agent-client-protocol` (cloned spec).

- `docs/protocol/v2/prompt-lifecycle.mdx:481` — "Background activity **MAY**
  continue and emit other `session/update` notifications while the Agent
  reports `idle`. These notifications do not change the state." Idle is not
  a wire boundary.
- `docs/rfds/v2/prompt.mdx` — the RFD's stated motivation is exactly this:
  the agent may **initiate an interaction** in a session without a user
  prompt (background tasks, subagents).
- `session/update` is strictly **agent→client**. No other party can emit
  one. So the task service can never send a session/update directly — it
  tells the agent, and the agent emits.
- **The wake is a real `session/prompt`** from the task client daemon: it
  lands in history, replays on resume, is attributable, and every attached
  client sees the cause. Compaction-safe — the completion message is just a
  message.

## Architecture

One new workspace crate, `crow-task`, two faces (mirrors crow-cli's own
`acp`/`run` split and crow-memory's server/SDK split).

### `crow-task serve` — resident CLIENT daemon

Declared in `client_settings.yaml`, managed by `crow-cli daemon`,
`requires: [crow-memory]`. Three jobs:

1. **Process supervisor.** Spawns background commands with `setsid`, owns
   the capture (PTY → `~/.agents/crow/tasks/<task_id>.log`), reaps, records
   exit. The process that spawns the child MUST own the child — crow-mcp is
   per-session and dies with the session, so launch cannot live there.
2. **Registry.** A `tasks` table through crow-memory (keeps the
   single-writer LanceDB invariant): `task_id, session_id, command, cwd,
   pid, start_time, status, exit_code, output_path, wake_state`. Output
   stays in the file; only the path goes in the row — no blobs in LanceDB
   (lesson of the multivector-scan sprint).
3. **ACP v2 client** of crow-daemon — `HttpClient` → `:2769`, exactly what
   `run_relay` (main.rs:823) already does. On exit:
   `session/resume(session_id)` → `session/prompt(completion event)`.

### `crow-task mcp` — thin stdio MCP wrapper

Spawned per-session by the agent (`mcp_servers` config), proxies to `serve`
over an SDK. No state in the wrapper — same pattern as crow-memory +
crow-memory-sdk. Session scoping rides `CROW_SESSION_ID` env, injected by
`setup_mcp` at spawn (agent.rs:137; the new-session path may need a
one-line reorder to mint the session id before `setup_mcp` runs).

## Tool surface

- `task_launch(command, cwd?, timeout?)` → `{task_id, pid}`
- `task_status(task_id)` — non-blocking
- `task_list()` — this session's tasks only
- `task_output(task_id, tail?)` — reads the log file
- `task_cancel(task_id)`

**No `task_wait`.** `task_launch`'s description tells the model to go idle
and expect a wake. The tool description is the policy surface. Wake = push
channel; tools = pull channel; both read the same registry. Typed handles
and schema-validated args instead of a skill that says "curl these
endpoints".

Subagents fall out for free: `task_launch("crow-cli run --headless -p
TASK.md")`, wake fires on exit, parent `query_session`s the worker.

## Session scoping (non-negotiable)

- A task is owned by **exactly one session** — the one that launched it.
  The daemon is multi-tenant; tasks are not cross-session.
- The wrapper enforces it: `task_list` shows only this session's tasks;
  `task_status`/`task_output`/`task_cancel` on another session's task is an
  error, not a lookup. No admin backdoor — if an agent needs another
  session's output, it reads the log file path with `read`.
- The wake goes only to the calling session. Never fans out.
- Subagents don't break this: the headless worker's run is the *parent's*
  task; the worker's own session is read via memory after the wake.

## Wake flow

1. Supervisor reaps the child → registry row: `status=exited`, `exit_code`,
   `output_path`.
2. ACP client: `session/resume(session_id)` → `session/prompt(completion
   event)`, tagged via `_meta` as a task-completion event so clients render
   it as a system/task update, not user speech.
3. Daemon runs a normal foreground turn: `state_update: running` → react
   loop → `idle`. The model sees the completion and acts.
4. **Gate race:** if the user is mid-turn, the `compare_exchange` gate
   (agent.rs:655-671) cleanly rejects the wake prompt → taskd retries with
   backoff. The RAII `ForegroundGuard` (ad786a75) is what makes the gate
   safe under panic.

## Edge cases

- **taskd restart:** rows say `running` but children are orphaned →
  re-adopt via `/proc/<pid>` existence + start-time match (guards against
  PID reuse).
- **Dead session:** resume fails → `wake_state=undelivered`, retry lazily;
  the completion is durable in the registry either way.
- **Daemon restart:** sessions reload from memory on resume; the wake path
  is resume→prompt, so it works unchanged.
- **Live streaming of background output:** out of scope for v1. The
  `terminal` tool covers the interactive/live-bytes case; background tasks
  get `task_output` on the captured file.

## Not building

- MCP-over-HTTP for crow-mcp (solves nothing — the wake target is the
  daemon either way).
- MCP Tasks extension (polling, not push; revisit if it stabilizes and we
  want interop).
- Cross-session task access.
- Live output streaming for background tasks (v1).

## Build order

1. Registry (`tasks` table in crow-memory: schema + store methods + HTTP
   endpoints + SDK) — same shape as the images-table work.
2. `crow-task serve` supervisor core: launch/reap/capture + registry writes.
3. Wake client: resume→prompt with backoff + `_meta` event tag.
4. `crow-task mcp` wrapper + `CROW_SESSION_ID` injection in `setup_mcp`.
5. Subagent flow end-to-end.
