# AGENTS.md

instructions for agents to follow

# RULES
1. Make no mistakes

# RUNNING
Run with: `cd crow-cli && uv --project . run crow-cli`

# ARCHITECTURE — sqlite memory (2026-08-11)
- Persistence is an in-process sqlite database (`~/.agents/crow/crow.db`,
  schema v3, WAL + busy_timeout=5000): crow-cli/src/crow_cli/agent/db.py
  (sqlalchemy) owns writes; crow-mcp reads the SAME file read-only with plain
  sqlite3 (crow-mcp/src/crow_mcp/memory/store.py). The sqlite file is the only
  integration point — crow-mcp NEVER imports crow-cli (MCP is a runtime
  protocol boundary).
- Images are files: inline image blocks are extracted to
  `~/.agents/crow/images/<sha256><ext>` at write time (db row stores an
  `image_ref` block) and hydrated to base64 data URLs only when the
  conversation is sent to the LLM.
- Search is FTS5 + bm25 (keyword). No embeddings, no LanceDB, no ColBERT.
- The service era is DELETED (2026-08-11): crow-memory (Rust),
  crow-memory-types, crow-memory-sdk, the root Cargo workspace and the
  vendor/ submodules are gone from the worktree. Daemon management was
  deleted from the CLI (daemon.py/daemon_cmd.py/embeddings.py gone); daemons
  that still run on a machine are supervised externally — NEVER stop/restart
  them from agent code, the user does that himself.
- crow-orchestrator-mcp and crow-task-mcp are DEAD (deleted 2026-08-10).
  Do not resurrect.

# TESTING
- crow-cli: `cd crow-cli && uv --project crow-cli run pytest crow-cli/tests/unit -q`
- crow-mcp: `uv --project crow-mcp run pytest crow-mcp/tests -q`
- Persistence contract lives in crow-cli/tests/unit/test_db.py.

# GOTCHAS (historical, service era — mostly dead)
- cargo on this laptop: always `-j 2`.
- crates.io still holds crow-memory/crow-memory-types 0.2.0 from an earlier
  ACP-agnostic publish; irrelevant now that the packages are deprecated.
