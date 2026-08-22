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

## Phase 5 — fork-idx (schema v5) on a FRESH dev db
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

## Phase 6 — delegation interiority (delegate tool + park/wake)
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
