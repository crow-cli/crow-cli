# TODO — PostgreSQL memory backend (same treatment as RustFS)

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Goal: `db_uri` decides the backend. A postgres `db_uri` in config → postgres
(compose service offered by init, FTS via tsvector/GIN, MCP read-only path
enforced per-dialect). Absent that → sqlite + local FS, exactly as today.
Motivation: central agent state shared across machines (coast-after-3 + this
box) — sqlite has no cross-host story; the task/delivery mailbox design is
already row-level-safe under postgres.

Prior sprint (image object store / RustFS) is COMPLETE — see git history
86c1c474..f114d966. This file replaces it.

## Items (unordered)

- [ ] models.py: swap `sqlalchemy.dialects.sqlite.JSON` → generic
      `sqlalchemy.JSON` (no JSON-operator queries anywhere, so generic is
      correct; keep schema dialect-free).
- [ ] db.py `_require_v5`: PRAGMA table_info is sqlite-only → use SQLAlchemy
      inspector (portable).
- [ ] pyproject: add `psycopg[binary]` dependency (sync driver; engine is
      sync SQLAlchemy throughout). URI form `postgresql+psycopg://`.
- [ ] FTS seam: new `memory/fts.py` owning ALL dialect-specific full-text
      code — create_fts / insert_fts / search_fts. sqlite = FTS5+bm25
      (unchanged behavior); postgres = messages_fts(rowid BIGINT PK, tsv
      tsvector) + GIN index, to_tsvector('simple'), plainto_tsquery,
      ts_rank NEGATED so the contract stays "lower = better, best first"
      (mcp/memory/main.py:359 negates again for display — keep it working).
      Wire into db.create_database, writes.add_message, reads.search_messages.
- [ ] MCP dialect awareness: `get_ro_engine` in memory/db.py — sqlite keeps
      `?mode=ro&uri=true`; postgres gets a connect listener
      `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`. store.py
      `_ro_engine` delegates; sqlite file-existence check stays.
- [ ] defaults.py COMPOSE_YAML: postgres service (postgres:17-alpine,
      POSTGRES_USER/PASSWORD/DB env refs, pg_isready healthcheck,
      postgres_data volume) — same env-ref-credentials pattern as rustfs.
- [ ] init_cmd.py: Step 2c PostgreSQL (mirror Step 2b rustfs: --yes default,
      YES_INSTALL_POSTGRES, Confirm.ask; POSTGRES_PORT/USER/DB/PASSWORD into
      env_vars, password random-default via secrets; db_uri becomes
      postgresql+psycopg://${...}@localhost:${POSTGRES_PORT}/${POSTGRES_DB};
      compose writer includes postgres; review/done panels reflect it).
- [ ] config.py apply_config_overrides: resolve_env_vars on db_uri (load()
      already resolves whole file at line 335).
- [ ] CONFIG_YAML template: db_uri comment shows the postgres option.
- [ ] Tests: tests/unit/test_init_postgres.py (mirror test_init_rustfs.py);
      RO-engine dialect branch tests; fts seam tests (sqlite path = existing
      suite; postgres path = live e2e tier).
- [ ] Live e2e: scripts/e2e_postgres_live.py — ephemeral postgres:17-alpine
      container; create_database; add_message→search_messages round trip;
      JSON data round trip; claim_deliveries exactly-once with 2 concurrent
      claimers; RO engine refuses writes; print E2E-POSTGRES-OK.
- [ ] Docs: README persistence section (postgres option), memory/__init__.py
      docstring ("except FTS5" is now false — both backends supported).
- [ ] Full suite green at every phase boundary; commit per phase with
      Session-Id trailer.

## Decisions (locked)

- Generic `sqlalchemy.JSON`, not JSONB variant: no JSON-operator queries
  exist; keep the schema dialect-free.
- Postgres FTS mirrors the sqlite architecture (side table maintained from
  Python in the same transaction) — NO trigger on messages.data, because
  message_text() extraction logic lives in Python.
- 'simple' ts config for keyword parity with FTS5 (no stemming surprises).
- Score contract preserved: search_messages returns lower=better on both
  backends (ts_rank negated).
- No sqlite→postgres history migration tool this sprint (fresh postgres DB;
  migration is a future task if wanted).
- postgres compose service has NO custom network (default compose network is
  fine; rustfs-network stays rustfs-only).
