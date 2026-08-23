# PLAN — consolidation → MCP inversion → fork → interiority

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Worktree: `/home/thomas/src/crow-team/crow-cli-session-fork` (branch `session-fork`).
Dev DB: `~/.agents/crow/crow-3.db` via `dev-crow-2.yaml` — a FRESH file,
created v5 from scratch (no migration work until the final phase). NEVER
point dev work at `~/.agents/crow/crow.db`.

Build/test commands:
- Unit: `cd crow-cli && uv --project . run pytest tests -q`
- E2E gate (every phase): `cd crow-cli && uv --project . run crow-cli run "say hi" --config-file ../dev-crow-2.yaml`
  (real LLM round-trip; config dir ~/.agents/crow has providers) + an
  ACP-level smoke through the client code (initialize/new_session/prompt).
- Commit after each item with Session-Id trailer.

Trajectory: 0 → 1 → 2 → 3 → 4 → 5 → 6 (user's order, preserved).

## Phase 0 — setup ✅
- [x] Worktree + branch created (fc25a2b2). dev-crow-2.yaml written.
      Verified 2026-08-22: `crow-cli --help` runs in worktree venv.

## Phase 1 — crow-mcp → crow_cli/mcp ✅ (2026-08-22)
- [x] 1.1 `git mv crow-mcp/src/crow_mcp crow-cli/src/crow_cli/mcp`; all
      `crow_mcp` imports rewritten to `crow_cli.mcp` (16 files).
- [x] 1.2 Tests moved to crow-cli/tests/mcp; duplicate tests/mcp/conftest.py
      deleted (root conftest already had identical tier gating).
- [x] 1.3 crow-mcp package deleted; deps merged into crow-cli pyproject
      (fastmcp bumped >=3.4.2, added markdownify/readabilipy/opencv-python/
      pydantic). crow-mcp was never a python dep — it was spawned over stdio.
- [x] 1.4 `crow-cli mcp` subcommand wired (serve() extracted in
      mcp/server/main.py, lazy import in cli/main.py); default config
      template + init_cmd now write stdio `crow-cli mcp`; stdio integration
      test updated to spawn `uv --project <crow-cli> run crow-cli mcp`.
- [x] Sprint dev infra: `--config-file` now threads run → spawn_agent →
      `python -m crow_cli.agent.main` (apply_config_overrides extracted into
      agent/configure.py; acp command uses it too).
- Evidence: 292 passed + 23 skipped (177 cli + 115 mcp); `crow-cli mcp`
  boots; E2E gate green — `crow-cli run "..." -m glm-5.2 --config-file
  dev-crow-2.yaml` round-tripped ("E2E-GATE-OK"), sessions persisted in
  crow-2.db, real crow.db untouched.
- GOTCHA: default model qwen3.8-27b points at llamacpp host coast-after-3
  which is DOWN — E2E gates pass `-m qwen3.8-max-preview`.

## Phase 2 — MCP ownership inversion (client passes, agent doesn't fall back) ✅ (2026-08-22)
- [x] 2.1 Agent side: create_mcp_client_from_acp takes only what the client
      passed (None/[] -> ({"mcpServers": {}}, None)); ValueError gone;
      get_tools(None) -> []; new_session/load_session/_provision_session all
      off the builtin path; Config.get_builtin_mcp_config deleted.
- [x] 2.2 Client side: _run_async loads Config (+--config-file overrides) and
      passes fastmcp_config_to_acp_servers(config.mcp_servers) to BOTH
      new_session and load_session — `crow-cli mcp` rides along as a normal
      mcpServers entry (the CLI passes itself through to its own agent).
- [x] 2.3 CONFIG_YAML defaults template documents mcpServers as client-owned
      (empty/absent = zero tools).
- Evidence: 299 passed + 23 skipped (7 new tests in tests/unit/
  test_mcp_client.py: converter stdio/http/sse, round-trip, zero-tool paths).
  E2E gates green on crow-2.db: WITH tools (dev-crow-2.yaml crow-mcp ->
  terminal tool ran, "E2E-GATE-OK"), zero-server override answered toolless
  (1161), and load_session -s round-trip with passed servers ("LOAD-OK").

## Phase 3 — crow-memory → crow_cli/memory ✅ (2026-08-22)
- [x] 3.1 `git mv crow-memory/src/crow_memory crow-cli/src/crow_cli/memory`
      (internal imports all relative — moved as-is); external importers
      rewritten: agent/configure.py, agent/memory.py (`import crow_cli.memory
      as db`), mcp/memory/store.py (`as cm`), moved test_store.py.
- [x] 3.2 tests moved to crow-cli/tests/memory (default tier, path-gated
      conftest picks them up); pyproject: sqlalchemy>=2.0 added, coolname
      already present, crow-memory pin + [tool.uv.sources] entry dropped;
      crow-memory dir deleted (uv sync uninstalled it).
- Evidence: 308 passed + 23 skipped (299 + the 9 moved store tests); E2E
  gate green on crow-2.db ("PHASE3-GATE-OK").

## Phase 4 — config → crow_cli/config ✅ (2026-08-22)
- [x] 4.1 agent/configure.py had NO interactive UX (that is `crow-cli init`
      in cli/init_cmd.py, untouched), so the whole module moved:
      `git mv agent/configure.py config/config.py` + `git mv agent/default
      config/default`; new crow_cli/config/__init__.py re-exports the public
      API; every importer rewritten (agent/*, cli/*, tests, PyInstaller spec,
      CONFIG_YAML template comment).
- Evidence: 308 passed + 23 skipped; `crow-cli init -d <tmp> -y` writes all
  defaults from the moved templates; E2E gate green on crow-2.db
  ("PHASE4-GATE-OK" via -j JSONL).

## Phase 5 — fork-idx (schema v5) on a FRESH dev db ✅ (2026-08-22)
NO per-phase migration work. Dev runs on a brand-new sqlite file (created
v5 from scratch by create_database); the one-and-only v4→v5 migration of the
real crow.db happens in the FINAL phase, once the schema has settled.

5.1 memory: agents.fork_idx + messages.fork_idx columns (Integer, default 1);
    agent_id format becomes {session}-{idx}-{fork} everywhere it is
    constructed (session.py create, compact.py, main.py _resolve_session);
    parse via rsplit("-", 2) (coolnames contain hyphens); FTS table gains
    fork_idx UNINDEXED column; agents.forked_at anchor column (message id).
5.2 fork_session handler on AcpAgent + use_unstable_protocol=True on
    run_agent AND client connection. _meta agentIdx/turnIdx kwargs (SDK
    flattens them); default = HEAD fork (max agent_idx, all messages);
    turnIdx snaps to turn boundaries (never split tool_calls from results);
    response sessionId = fork's agent_id; zero mcpServers honored (interrogation).
5.3 include_forks=False default on query_session/query_memory/list_sessions
    (MCP tools + CLI telemetry surfaces); session summary/repr shows no fork
    id unless include_forks=True.
5.4 CLI: `--fork` (spawn fork) / `--fork-idx N` (continue fork N) on run.
- Verify: unit tests for schema, fork-at-HEAD, fork-at-turn, include_forks
  filtering; E2E on the fresh dev db: fork a real session with zero tools,
  interrogate it, confirm trunk unpolluted + fork persisted + `--fork-idx`
  resumes it. Commit.
- Evidence: 336 passed + 23 skipped. 5.1 (5c50da4d): three-part ids at every
  construction site, _require_v5 fail-fast, 312 passed + fresh crow-3.db E2E.
  5.2 (aad1d519): wire_session_id addressing (trunk=bare id, fork=agent_id),
  AgentSession.fork + snap_turn_cut (turn anchors never split tool pairs),
  fork_session handler (forked_at message-id anchor, zero-mcpServers
  honored), use_unstable_protocol both ends, ForkSessionCapabilities
  advertised; tests/unit/test_fork.py on a REAL tmp sqlite (FakeMemoryClient
  has no id anchors), memory-layer load_agent_messages/get_max_fork_idx.
  E2E: fork answered ZEBRA-42 from the shared prefix, sqlite showed
  forked_at=6 + fork own-rows-only + trunk unpolluted.
  5.3 (64dd1a00): include_forks=False on list_sessions/query_session/
  query_memory (MCP tools) + `inspect --include-forks`; fork rows/agents/
  hits hidden by default everywhere, verified against the real forked
  session (counts 1/5 default vs 2/7 with flag; fork ids never leak).
  5.4: `run --fork` spawned fork -1-3 (idx incremented past existing fork 2)
  and `run --fork-idx 3` resumed it (model recalled its own fork-only turn);
  trunk still exactly 5 rows; CliRunner validation tests for the flags.

## Phase 6 — delegation interiority (delegate tool + park/wake) ✅ (2026-08-22)
6.1 Task registry: in-process shared state between tools and react loop
    (this is why everything lives in one package now).
6.2 Milestone A — blocking delegation: native delegate tool launches a
    subagent (client code / direct react loop), asyncio.gather over parallel
    delegate tool calls; cancel tree wired (prompt task → delegates).
6.3 Milestone B — park/wake: loop exit condition = model done AND registry
    empty; park on asyncio queue (zero tokens); completion injected as
    synthetic message (never role=tool on the launch's tool_call_id);
    tool_call_update stream keeps the client-side tool call alive; cancel
    kills the whole stack.
- Verify: e2e on the fresh dev db — delegate a task, parent reacts to the
  injected completion; cancel mid-delegation cancels the delegate; no
  end_turn emitted before completion lands. Commit.
- Evidence: 6.1+6.2 (2d8501bd): TaskRegistry (agent/tasks.py) + blocking
  execute_delegate + gather over parallel delegates; E2E parent delegated
  "SUBAGENT-OK" and both sessions persisted. 6.3: delegate tool went
  NON-BLOCKING — launch_delegate provisions the subagent, launches its
  background lifetime (asyncio.create_task, handle on the TaskInfo), returns
  the ack as the launch call's ONE result. React loop exit is now "model
  done AND registry empty AND wake queue empty": otherwise park_until_
  completion awaits the session's queue (zero tokens) with 15s heartbeats
  re-emitting each pending task's tool_call_update surface (`<turn>/<task-N>`
  stays in_progress until the subagent flips it completed/failed). Wake =
  synthetic plain user message `[task-N: delegate <sid> finished]\n<answer>`
  (synthetic_completion_message; also surfaced best-effort as
  user_message_chunk) — never role=tool. Wake queue exists from LAUNCH time
  so a fast subagent can't be lost before the owner's first park. Cancel
  tree: cancel_outstanding_delegates (registry.cancel_all + await handles)
  runs in ALL THREE cancel paths (mid-stream, mid-tool, mid-park); subagents
  cancel their own delegates in their own handlers — the whole stack falls
  together, cancelled state persisted before the cancel response returns.
  prompt() unchanged: the JSON-RPC request stays open across the park (100%
  legal v1). Tests: 361 passed + 23 skipped (test_tasks.py cancel_all +
  launch-time queue; test_delegate.py rewritten for B — ack semantics, full
  park/wake cycle with heartbeat proof, drain path, parallel delegates both
  injected, cancel-during-park persists subagent partial state, cancel-mid-
  batch kills launched delegates). E2E on crow-3.db: parent audacious-
  lobster-of-pastoral-stamina delegated to academic-solemn-fossa-of-debate,
  ended its turn ("Ending my turn now to wait"), was WOKEN by the injection,
  answered DELEGATION-COMPLETE SUBAGENT-OK in the SAME prompt request (no
  premature end_turn — CLI would have exited); sqlite shows ack tool msg +
  synthetic user msg + subagent session intact; no-delegate regression gate
  green.

## Telemetry CLI facade (unphased TODO item) ✅ (2026-08-22)
The MCP query tools as CLI surfaces — same functions, two facades:
`list-sessions` / `query-memory` / `query-session` commands call the exact
functions the MCP server exposes (crow_cli.mcp.memory.main), with the same
include_forks semantics and a --config-file db override (CROW_DB_URI env is
the store's documented hook; the CLI sets it from the overridden Config so
dev-crow-2.yaml points the telemetry at crow-3.db just like `run`).
- Enabling refactor: the FastMCP instance moved to mcp/server/app.py (leaf
  module, fastmcp-only) and crow_cli/__init__, crow_cli/agent/__init__,
  crow_cli/mcp/__init__ became lazy PEP 562 facades — importing the memory
  facade no longer drags in the agent stack or the other tool groups (1.6s
  + terminal-log side effects -> 0.9s, nothing extra loaded). This also
  unmasked a latent import circle (config -> agent.logger -> agent/__init__
  -> agent.main -> compact -> config) that the old eager top-level import
  order happened to dodge; lazy agent/__init__ closes it properly.
  PyInstaller spec pins the lazy modules as hiddenimports.
- Evidence: 368 passed + 23 skipped (7 new tests in tests/unit/
  test_cli_telemetry.py on a real tmp v5 db: listing, browse, search,
  cross-session discovery, include_forks parity, invalid-mode rejection —
  commands run via asyncio.to_thread so their asyncio.run() gets a fresh
  loop). Live smoke on crow-3.db: list-sessions shows the delegation
  sessions; query-session renders the full park/wake transcript (ack ->
  synthetic injection -> final answer); `crow-cli mcp` still boots and
  serves all 11 tools.

## Phase 7 — THE migration + cutover (only when 1–6 proven, schema settled)
The ONE AND ONLY migration. Everything before this phase runs on fresh v5
databases; nothing is ever migrated mid-sprint.
7.1 Write the v4→v5 migration (append `-1` to every agent_id in agents,
    messages, FTS; preserve message ids + created_at). Run it: real
    crow.db → NEW db file (backup the original first), point default config
    at the new db, retire the dev override; update MCP consumers' configs
    (builtin MCP command = `crow-cli mcp`).
- Verify: migrated-DB round-trip + memory tools green + row counts match.
  Commit. Tag.
- 7.1 DONE (script + tests + dry-run on real data): crow-cli/scripts/
  migrate_v5.py (the path _require_v5 already advertises). Source opens
  READ-ONLY and is never modified; destination is created fresh v5; FTS is
  REBUILT with the current message_text extractor; built-in verify() exits
  non-zero on any count/id/created_at drift. Tests: tests/memory/
  test_migrate_v5.py (4 — synthetic v4 DDL copied verbatim from the real
  db; counts/ids/timestamps, memory-layer round-trip incl. search over the
  rebuilt FTS, refuses v5 source + non-crow db). DRY-RUN on a snapshot of
  the REAL crow.db: 1 prompt, 100 agents, 5983 messages migrated +
  verified; list-sessions/query-memory/query-session against the migrated
  copy all green (live session reads back with all 4 compaction agents;
  BM25 finds this sprint's own design messages). 372 passed.
- 7.2 DONE — LIVE migration into crow-2.db (user directive: "migrate the
  crow.db just call it like crow-2.db and validate it works with new code.
  then I can do simple rename offline"). Hardening for migrating a LIVE db:
  the script now pins ONE read transaction (explicit BEGIN; COMMIT moved
  AFTER verify()) so fetches and verification all see the same snapshot
  even with a writer mid-WAL. The retired v4 dev db was preserved first:
  ~/.agents/crow/crow-2.db.pre-v5.bak (WAL consolidated, 29 messages
  verified intact). Migration ran against the LIVE crow.db: 1 prompt,
  101 agents, 6022 messages (+FTS) — verified. VALIDATION against
  crow-2.db with the new code, all green:
    * list-sessions / query-session / query-memory (BM25 over rebuilt FTS)
    * E2E NEW session (create_database idempotent on migrated v5):
      godlike-cooperative-lynx-of-romance replied MIGRATED-DB-OK
    * E2E LOAD: hissing-speedy-seal-of-respect (238 migrated messages)
      hydrated and recalled its design-doc path from hours earlier
    * E2E FORK: --fork of the same session -> wire id
      hissing-speedy-seal-of-respect-1-2, forked_at=trunk HEAD, 2 own
      rows, trunk unpolluted (v5 no-prefix-copy semantics intact)
  Validation exposed + fixed ONE latent bug (7.2b): the -m override at
  load/fork time set _config_values (provider routing + the model config
  option's currentValue) but NOT session.model_identifier — which is what
  react.py sends to the API. Loading a session saved under a dead model
  404'd at the gateway ("Model not exist"). Fix per ACP session config
  options: _apply_model_option() is now the ONE path that applies the
  model option — shared by session/set_config_option and the -m override
  in load_session/fork_session. +4 regression tests (376 passed).
- CUTOVER is now a simple OFFLINE RENAME (user does it when no crow
  process is running). User call 2026-08-22: the migration ALREADY RAN —
  NO re-run; the small stale gap (messages written to crow.db after the
  18:42 snapshot, mostly the tail of the migrating session) is accepted.
    1. mv ~/.agents/crow/crow.db ~/.agents/crow/crow.db.v4-backup
    2. mv ~/.agents/crow/crow-2.db ~/.agents/crow/crow.db
       (config.yaml memory_path already says ~/.agents/crow/crow.db —
       zero config edits; drop dev-crow-2.yaml / validate-crow-2.yaml
       overrides from any consumer still using them)
    3. smoke: crow-cli list-sessions + one `run` round-trip; keep the v4
       backup + crow-2.db.pre-v5.bak until confident, then retire them
       and crow-3.db.
