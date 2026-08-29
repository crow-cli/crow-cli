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
- [ ] YAML ACP agent server config: user-editable YAML (crow-cli way, lives
      with config.yaml in ~/.agents/crow/) describing ACP agent servers
      (identity/name/command/args/env/protocol), merged over bundled defaults;
      TUI store lists them; spawn path unchanged.
- [ ] Sqlite consolidation: TUI sessions (title/last_used) move into
      crow-memory's sessions table; tui/db.py deleted; TUI session list/new/
      load driven by memory db (same store the telemetry surfaces already read).
