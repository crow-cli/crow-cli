# PLAN — PostgreSQL memory backend (same treatment as RustFS) — COMPLETE 2026-08-26

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Build/test gate (every phase boundary):
`./run_tests.sh tests/unit tests/memory tests/mcp tests/integration -q`
(rustfs sprint ended at 446 green on this gate; live-LLM e2e excluded.)

Trajectory: 1 → 2 → 3 → 4 → 5. Commit after each phase, Session-Id trailer.

## Phase 1 — mechanical portability — DONE 2026-08-26

1. models.py: `from sqlalchemy import JSON` (drop the sqlite dialect import).
2. db.py `_require_v5`: `sqlalchemy.inspect(engine).get_columns("agents")`
   instead of `PRAGMA table_info` — portable, same fail-fast on v4 DBs.
3. pyproject: `psycopg[binary]` dep; `uv --project . sync`.
- Verify: gate green (sqlite behavior untouched). Commit.

## Phase 2 — the FTS seam — DONE 2026-08-26

1. New `src/crow_cli/memory/fts.py`: `create_fts(conn, engine)`,
   `insert_fts(conn, engine, row_id, agent_id, role, fork_idx, text)`,
   `search_fts(conn, engine, query, limit) -> list[(rowid, rank)]`
   (best-first, lower=better on BOTH backends — postgres negates ts_rank).
   sqlite branch = exact current SQL; postgres branch =
   `CREATE TABLE IF NOT EXISTS messages_fts (rowid BIGINT PRIMARY KEY,
   tsv tsvector)` + GIN index; `to_tsvector('simple', :t)` insert;
   `plainto_tsquery('simple', :q)` + `ts_rank` search.
2. db.py create_database → fts.create_fts (drop FTS_DDL constant).
3. writes.py add_message → fts.insert_fts.
4. reads.py search_messages → fts.search_fts (drop inline MATCH SQL).
- Verify: gate green — sqlite search tests pass unchanged. Commit.

## Phase 3 — MCP dialect awareness — DONE 2026-08-26

1. db.py: `get_ro_engine(db_uri)` — sqlite → `?mode=ro&uri=true` rewrite;
   postgres → connect listener `SET SESSION CHARACTERISTICS AS TRANSACTION
   READ ONLY`. Export from memory/__init__.
2. mcp/memory/store.py `_ro_engine`: keep sqlite file-existence check,
   delegate engine creation to get_ro_engine.
- Verify: gate green + new unit tests (sqlite rewrite unchanged; postgres
  branch registers the listener — engine creation needs no live server).
  Commit.

## Phase 4 — init/compose/config (the rustfs treatment) — DONE 2026-08-26

1. defaults.py COMPOSE_YAML: postgres service — postgres:17-alpine,
   `${POSTGRES_PORT}:5432`, POSTGRES_USER/PASSWORD/DB env refs,
   pg_isready healthcheck, postgres_data volume.
2. init_cmd.py Step 2c (mirror 2b): --yes → install; YES_INSTALL_POSTGRES;
   else Confirm.ask. env_vars: POSTGRES_PORT=5432, POSTGRES_USER=crow,
   POSTGRES_DB=crow, POSTGRES_PASSWORD=<env or secrets.token_hex(16)>.
   setup_postgres → db_uri = postgresql+psycopg://${POSTGRES_USER}:
   ${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT}/${POSTGRES_DB};
   compose writer includes postgres; review + done panels reflect backend.
3. config.py apply_config_overrides: resolve_env_vars on db_uri.
4. CONFIG_YAML template: commented postgres db_uri example.
- Verify: tests/unit/test_init_postgres.py (mirror test_init_rustfs.py) +
  gate green. Commit.

## Phase 5 — live e2e + docs — DONE 2026-08-26

1. scripts/e2e_postgres_live.py: ephemeral postgres:17-alpine container
   (port 15432, wait pg_isready); create_database on the postgres URI;
   add_message → search_messages round trip (FTS works, lower=better);
   JSON data round trip byte-identical; claim_deliveries with 2 concurrent
   claimers → exactly one wins; get_ro_engine SELECT ok / INSERT raises;
   kill container in finally; print E2E-POSTGRES-OK.
2. README persistence section: postgres option + when to use it
   (multi-machine state). memory/__init__.py docstring: both backends now.
- Verify: script passes against live container; gate green; commit.

## Evidence log

- Phase 1 (58061203, 2026-08-26): generic JSON + inspector v5 check +
  psycopg 3.3.4 installed; gate 446 passed.
- Phase 2 (73823339): memory/fts.py seam; sqlite search behavior unchanged —
  gate 446 passed.
- Phase 3 (80e72807): get_ro_engine dialect-aware; tests/memory/test_db.py
  (sqlite write actually refused by OS); gate 450 passed.
- Phase 4 (0de9c278): compose service + wizard Step 2c + db_uri env
  resolution; tests/unit/test_init_postgres.py (5 tests); rendered compose
  passes `docker compose config` with live .env interpolation; gate 455.
- Phase 5 (this commit): scripts/e2e_postgres_live.py → E2E-POSTGRES-OK
  against a REAL postgres:17-alpine container: schema+GIN index created,
  tsvector search round trip (lower=better), JSON round trip identical,
  2 concurrent claimers → exactly one delivery claimed, RO engine SELECT ok
  / INSERT refused by the server. README persistence section rewritten.
  Gate 455 passed.

Sprint complete: db_uri picks the backend — postgres config → shared
postgres; absent → sqlite + local FS, exactly as before.
