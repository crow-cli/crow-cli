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

## Phase 3 — sqlite consolidation — DONE 2026-08-29 (495 green)

User steer: the agents table IS the session table server-side, so the new
table is named for the client concept: `session_tabs` (ORM `SessionTab`).
Common authority = crow_cli.config: base dir (phase 2) + Config.db_uri
(phase 3); memory stays a parameterized store layer; tui is a pure consumer.

1. models.py: `SessionTab` / `session_tabs` (id, agent, agent_identity,
   agent_session_id, title, protocol, prompt_count, created_at, last_used,
   meta_json). create_all is additive — existing dbs gain the table on next
   create_database(), no schema bump.
2. memory/session_tabs.py: sync CRUD (tab_new/get/recent/touch/rename).
3. tui/db.py: async facade (same method names/signatures — zero caller
   changes in acp/agent.py, app.py, session_resume_modal.py); db_uri
   defaults to Config.load().db_uri. Dead app.db_path removed.
4. Old ~/.local/state/crow/tui.db orphaned, no migration (titles were
   session ids; resume list starts fresh).
- Verified: 3 new tests (tests/memory/test_session_tabs.py incl. facade);
  gate 495; live crow.db inspected (session_tabs present); list-sessions
  unaffected.
- Follow-up (not blocking): telemetry list_sessions could LEFT JOIN
  session_tabs to show TUI titles.

Sprint complete: phases 1-3 all done.
