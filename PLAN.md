# PLAN — toad absorption polish (sweep → YAML agent config → sqlite consolidation)

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Build/test gate (every phase boundary):
`uv --project . run pytest tests/unit tests/mcp -q` then
`./run_tests.sh tests/unit tests/memory tests/mcp tests/integration -q`
Full gate at phase boundaries; unit+mcp after each item.

Trajectory: 1 → 2 → 3. Phases 2–3 are DESIGN-SCOPED (user asked to plan first);
implement after user review. Commit after each phase, Session-Id trailer.

## Phase 1 — attribution sweep — DONE 2026-08-29 (487 green, sweep rg-clean; commit same day)

1. Env renames: `env["TOAD"]`→`env["CROW"]` (widgets/command_pane.py:112,
   shell.py:202); `TOAD_LOG`→`CROW_LOG` (acp/agent.py:164);
   `TOAD_CWD`→`CROW_CWD` (acp/agent.py:556);
   `TOAD_ACP_INITIALIZE`→`CROW_ACP_INITIALIZE` (constants.py:54).
   - Verify: `rg -n "TOAD" src/` → zero hits; unit+mcp green.
2. conversation.py UX strings: "run `toad` again"→"run `crow` again" (line 98);
   slash IDs `/toad:clear|rename|session-close|session-new` → `/crow:*`
   (replace_all, defs + dispatch are the only references);
   `generate_datetime_filename("Toad", ...)` → `"Crow"` (line 1796).
   - Verify: `rg -n "toad:" src/` → zero; `rg -ni toad src/` only NOTICE-pointing
     comments; unit+mcp green; TUI imports + slash list builds.
3. Cosmetics: screens/store.py `toad_version`→`crow_version`; mcp.py comment
   "toad never connects"→"the TUI never connects"; jsonrpc.py debug sample
   `{"name": "Will"}`/`greet("Will")` → "Crow".
   - Verify: `rg -ni "will" src/` → only app.py SF-quote + LICENSE; green.
4. Full gate + commit. Keep-list (NOTICE, pyproject comment, README, tui_cmd
   docstring, app.py quote, sandbox/docs, crow-native telemetry naming) stays.

## Phase 2 — ACP agent server config — DONE 2026-08-29 (492 green)

User pivot: keep TOML, keep separate from config.yaml; common ground with
crow_cli.config = shared base dir + shared env expansion.

1. `agents.py`: store = `get_default_config_dir()/agents/*.toml`; seeded once
   from bundled `data/agents` (mkdir + copy iff dir absent; user dir then
   authority — no clobber). `resolve_env_vars` applied to parsed TOML
   (unset → "" + warning, parity with mcpServers). Bad TOML → AgentReadError.
2. `app.py`: `settings_path` = `get_default_config_dir()/tui.json` (was a
   hardcoded `~/.agents/crow` duplicating config's authority); dead
   `config_path` property (XDG, zero readers) removed.
3. Tests: `tests/unit/test_agent_store.py` — seed, no-clobber, add/hide,
   env expansion, fail-fast. 5 passed; full gate 492.
- Verified: pytest gate + `ls ~/.agents/crow/agents` after first TUI run
  shows seeded crowai.dev.toml (live check pending next TUI launch).

## Phase 3 — sqlite consolidation (design; implement post-review)

Current state: TWO stores. `tui/db.py` = private aiosqlite `sessions` table
(int id, title, last_used) for the TUI's session tabs; `memory/db.py` (v5) =
sessions/agents/messages + FTS in crow.db, already the source for telemetry
surfaces and `session/load`.

Design:
1. Add `title TEXT` + `last_used` (or reuse existing timestamp cols) to
   memory's sessions table (idempotent ALTER, no full migration — v5 stays v5).
2. Rewire TUI: session list/new/rename/touch → memory db API; TUI int-id
   indirection dies (session id string is the key; title pre-set to session
   id per existing behavior).
3. Delete `tui/db.py` + its db file path; one-time import of existing TUI
   titles NOT needed (titles are session ids today).
- Test criteria: unit tests for renamed session ops against memory db;
  full gate green; live: TUI shows sessions identical to
  `crow-cli list-sessions`, rename persists and is visible from CLI.
