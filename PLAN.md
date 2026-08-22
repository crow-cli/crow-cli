# PLAN — consolidation → MCP inversion → fork → interiority

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Worktree: `/home/thomas/src/crow-team/crow-cli-session-fork` (branch `session-fork`).
Dev DB: `~/.agents/crow/crow-2.db` via `dev-crow-2.yaml` — NEVER point dev
work at `~/.agents/crow/crow.db`.

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

## Phase 1 — crow-mcp → crow_cli/mcp
1.1 `git mv crow-mcp/src/crow_mcp crow-cli/src/crow_cli/mcp`; rewrite
    `crow_mcp` → `crow_cli.mcp` imports inside moved code + crow-cli code.
1.2 `git mv crow-mcp/tests crow-cli/tests/mcp`; fix imports; make them run
    under crow-cli's pytest (testpaths).
1.3 Merge crow-mcp's pyproject deps into crow-cli's; drop the `crow-mcp==`
    pin + `[tool.uv.sources]` entry; delete the crow-mcp dir (pyproject,
    uv.lock, README content worth keeping → note in crow-cli README).
1.4 Wire `crow-cli mcp` subcommand (cli/main.py) to the FastMCP server entry;
    update the builtin/default MCP config command to `crow-cli mcp`
    (defaults.py template + get_builtin_mcp_config consumers) so behavior is
    IDENTICAL through this phase.
- Verify: full unit suite green (177 + moved ~115); `crow-cli mcp` boots
  (stdio smoke); E2E gate green. Commit.

## Phase 2 — MCP ownership inversion (client passes, agent doesn't fall back)
2.1 Agent side: strip builtin_config from create_mcp_client_from_acp and from
    new_session/load_session; empty mcpServers = zero tools (remove
    ValueError, mcp_client.py:~112; get_tools returns []).
2.2 Client side: CrowClient/run builds ACP mcp_servers from config.mcp_servers
    (FastMCP dict → McpServerStdio converter; inverse of acp_to_fastmcp_config)
    and passes them to new_session — `crow-cli mcp` included: the CLI passes
    itself through as the MCP server to its own ACP agent.
2.3 Config plumbing: config.yaml mcpServers now consumed by the CLIENT;
    document in defaults template.
- Verify: new unit tests — zero-tool session answers a prompt; client passes
  configured servers; E2E gate green WITH tools (terminal tool reachable) and
  a zero-server config run answers toolless. Commit.

## Phase 3 — crow-memory → crow_cli/memory
3.1 `git mv crow-memory/src/crow_memory crow-cli/src/crow_cli/memory`; rewrite
    `crow_memory` → `crow_cli.memory` (agent/memory.py `import crow_memory as
    db`, mcp/memory/store.py `import crow_memory as cm`, cli/main.py, tests).
3.2 `git mv crow-memory/tests crow-cli/tests/memory`; merge pyproject deps
    (sqlalchemy, coolname), drop pin + source, delete crow-memory dir.
- Verify: full suite green (incl. moved 9 memory tests); E2E gate green.
  Commit.

## Phase 4 — config → crow_cli/config
4.1 Extract Config/load/defaults/get_default_config_dir from
    agent/configure.py into crow_cli/config/ package; agent/configure.py keeps
    only interactive configure UX (or moves to cli/) — all importers updated.
- Verify: full suite green; `crow-cli init`/configure flow intact; E2E gate
  green. Commit.

## Phase 5 — fork-idx (schema v5) on crow-2.db
5.1 memory: agents.fork_idx + messages.fork_idx columns (Integer, default 1);
    agent_id format becomes {session}-{idx}-{fork} everywhere it is
    constructed (session.py create, compact.py, main.py _resolve_session);
    parse via rsplit("-", 2) (coolnames contain hyphens); FTS table gains
    fork_idx UNINDEXED column; agents.forked_at anchor column (message id).
5.2 Migration script: crow.db → crow-2.db copy with `-1` appended to every
    agent_id (agents, messages, FTS) — run it, verify row counts + three-part
    ids + list_sessions/query round-trips on crow-2.db.
5.3 fork_session handler on AcpAgent + use_unstable_protocol=True on
    run_agent AND client connection. _meta agentIdx/turnIdx kwargs (SDK
    flattens them); default = HEAD fork (max agent_idx, all messages);
    turnIdx snaps to turn boundaries (never split tool_calls from results);
    response sessionId = fork's agent_id; zero mcpServers honored (interrogation).
5.4 include_forks=False default on query_session/query_memory/list_sessions
    (MCP tools + CLI telemetry surfaces); session summary/repr shows no fork
    id unless include_forks=True.
5.5 CLI: `--fork` (spawn fork) / `--fork-idx N` (continue fork N) on run.
- Verify: unit tests for schema, migration, fork-at-HEAD, fork-at-turn,
  include_forks filtering; E2E on crow-2.db: fork a real session with zero
  tools, interrogate it, confirm trunk unpolluted + fork persisted +
  `--fork-idx` resumes it. Commit.

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
- Verify: e2e on crow-2.db — delegate a task, parent reacts to the injected
  completion; cancel mid-delegation cancels the delegate; no end_turn emitted
  before completion lands. Commit.

## Phase 7 — cutover (only when 1–6 proven)
7.1 Run migration against the real crow.db (backup first), point default
    config at it, retire dev-crow-2.yaml; update crow-mcp consumers' configs
    (builtin MCP command = `crow-cli mcp`).
- Verify: real-DB round-trip + memory tools green. Commit. Tag.
