# PLAN — taskmaster sprint (bg-only task system)

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Build/test (ALL tiers mandatory, every run):

    cd /home/thomas/src/crow-team/crow-cli-taskmaster
    uv --project . run pytest tests -q

e2e uses the live model qwen3.8-max-preview (alibaba); the default
llamacpp host coast-after-3 is DOWN. Every commit ends with the agent's
`Session-Id:` trailer. Scope capture + the user's verbatim architecture
quotes: TODO.md. Current trajectory: 0 → 1 → 2 → 3 → 4 → 5 → 6.

One-liner: all tool calling is MCP JSON-RPC to a separate process; ACP is
the client↔agent contract; the coupling between the two is SHARED SQLITE
STATE, never in-process communication. Subagents are real ACP agents the
task tool spawns as subprocesses and drives as an ACP client. Priority
decides delivery: high = cancel→prompt, low = hold to end of prompt. No
run_mode, no park, no hostage, no fg.

---

## Phase 0 — mcpServers round trip through sqlite — DONE 2026-08-23

The user-designated critical path: the task tool (separate MCP server
process) must read the parent session's client-defined mcpServers from
sqlite to pass them through to the delegated agent.

- 0.1 `session_mcp_servers` table (session_id PK, servers JSON,
      updated_at) + `set_session_mcp_servers` / `get_session_mcp_servers`
      in memory writes/reads. Additive — create_all picks it up, zero
      migration drama on live dbs.
- 0.2 `MemoryClient` async wrappers; `_mcp_servers_to_wire`
      (model_dump(mode="json", exclude_none=True)) in agent/main.py;
      persisted at session/new, session/load, fork_session — keyed by
      WIRE id exactly like the in-process map. Hydration
      (_provision_session) never overwrites the saved row.
- 0.3 FakeMemoryClient gains the same surface (+ query_messages,
      get_max_fork_idx the fork path needs).

Verified: tests/memory/test_session_mcp_servers.py (5, incl. two-engine
cross-process + explicit-[] toolless) and
tests/unit/test_session_mcp_servers_wiring.py (9, incl. real ACP objects
→ wire dicts → parse-back equality; real ACP shapes learned the hard way:
name required, env/headers are {name,value} lists, type const explicit).
413 fast-tier tests green.

## Phase 1 — `task` tool schema prototype (FastMCP experiment) — DONE 2026-08-23

EXPERIMENT FIRST: before any plumbing, prove the tool shape.

- 1.1 Prototype in tests/unit: FastMCP tool `task(updates:
      list[PromptItem | CancelTurnItem])`. PromptItem{action="prompt",
      prompt, session_id=None, priority="low", model=None};
      CancelTurnItem{action="cancel", session_id, prompt=None}. The two
      item types have OVERLAPPING fields ({prompt, session_id} both
      optional-ish) — the hypothesis is an explicit discriminator is
      REQUIRED; prove the ambiguity fails/misparses without it and the
      discriminated union round-trips.
- 1.2 Dump the schema the model would see (FastMCP → tool parameters);
      assert it names both variants and the discriminator.
- 1.3 Call the tool through FastMCP with model-shaped args (launch,
      re-prompt, cancel+follow-up in ONE updates list) and assert the
      parsed pydantic objects.

Verified when: the prototype tests are green and the generated schema is
something a model can follow (eyeball it in the test output once).

Verified: tests/unit/test_task_tool_schema.py — 8 green. Ambiguity proven
(one dict validates as BOTH naive variants); discriminated union parses
launch/re-prompt/cancel+follow-up; omitted action REJECTED (pydantic
discriminator is strict — the model must state intent, the schema marks
action const per variant); model-visible schema names PromptItem +
CancelTurn + action + high/low; mixed batch round-trips through the real
FastMCP call path; unknown action rejected, not guessed.

## Phase 2 — task state in sqlite — DONE 2026-08-23

- 2.1 `tasks` + `task_deliveries` tables (additive v5): see TODO.md for
      columns. deliveries = durable mailbox; status pending|delivered.
- 2.2 memory reads/writes: launch_task / finish_task (STATE FIRST:
      update tasks row + insert delivery in ONE commit) /
      pending_deliveries / mark_delivered / task_by_id / running_tasks.
- 2.3 Cross-process test: writer engine finishes a task, reader engine
      sees the delivery (the MCP-server-process / agent-process split).

Verified when: unit tests green incl. the two-engine case and idempotent
double-finish (a second finish on a terminal task is a no-op).

Verified: tests/memory/test_task_state.py — 7 green: launch registers
running state cross-engine; finish flips status AND lands the delivery in
ONE commit (read back through a second engine); double-finish no-op;
unknown-task no-op; mark_delivered drains in arrival order; priority rides
both rows; mailboxes per-session.

## Phase 3 — client driver + task tool + live e2e — DONE 2026-08-23

Placement (user-corrected, verbatim): "IT PROBABLY SHOULD BE SPLIT
INTELLIGENTLY BETWEEN CLIENT AND MCP" — client package owns the ACP
machinery (headless, no state knowledge), mcp package owns the `task`
tool (schema + sqlite coupling + dispatch), agent package gets NOTHING
new. The two couple through sqlite, never in-process.

- 3.1 WAKE EXPERIMENT — DONE (de4e6596): `_run_internal_round` in
      agent/main.py, synthetic round with NO client request; live-model
      e2e green (tests/e2e/test_wake_experiment.py). Race sentinel
      converted (150s, expects the hang) — flips into the regression at
      Phase 6.1.
- 3.2a CLIENT DRIVER — DONE (b139549e): src/crow_cli/client/subagent.py —
      spawn_agent_process() free fn, HeadlessClient (swallows updates;
      fs/permission = method_not_found), SubagentDriver (start/
      new_session/load_session/prompt/cancel/close; terminal=False at
      handshake). CrowClient.spawn_agent delegates to the shared spawn
      fn — one spawn path.
- 3.2b THE TASK TOOL — DONE (a6211824): src/crow_cli/mcp/task/main.py —
      ONE `task` tool, `updates: list[PromptItem | CancelTurn]`
      discriminated on action (Phase 1 models promoted). Launch: STATE
      FIRST → driver start → session/new with the OWNER's mcpServers
      passthrough (Phase 0 round trip consumed) → watcher. Re-prompt:
      live mid-turn refuses; terminal row reopens + session/load (the
      agent implements load, NOT resume). Cancel: driver.cancel() →
      pending prompt resolves cancelled; optional follow-up reopens the
      row and the watcher loop continues. New state fns:
      set_task_sub_session, reopen_task, task_by_sub_session,
      count_tasks (task-N numbering). Owner attribution: the agent
      intercepts tool_name == "task" and passes the calling session's
      wire id through the tools/call _meta — execute_acp_task +
      task(updates, ctx: Context), Context filtered out of the LLM
      schema (be2317db; replaced env injection, which was a hack).
      Config context for children still rides CROW_CONFIG_FILE/
      CROW_CONFIG_DIR process env. Registered in server/main.py.
- 3.3 LIVE E2E — DONE (6d9316aa): tests/e2e/test_task_mcp_launch.py —
      launch→completion (answer lands in the delivery), mcpServers
      passthrough (child USES the passed-through terminal tool: date
      output in its answer — [] cascade stays dead), cancel mid-turn,
      cancel→follow-up (one delivery, follow-up answered). Isolation =
      production shape: CROW_DB_URI for the tool, CROW_CONFIG_FILE
      (same tmp db) for the child.
- 3.4 CRASH PATH — DONE (this commit): SIGKILL the child mid-turn →
      watcher's prompt future breaks on the dead transport → failed
      status + delivery, never hangs (test_child_crash_registers_failed).

Found en route (3.3): the SDK SILENTLY DROPS mcpServers request items
that fail validation (a stdio dict missing the required env list
vanished; the child came up toolless with no error anywhere). The driver
now parses wire dicts item-by-item BEFORE sending (_parse_mcp_servers —
loud failures, fills required-but-emptyable args/env); pinned by
tests/unit/test_subagent_parse_servers.py. Also observed: a child that
still carries DELEGATE_TOOL may delegate instead of using its
passed-through tools — structurally resolved by Phase 5.3's deletion.

## Phase 4 — react loop: kill the hostage machinery, consult state

- 4.1 Delete park_until_completion, wake queues, drain_dead, cancel_all
      propagation; react exit condition returns to "model done" — then
      the NEW end-turn check: pending low-priority deliveries registered
      during this turn → inject as synthetic user messages, loop
      continues; none → end_turn.
- 4.2 Prompt-start drain: pending deliveries (idle arrivals) injected
      before the first model call.
- 4.3 High priority: owner-active delivery cancels the in-flight turn
      (the prompt task), then a synthesized round delivers it
      (cancel→prompt). Owner-idle: synthesized round at once.
- 4.4 Parent cancel does NOT touch children (bg semantics).

Verified when: integration tests cover all three arrival states
(active-low, active-high, idle) with a controllable child; the old
park/wake tests are deleted, not adapted.

## Phase 5 — kill delegate.py

(The `task` tool shipped in Phase 3.2b and its session-context channel
shipped with be2317db: owner attribution rides the tools/call _meta,
injected by execute_acp_task in the react loop — the LLM never sees it
and cannot forge it. What remains is deleting the machinery `task`
replaces.)

- 5.1 DELETE src/crow_cli/agent/delegate.py, DELEGATE_TOOL imports, the
      TaskRegistry in tasks.py (replaced by sqlite state). Nothing may
      reference them afterward (rg comes back empty). This also removes
      the child's ability to delegate instead of using its passed-
      through tools (observed in Phase 3.3).
- 5.2 System prompt delegation recipe rewritten for `task` (launch =
      PromptItem no session_id; checking on children = query_session;
      cancel/re-prompt = CancelTurn / PromptItem with session_id).

Verified when: rg "delegate" finds no live code path; an agent with
crow-mcp launches a subagent through `task` with zero delegate code.

## Phase 6 — regression + live E2E + full suite

- 6.1 tests/e2e/test_delegate_race_experiment.py rewritten as the
      regression: fast child completes mid-parent-turn → registered in
      state → delivered (low: end-turn injection; high: cancel→prompt) →
      end_turn fires. The hang is structurally impossible: nothing waits
      on unregistered work.
- 6.2 Live E2E (qwen3.8-max-preview): launch two subagents via `task`,
      one high one low priority; both completions arrive correctly;
      cancel one mid-flight via CancelTurn.
- 6.3 Full suite green from the worktree root; then the merge to main is
      the user's call.

Verified when: `uv --project . run pytest tests -q` is all-green, zero
skipped, from a clean checkout of the branch.
