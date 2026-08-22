# AGENTS.md

instructions for agents to follow

# ACTIVE SPRINT (2026-08-22)
Consolidation + session-fork + delegation sprint runs in the git worktree
`../crow-cli-session-fork` (branch `session-fork`). Pickup = read that
worktree's `TODO.md` + `PLAN.md` first (mandate headers apply). Design
background: `~/.agents/notes/dev/crow-fork-design.md`.

# RULES
1. Make no mistakes

# RUNNING
Run with: `cd crow-cli && uv --project . run crow-cli`

# ARCHITECTURE — sqlite memory (2026-08-11)
- Persistence lives in the crow-memory package (crow-memory/): SQL storage,
  WAL + busy_timeout=5000, sqlite by default and postgres-ready.
  The db_uri is the ONLY boundary — crow-memory takes no config object.
  crow-cli writes through it (config.db_uri); crow-mcp consumes the same
  package with a read-only engine. crow-mcp NEVER imports crow-cli (MCP is a
  runtime protocol boundary). The db file default is ~/.agents/crow/crow.db.
- Images are files: inline image blocks are extracted to
  `~/.agents/crow/images/<sha256><ext>` at write time (db row stores an
  `image_ref` block) and hydrated to base64 data URLs only when the
  conversation is sent to the LLM.
- Search is FTS5 + bm25 (keyword). No embeddings, no LanceDB, no ColBERT.
- The service era is DELETED (2026-08-11): the Rust crow-memory daemon,
  crow-memory-types, crow-memory-sdk, the root Cargo workspace and the
  vendor/ submodules are gone from the worktree (the Python crow-memory
  package above is its REPLACEMENT, not a resurrection). Daemon management was
  deleted from the CLI (daemon.py/daemon_cmd.py/embeddings.py gone); daemons
  that still run on a machine are supervised externally — NEVER stop/restart
  them from agent code, the user does that himself.
- crow-orchestrator-mcp and crow-task-mcp are DEAD (deleted 2026-08-10).
  Do not resurrect.

# TESTING
- crow-cli: `cd crow-cli && uv --project . run pytest tests/unit tests/integration --run-integration -q`
  (e2e tier is opt-in: add `tests/e2e --run-e2e`, makes live LLM calls)
- crow-mcp: `uv --project crow-mcp run pytest crow-mcp/tests -q`
- crow-memory: `uv --project crow-memory run pytest crow-memory/tests -q`
- Persistence contract lives in crow-memory/tests/test_store.py.
- Versions exist ONLY in each package's pyproject.toml — never hardcode them
  anywhere else (e.g. client/main.py keeps its own literal on purpose).

# GOTCHAS (historical, service era — mostly dead)
- cargo on this laptop: always `-j 2`.
- crates.io still holds crow-memory/crow-memory-types 0.2.0 from an earlier
  ACP-agnostic publish; irrelevant now that the packages are deprecated.
