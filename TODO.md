# TODO — crow-cli consolidation + session fork + delegation interiority

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Branch: `session-fork` in worktree `/home/thomas/src/crow-team/crow-cli-session-fork`.
ALL dev work runs against a FRESH `~/.agents/crow/crow-3.db` via
`dev-crow-2.yaml` (`crow-cli ... --config-file dev-crow-2.yaml`) — created
v5 from scratch. NO migration work mid-sprint: the one and only v4→v5
migration of the real crow.db is the FINAL phase, when the schema settles.

Design docs: `~/.agents/notes/dev/crow-fork-design.md` (fork identity, FINAL
decision section supersedes earlier same-day sections).

Unordered scope capture:

- [x] Move crow-mcp package into `crow-cli/src/crow_cli/mcp` (defer splitting
      into tool groups). Kill the crow-mcp pyproject/package. `crow-cli mcp`
      becomes the server entry point. (2026-08-22: done, 292 tests green,
      E2E gate green on crow-2.db — see PLAN.md Phase 1 evidence.)
- [x] Invert MCP ownership: agent side (`crow-cli acp`) gets NO builtin/default
      MCP servers; empty mcpServers list = zero tools (kill the ValueError at
      mcp_client.py:112 and the builtin_config fallback in
      create_mcp_client_from_acp). Client side (crow-cli run / CrowClient)
      passes mcpServers from config into new_session — including `crow-cli mcp`
      itself (the CLI passes itself through as the MCP server to its own ACP
      agent). (2026-08-22: done — see PLAN.md Phase 2 evidence.)
- [x] Move crow-memory package into `crow-cli/src/crow_cli/memory`. Kill the
      crow-memory pyproject/package. (2026-08-22: done — see PLAN.md Phase 3
      evidence.)
- [x] Move config out of `crow_cli/agent` into `crow_cli/config` ("because
      everybody's using it!"). (2026-08-22: done — see PLAN.md Phase 4
      evidence.)
- [x] Fork support (schema v5): agent_id = `{session_id}-{agent_idx}-{fork_idx}`,
      all 1-based, trunk carries the pointless `-1`. Update memory, agent, mcp.
      `session/fork` handler reads `_meta` agentIdx/turnIdx (flattened into
      kwargs by the SDK router), default = fork at HEAD (max agent_idx, all
      messages). query_session/query_memory/list_sessions hide forks unless
      include_forks=True; session summary/repr never shows fork id unless
      include_forks=True. (2026-08-22: done — PLAN.md Phase 5 evidence:
      schema v5 + wire ids (5.1), fork_session handler + turn-snapped anchors
      (5.2), include_forks=False everywhere (5.3), `run --fork` /
      `--fork-idx N` (5.4); 336 tests + real E2E forks on crow-3.db.)
- [ ] Migration (FINAL phase, when the schema has settled): the ONE v4→v5
      migration — real crow.db → NEW db file, appending `-1` to every
      agent_id (agents, messages, FTS), preserving message ids/created_at.
      Until then dev just uses fresh v5 databases.
      (2026-08-22: script WRITTEN + PROVEN — crow-cli/scripts/migrate_v5.py,
      4 unit tests on the verbatim v4 DDL, dry-run on a real-crow.db
      snapshot migrated 100 agents / 5983 messages with full verification,
      telemetry green against the migrated copy. Only the CUTOVER remains
      and it must run when no crow process is writing crow.db — see PLAN.md
      Phase 7 for the 4-step procedure.)
- [x] Delegate tool + async task interiority: native delegate tool launches
      subagents; react loop exit condition = model done AND outstanding-task
      registry empty; loop PARKS (asyncio queue wait, zero tokens, no busywork)
      instead of emitting PromptResponse(end_turn); completions injected as
      synthetic messages (NOT role=tool on the original tool_call_id — wire
      contract is one result per call); client-side visualization via
      tool_call_update stream on the still-open tool call; cancel propagates
      down the task tree. session/prompt is A ROUTE to the react loop, not THE
      route. First milestone: parallel blocking delegate calls (asyncio.gather)
      to prove launch/cancel/result plumbing before park/wake.
      (2026-08-22: done — Milestone A blocking (2d8501bd) then Milestone B
      park/wake: non-blocking launch_delegate, park_until_completion +
      heartbeats, synthetic-message wake injection, cancel tree on all three
      cancel paths; 361 tests + real E2E wake cycle on crow-3.db. See PLAN.md
      Phase 6 evidence.)
- [ ] End-to-end testing throughout: every phase punctuated by a real e2e gate
      (real LLM round-trip via `crow-cli run --config-file dev-crow-2.yaml`
      plus ACP-level initialize/new_session/prompt through the client code).
      Keep it working and viable through every big change.
- [x] Telemetry tools in crow-cli mirroring the (now internal) MCP query tools
      — list_sessions/query_session/query_memory as CLI surfaces sharing one
      implementation (dissolves into the consolidation: same functions, two
      facades). (2026-08-22: done — `list-sessions` / `query-memory` /
      `query-session` commands call the MCP tool functions directly, with
      --config-file db override + include_forks parity; enabling refactor
      made the memory facade cheaply importable (lazy PEP 562 package
      inits + mcp/server/app.py). See PLAN.md "Telemetry CLI facade".)
- [x] Zero-tool interrogation e2e: fork a session with no mcpServers, ask it
      "why did you do X", verify trunk unpolluted and fork persisted.
      (2026-08-22: done in the 5.2 gate — fork created with mcp_servers=[],
      answered the secret from the shared prefix, sqlite verified forked_at
      anchor + fork own-rows-only + trunk untouched.)

Explicitly rejected / not doing:
- forked_from column (provenance is already session_id+agent_idx in the row).
- Splitting MCP tools into flag-selectable groups — deferred.
- ACP v2 — interiority first; v2 becomes another adapter later.
- Copying fork prefix messages (prefix is shared trunk rows ≤ anchor).
