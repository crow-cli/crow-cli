# crow-cli PLAN — sqlite fallback sprint (2026-08-11)

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

User mandate (verbatim gist): "go back to clean and simple but with the wrinkle
of 'save images to config.config_dir / "images" instead of directly in blob.
instead of image data, keep file location, hydrate/replace uri with base64 data
on sending to LLM'". db.py with sqlalchemy types back in crow-cli. No lancedb,
no embeddings — crow-mcp reads ~/.agents/crow/crow.db with sqlite and search is
BM25 (FTS5) instead of ColBERT MaxSim. NO DATA MIGRATION ("we do not give a
single fuck about migrating data"). Everything after db.py + hydration is
deleting files. MCP stays a runtime protocol boundary: crow-mcp NEVER imports
crow-cli — the sqlite file is the only integration point. Don't overcomplicate.

Build/test: `cd crow-cli && uv --project crow-cli run pytest crow-cli/tests/unit -q`
and `uv --project crow-mcp run pytest crow-mcp/tests -q`.

All phases complete (1 → 2 → 3 → 4).

## Phase 1 — db.py back in crow-cli
1.1 [x] Re-add `sqlalchemy` to crow-cli pyproject.
1.2 [x] `crow-cli/src/crow_cli/agent/db.py`: schema v3 (prompts/agents/messages;
    one row = one message; JSON data col) + engine pragmas (WAL,
    busy_timeout=5000, synchronous=NORMAL) + FTS5 `messages_fts` (agent_id/role
    unindexed + extracted text, bm25 rank) synced in add_message + image
    extract/hydrate (files `images_dir/<sha256hex><ext>`, blocks
    `{"type":"image_ref","path","mime"}`; hydrate swaps to base64 data URL) +
    helpers: create_database, add_message, load_messages, list_sessions,
    search_messages, get/create agent, lookup_or_create_prompt.
    Verify: crow-cli/tests/unit/test_db.py — image roundtrip, bm25 hit/miss,
    two-engine concurrent write smoke, list_sessions ordering.

## Phase 2 — rewire crow-cli agent
2.1 [x] session.py: MemoryClient → db.py; db_uri/images_dir from Config
    (config_dir/crow.db, config_dir/images).
2.2 [x] react.py / main.py / compact.py / cli inspect: follow the new seam;
    hydrate image_ref → base64 ONLY when building the LLM request.
2.3 [x] Delete agent/memory.py (rewrote as sqlite adapter; interface kept) SDK wrapper; drop dead config keys
    (memory URL/retry budget).
    Verify: crow-cli unit suite green; live smoke: persist message with inline
    image → row has image_ref, file on disk, hydrated payload has data URL.

## Phase 3 — crow-mcp memory tools on sqlite + BM25
3.1 memory/main.py: drop crow_memory_sdk; thin local sqlite reader (own engine,
    same pragmas); query_memory/query_session keyword = FTS5 bm25; docstrings
    say keyword/BM25.
3.2 Restart crow-mcp; verify list_sessions/query_session/query_memory return
    real rows (this session visible). crow-mcp suite green.

## Phase 4 — delete daemon management from the CLI (done)
4.1 [x] Deleted daemon.py, daemon_cmd.py, embeddings.py (ollama-mv provisioning),
    test_daemon.py, test_embeddings.py, main.py registration, init_cmd.py
    steps 5+6 (ollama-mv build + daemon start), stale service-era
    integration test in crow-mcp.
4.2 [x] defaults.py template: memory_path → crow.db, retry-budget block deleted;
    init writes sqlite facts, no daemon promises.
4.3 [x] READMEs (root, crow-cli, crow-mcp) + monorepo AGENTS.md: sqlite story,
    crow-memory*/sdk marked deprecated.
4.4 [x] Running daemons left ALIVE (user supervises; never kill from agent work).
    Live LLM vision test passed against the running crow-mcp daemon.
4.5 [x] Root AGENTS.md (~/src/crow-team): new architecture facts.
    Commit per phase with Session-Id trailer.
