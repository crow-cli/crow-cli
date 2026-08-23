# TODO — taskmaster sprint (bg-only task system)

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Unordered scope capture. Ordered execution lives in PLAN.md. Worktree:
`/home/thomas/src/crow-team/crow-cli-taskmaster` (branch
`crow-cli-taskmaster`, from main @ 1c004001). Design context:
`/home/thomas/src/crow-team/task-system-phase1-proposal.md` (v2 doc; this
file SUPERSEDES it — scope was cut to bg-only after sign-off).

## Architecture (the user's words, verbatim where quoted)

- "everything is an mcp tool. all the tool calling happens over MCP
  json-rpc to a separate MCP server. Just like ACP is how clients and
  agents interact with one another, tools and agents are the MCP contract
  and even though they're in the same codebase we couple them together
  through the shared STATE of the sqlite ... the coupling should come from
  the fact they share the same tables and NOT through in-process
  communications"
- "memory/state is more fundamental than the react loop" — completions
  register in STATE first; the loop consults state.
- "no command item. just subagents for now ... NO run_mode. no park. no
  hostage ... just wake up agent with session/prompt. emit to client and
  it will think it sent it"
- "we keep priority. priority determines if we cancel -> prompt or hold
  until end prompt"
- "we want task_update, not just task_cancel. don't dumb down too much" →
  resolved to ONE `task` tool (no task_create/task_read/task_cancel):
  "in fact, why even have a task_create tool? we don't need task_read.
  that's just query_session of the session_id"

## Items

- [x] mcpServers round trip through sqlite (CRITICAL PATH, user-mandated).
      session_mcp_servers table; persisted at session/new, load, fork;
      readable by a separate process; explicit [] = explicitly toolless.
      Verified 2026-08-23: 14 tests green (5 memory round-trip incl.
      two-engine cross-process, 9 wiring incl. real ACP objects +
      parse-back fidelity), 413 fast-tier tests green. Commit on
      crow-cli-taskmaster.
- [x] ONE `task` MCP tool (on the crow MCP server, separate process):
      `updates: list[PromptItem | CancelTurnItem]`, discriminated union.
      PromptItem{prompt, session_id=None, priority, model?}: session_id
      None → launch NEW subagent; set → re-prompt existing session
      (session/load when not live — we do NOT emit history to the
      client, and that's fine). CancelTurnItem{session_id, prompt=None}:
      session/cancel if running + optional follow-up prompt in one call.
      Verified 2026-08-23: FastMCP prototype proved the discriminator is
      REQUIRED (naive union parses one dict as both variants — Phase 1,
      930307ef); the real tool shipped in src/crow_cli/mcp/task/ with
      dispatch-guard units (a6211824) + 5 live e2e (6d9316aa + crash
      path).
- [x] Kill the in-process delegate: launch_delegate/_run_subagent/
      _DelegateConn, park_until_completion, wake queues, drain_dead,
      cancel_all propagation, DELEGATE_TOOL. The in-process react loop
      nesting is VERBOTEN — subagents are real ACP agents driven by an
      ACP client. DONE 2026-08-23 (Phase 4+5): delegate.py + tasks.py
      DELETED; react.py consults sqlite at breakpoints instead
      (consult_deliveries + atomic claim_deliveries); rg delegate over
      src/ matches only docstrings/comments.
- [x] Subagent transport: spawn `python -m crow_cli.agent.main`
      subprocess (frozen builds: `crow` acp subcommand — the proven
      CrowClient.spawn_agent pattern, now SHARED via
      spawn_agent_process in src/crow_cli/client/subagent.py); drive it:
      initialize → session/new(cwd, mcpServers FROM THE SQLITE ROUND
      TRIP) → session/prompt; session/cancel for CancelTurn. Watcher
      owns the child's PromptResponse future; on resolution — STATE
      FIRST (tasks row + task_deliveries row), then signal. Verified
      2026-08-23: b139549e (driver) + live e2e incl. crash path.
- [x] Task state in sqlite: `tasks` + `task_deliveries` tables (additive
      v5, no migration drama). tasks: task_id, kind=subagent,
      owner_session (wire id), tool_call_id, sub_session, prompt, model,
      priority, status(running|completed|failed|cancelled), result,
      created/finished. task_deliveries: durable mailbox — completions
      land here THE MOMENT THEY ARRIVE, in a separate process if needed;
      drained by the agent process. Survives process death: even if the
      MCP server process that spawned a child dies, the child's session
      persists in sqlite and task(Prompt, session_id) can resume it.
      Verified 2026-08-23: 51437954, 8 state tests green incl.
      two-engine cross-process; + set_task_sub_session/reopen_task/
      task_by_sub_session/count_tasks (a6211824).
- [x] Delivery (bg-only, priority decides): completion arrives while
      owner ACTIVE + priority low → HELD, injected before end_turn (loop
      continues; end_turn fires only when model done AND nothing
      registered in the meantime). Owner ACTIVE + priority high →
      injected at the next tool-batch boundary (the earliest breakpoint;
      cancelling a mid-STREAM response would need in-loop polling, which
      is rejected). Owner IDLE → the per-session delivery watcher claims
      the row and wakes a synthesized internal round: emit session/update
      (user_message_chunk + the agent turn) so the client renders it as
      if IT had prompted. DONE 2026-08-23 (Phase 4): consult_deliveries
      at prompt-start / after-batch(high) / end-turn, plus
      AcpAgent._delivery_watcher for the idle case; the atomic
      claim_deliveries guarantees each delivery injects exactly once
      even when the consults and the watcher race. Verified: 2 react-loop
      integration tests (active-low held, prompt-start drain) + 4 watcher
      units + 3 claim units.
- [x] The wake experiment (answers "how did the current version make the
      frontend think it sent the message?"): current version never emits
      outside an open prompt — the park happens INSIDE the client's
      session/prompt call, so the turn just keeps streaming. The idle
      wake is NEW territory: session/update with no outstanding prompt
      request. Verified 2026-08-23 (de4e6596): _run_internal_round
      proved live — synthetic user chunk first, model reacts, history
      persisted, NO client request in flight.
- [x] Cancel semantics v1-style: NO propagation — cancelling the parent
      does not touch children (bg keeps running). The MODEL cancels
      subagents explicitly via task(CancelTurn) → session/cancel over the
      child's connection, mid-turn. DONE 2026-08-23 (Phase 4): react.py's
      CancelledError handlers persist history and re-raise WITHOUT
      touching the registry (there is none); the old
      cancel_outstanding_delegates tree-kill is deleted.
- [x] Session context for the task tool: the MCP server process must
      know WHICH session's mcpServers/task state to use. DECIDED +
      SHIPPED (be2317db): owner attribution rides the tools/call _meta —
      the react loop intercepts tool_name == "task" (execute_acp_task,
      same family as the old execute_orchestration_* fns) and passes the
      calling session's wire id; the tool's Context param is filtered
      out of the LLM schema, so the model can neither see nor forge it.
      Env injection replaced as a hack. Config context for children
      still rides CROW_CONFIG_FILE/CROW_CONFIG_DIR process env.
- [x] System prompt: delegation recipe rewritten for `task` (launch =
      PromptItem no session_id; check on children = query_session;
      cancel/re-prompt = CancelTurnItem/PromptItem with session_id).
      DONE 2026-08-23 (Phase 5): the recipe was DELEGATE_TOOL.description
      itself — it died with the file. The `task` tool's own description
      (mcp/task/main.py) is the model-facing recipe now. No system prompt
      carried a delegation section (checked the SYSTEM_PROMPT default and
      the live user prompt file). CLI `run` help updated to match.
- [x] Race experiment → regression test: fast child completes
      mid-parent-turn → completion REGISTERS in state → injected (low) →
      end_turn fires. Hang impossible: nothing waits on unregistered work.
      DONE 2026-08-23 (Phase 6.1): the sentinel
      tests/e2e/test_delegate_race_experiment.py (asserted the hang) is
      rewritten + renamed tests/e2e/test_task_race_regression.py — now
      asserts end_turn inside the window, task-1 terminal in state, and
      the delivery injected into the parent's history (in-loop consult or
      the quiescent watcher).
- [ ] E2E live LLM (qwen3.8-max-preview; llamacpp host coast-after-3 is
      DOWN): task launch over the ACP spawn, completion delivered both
      ways; full suite green (all tiers mandatory). PROGRESS 2026-08-23:
      the task tool's own e2e is green (launch/completion/passthrough/
      cancel/follow-up/crash — 6d9316aa); the delivery-routing half is
      now green too — race regression (fast child mid-parent-turn →
      registered → delivered → end_turn) live in 90s, plus the watcher +
      consult units. Remaining: the two-subagent high/low live run (PLAN
      6.2) and the final all-tiers sweep.

## Deferred (explicitly NOT Phase 1 — user cut them)

- fg / run_mode / waiting state ("see if it's even a problem" — v1
  protocol hack; ACP v2 is "outside the end_turn" focused).
- Command tasks (async terminal) + task_read / log tail (tmux-view).
  task_read is trivially query_session for subagents.
- Default crow-mcp server vs `--no-default-tools` flag; client-side-only
  mcpServers docs ("a new flag is probably warranted" — later).
- Fork-delegate interrogation route: `--call-no-tools` for --fork /
  --fork-idx → react.py tool_choice "auto"→"none" (the exxon-valdez
  "interrogate the state, don't give it the wheel" use case).
- Routing child session/updates to the client with attribution headers
  ("from {coolname}", like compaction announcements), priority/
  chronological ordering while the parent is unresponsive.
- HTTP transport for children (daemon direction) — stdio first.
- Prompt queueing to a subagent beyond CancelTurn's single follow-up.
