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

## Phase 4 — react loop: kill the hostage machinery, consult state — DONE 2026-08-23

The loop CONSULTS STATE at natural breakpoints — no polling in-loop, no
parking, no hostage. Completions register in sqlite (finish_task lands
them in task_deliveries the moment they arrive); the loop looks at the
mailbox at three points and the quiescent watcher covers the fourth.

- 4.1 DONE. park_until_completion, wake queues, drain_dead,
      synthetic_completion_message, cancel_all propagation — all gone
      from react.py. End-turn check: consult_deliveries() claims ALL
      pending deliveries → inject as synthetic user messages + loop
      continues; none → end_turn.
- 4.2 DONE. Prompt-start drain: consult_deliveries() before the first
      model call — idle arrivals are known at prompt start.
- 4.3 DONE (breakpoint form). After each tool batch:
      consult_deliveries(high_only=True) — highs inject at the next
      batch boundary, lows stay pending for end of turn. Cancelling a
      mid-STREAM model response would need polling in the streaming
      loop (rejected), so the batch boundary is the earliest injection
      point; a high that lands while the session is idle wakes it at
      once via the watcher (below).
- 4.4 DONE. Parent cancel does NOT touch children — the react loop's
      CancelledError handler persists history and re-raises; subagents
      keep running, their completions still land in the mailbox, and
      the model cancels them itself via task(CancelTurn) if it wants.
- 4.5 DONE (the out-of-loop half). AcpAgent._delivery_watcher: one
      asyncio task per session (started at provisioning, cancelled at
      cleanup), polls every DELIVERY_POLL_S=2s. Session lock held
      (active turn) → skip, the in-loop consults own that window.
      Idle + pending → atomic claim, then _run_internal_round with the
      joined delivery contents (Phase 3.1's wake). The claim is a
      single UPDATE...RETURNING (claim_deliveries in memory/writes.py):
      watcher vs in-loop consult can race for the same rows and each
      delivery is still injected EXACTLY ONCE.

Verified when: integration tests cover all three arrival states
(active-low, active-high, idle) with a controllable child; the old
park/wake tests are deleted, not adapted.
Evidence: tests/integration/test_react_loop_tool_round.py
(test_prompt_start_drains_idle_mailbox,
test_low_delivery_held_to_end_of_turn — real sqlite mailbox, scripted
LLM, real react_loop), tests/unit/test_delivery_watcher.py (wake,
skip-while-active, idempotent ensure, no double claim),
tests/memory/test_task_state.py (claim_deliveries: arrival order,
priority filter, cross-engine no-double-claim). 418 passed in the fast
tiers at this commit.

## Phase 5 — kill delegate.py — DONE 2026-08-23

(The `task` tool shipped in Phase 3.2b and its session-context channel
shipped with be2317db: owner attribution rides the tools/call _meta,
injected by execute_acp_task in the react loop — the LLM never sees it
and cannot forge it. What remains is deleting the machinery `task`
replaces.)

- 5.1 DONE. DELETED src/crow_cli/agent/delegate.py and
      src/crow_cli/agent/tasks.py; DELEGATE_TOOL imports, the
      TaskRegistry, the _session_mcp_servers in-process map (sqlite's
      session_mcp_servers row stays the cross-process authority), and
      the registry/session_mcp_servers kwargs from react_loop +
      execute_tool_calls + both react_loop call sites in agent/main.py.
      Tests deleted: unit/test_delegate.py, unit/test_tasks.py,
      e2e/test_delegate_live.py, e2e/test_delegate_true_e2e.py.
- 5.2 DONE (no rewrite needed). The model-facing recipe was
      DELEGATE_TOOL.description itself — it died with the file. The
      `task` tool's own description in mcp/task/main.py is the recipe
      now (launch = PromptItem no session_id; re-prompt = PromptItem
      with session_id; cancel = CancelTurn, optional follow-up). No
      system prompt carried a delegation section (checked
      config/default/defaults.py's SYSTEM_PROMPT and the user's live
      ~/.agents/crow/prompts/system_prompt.jinja2). CLI help text
      updated: agents launch subagents via `task`; `run -s` is the
      human attach recipe.

Verified when: rg "delegate" finds no live code path; an agent with
crow-mcp launches a subagent through `task` with zero delegate code.
Evidence: rg delegate over src/ matches only docstrings/comments
(models.py task-table history note, mcp/memory tool descriptions,
mcp/task module docstring, mcp/editor "delegated to the OS"); zero
imports of the deleted modules anywhere.

## Phase 6 — regression + live E2E + full suite

- 6.1 DONE. tests/e2e/test_delegate_race_experiment.py (the sentinel that
      asserted the hang) rewritten + renamed
      tests/e2e/test_task_race_regression.py: fast child completes
      mid-parent-turn → registered in state → delivered (low: end-turn
      injection) → end_turn fires. The hang is structurally impossible:
      nothing waits on unregistered work. GREEN live (90s) against
      qwen3.8-max-preview. Two e2e isolation lessons baked into it:
      (a) the ACP SDK SILENTLY DROPS mcpServers items that fail schema
      validation — stdio needs name/command/args AND env (a list of
      {name,value}); (b) the mcp stdio spawn gives the child ONLY
      {**get_default_environment(), **server.env} — NOTHING is inherited
      from the agent process, so db/config isolation must ride the wire
      env (CROW_DB_URI / CROW_CONFIG_FILE), which the task tool then
      forwards to the child it launches.
- 6.2 Live E2E (qwen3.8-max-preview): the task tool's own loop is green
      (test_task_mcp_launch.py: launch/completion, mcpServers passthrough,
      cancel, cancel→follow-up, child-crash→failed) and the delivery
      routing is green (6.1 + the watcher/consult units). Remaining: a
      single live run launching TWO subagents, one high one low priority,
      asserting both arrive and the high interrupts first.
- 6.3 Full suite green from the worktree root; then the merge to main is
      the user's call.

Verified when: `uv --project . run pytest tests -q` is all-green, zero
skipped, from a clean checkout of the branch.
