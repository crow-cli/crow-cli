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

## Phase 1 — `task` tool schema prototype (FastMCP experiment)

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

## Phase 2 — task state in sqlite

- 2.1 `tasks` + `task_deliveries` tables (additive v5): see TODO.md for
      columns. deliveries = durable mailbox; status pending|delivered.
- 2.2 memory reads/writes: launch_task / finish_task (STATE FIRST:
      update tasks row + insert delivery in ONE commit) /
      pending_deliveries / mark_delivered / task_by_id / running_tasks.
- 2.3 Cross-process test: writer engine finishes a task, reader engine
      sees the delivery (the MCP-server-process / agent-process split).

Verified when: unit tests green incl. the two-engine case and idempotent
double-finish (a second finish on a terminal task is a no-op).

## Phase 3 — SubagentClient + the wake experiment

- 3.1 WAKE EXPERIMENT (the riskiest unknown, do it early): can an
      AcpAgent emit a synthetic prompt round OUTSIDE any client
      session/prompt — session/update user_message_chunk + agent chunks —
      and have a RecordingClient record it exactly like a client-sent
      turn? Current version never does this (the park lives INSIDE the
      client's open prompt call — that's why the frontend thinks it sent
      the message: the turn never ended). If spontaneous emission breaks
      clients, fall back is documented in the test.
- 3.2 SubagentClient in src/crow_cli/agent/subagent_client.py: spawn
      `python -m crow_cli.agent.main` (pattern: CrowClient.spawn_agent +
      connect_client in src/crow_cli/client/main.py,
      use_unstable_protocol=True), initialize → session/new(cwd,
      mcpServers from get_session_mcp_servers) → session/prompt.
- 3.3 Watcher: owns the child's PromptResponse future; on resolution →
      finish_task (STATE FIRST) → signal per priority/owner state.
- 3.4 session/cancel through the client; child exit/crash paths register
      failed/cancelled, never hang.

Verified when: echo-style tests (no LLM — a scripted child agent or the
real one with a canned model) cover launch, fast-finish, cancel, crash;
the wake experiment records a synthetic round end to end.

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

## Phase 5 — the `task` MCP tool + kill delegate.py

- 5.1 Session context: the crow MCP server process must know its parent
      session id to read mcpServers/task state — implement + test the
      chosen channel (candidate: env var injected at the per-session MCP
      server spawn; the agent owns that spawn).
- 5.2 `task` tool on the crow MCP server (fastmcp), schema from Phase 1,
      body from Phases 2–3: PromptItem(None) → SubagentClient launch;
      PromptItem(session_id) → resume/re-prompt; CancelTurnItem →
      session/cancel (+ follow-up prompt). Returns per-session status
      strings.
- 5.3 DELETE src/crow_cli/agent/delegate.py, DELEGATE_TOOL imports, the
      TaskRegistry in tasks.py (replaced by sqlite state). Nothing may
      reference them afterward (rg comes back empty).
- 5.4 System prompt delegation recipe rewritten for `task`.

Verified when: unit/integration tests drive the tool through a real MCP
client connection (fastmcp in-process client is fine); rg "delegate"
finds no live code path.

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
