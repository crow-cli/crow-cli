# TODO — toad absorption polish: sweep + YAML agent config + sqlite consolidation

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Goal: finish absorbing the toad TUI. (1) one more attribution/telemetry sweep
so nothing toad-flavored leaks into UX or env; (2) a crow-cli-way YAML config
system for ACP agent servers (replace toad's bundled-TOML agent store);
(3) consolidate the TUI's private sqlite (tui/db.py sessions table) into
crow-memory's db — one store for the package's state.

Prior sprint (PostgreSQL memory backend) is COMPLETE — see git history.
This file replaces it.

## Items (unordered)

- [x] Sweep: rename env vars TOAD→CROW, TOAD_LOG→CROW_LOG, TOAD_CWD→CROW_CWD,
      TOAD_ACP_INITIALIZE→CROW_ACP_INITIALIZE (command_pane.py, shell.py,
      acp/agent.py, constants.py). No in-repo consumers beyond setters — verified.
- [x] Sweep: conversation.py — "run `toad` again" → crow; /toad:* slash command
      IDs → /crow:* (defs + dispatch, only file referencing them); SVG export
      filename "Toad" → "Crow".
- [x] Sweep: cosmetics — store.py `toad_version` var, mcp.py "toad never
      connects" comment, jsonrpc.py debug-sample greet("Will").
- [ ] Audited, KEEP: NOTICE + pyproject comment + README:182 + tui_cmd.py
      docstring (license-required attribution); app.py "Danger, Will Robinson!"
      (SF-movie quote list — pop culture, not attribution); sandbox/ + docs/
      ancestors (history); crow-native "telemetry" naming = the MCP query
      facade (list-sessions/query-memory/query-session), NOT toad telemetry.
      toad telemetry itself is gone: zero posthog/toad.run/batrachian.ai in src.
- [x] ACP agent server config (TOML kept, per user pivot — separate from
      config.yaml is fine): user-editable TOMLs in ~/.agents/crow/agents/,
      seeded once from bundled data/agents (user dir then authority);
      ${VAR} expansion via shared resolve_env_vars; app.settings_path now
      uses get_default_config_dir() (was hardcoded dup); dead config_path
      removed. Verified 2026-08-29: 5 new unit tests, full gate 492 green.
- [x] v5→v6 migration script (scripts/migrate_v6.py): fresh dst = v5 copy +
      FTS rebuild + session_tabs (copied from src if present + imported from
      legacy tui.db, deduped on agent_session_id, timestamps converted to
      iso-UTC). Non-destructive; cutover = db_uri dry runs, then user backup
      + rename. Verified 2026-08-29: 3 tests; live run produced
      ~/.agents/crow/crow-v6.db (71558 msgs +FTS, 34 tabs).
- [x] Sqlite consolidation: new `session_tabs` table in crow_cli.memory
      (named for what it is — the agents table already owns "sessions"
      server-side); tui/db.py rewritten as async facade over it, db_uri from
      Config.load() (common authority with agent + MCP surfaces); dead
      app.db_path removed. Old ~/.local/state/crow/tui.db orphaned (resume
      list starts fresh; titles were session ids anyway). Verified
      2026-08-29: 3 new tests, gate 495 green, live crow.db has the table,
      list-sessions unaffected.
