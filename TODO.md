# TODO

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Prior sprint (toad absorption polish: attribution sweep, TOML agent store,
sqlite consolidation, v5→v6 migration) is COMPLETE — see git history
(phases landed 2026-08-29, gate 498 green).

## Items (unordered)

- [x] DONE — open files in helix inside a terminal tab (see PLAN.md, steps
      1–7 all complete). Click file in explorer → new session tab whose body
      is a pass-through terminal emulator running `hx <path>`; `:wq!` closes
      the tab; generic tab model `AcpClientChat | Terminal | Editor`.
      SLICE 1 (a52e3d41, 296a568c, 3d8597e5): EditorTerminal widget,
      EditorScreen + sidebar/column chrome, generic tab kind, file-click
      rewire, and the root-cause PTY fix (child now owns the PTY as its
      controlling terminal via setsid+TIOCSCTTY — without it helix read the
      OUTER terminal's size off /dev/tty and never got SIGWINCH, which was
      the blank/garbled editor, not the ANSI state).
      SLICE 2 (this segment): tab `✕` close affordance — editor tab closes
      gracefully (sends `:wq!\r`, NOT `\n`; helix needs `\r`), chat tab
      closes directly; `kill()` now process-group-kills (os.killpg) and
      `EditorTerminal.on_unmount` calls it so no `sh`/`hx` orphan survives a
      closed tab. Live tmux smoke green (✕ renders, graceful close, no
      orphan); unit `test_x_affordance_gracefully_closes_editor_tab` green;
      full gate 518 passed.
- [x] DONE — mature the ANSI emulator + split the agent terminal (see
      PLAN.md "mature the ANSI emulator + editor tab = chat page").
      (1) Helix garble root-caused via a pyte oracle: our resize FOLDED
      stale wide lines (fold-index ≠ row-index breaks CUP addressing);
      `TerminalState.update_size` now has pyte semantics for the alternate
      screen (truncate columns on width shrink, top-trim/pad on height
      change, clamp cursor, 1:1 fold index) while scrollback keeps folding;
      lossy alt-buffer wipe removed. Live tmux: 100 downs + shrink-resize
      repaint immaculate.
      (2) The agent's `terminal` tool no longer rides the human-facing
      emulator: new headless `tui/agent_terminal.py::AgentTerminal`
      (PTY + raw byte capture, no Textual, no ANSI state) backs the ACP
      terminal handlers; Conversation gets a best-effort display-only
      TerminalTool mirror. Regression pinned: terminal/create with a
      suspended 0-size conversation window captures output (old path sized
      the PTY from the 0 window → negative width → struct.pack raised →
      silent empty output).
      (3) Editor tab = chat page: SessionsTabs inside `#editor-body`,
      column chrome mirrors Conversation (`-column` class + max-width);
      the earlier "column toggle never lands" mystery was a test artifact
      (`cat` exits → Exited → SessionClose pops the screen mid-pause), not
      a watcher bug. Gate 519 green (290 unit).
- [ ] Migrate the TUI's ACP client off the hand-rolled stack. `tui/jsonrpc.py`
      + `tui/acp/` are toad legacy: own Request/MethodCall futures, own
      dispatch loop, own subprocess plumbing — while `client/` (main.py,
      subagent.py) already speaks ACP through the official `acp` SDK
      (ClientSideConnection, concurrent dispatch, protocol-correct
      notification semantics). Rolled-own is where bugs like the 2026-08-29
      cancel-lag fester. NOTE: the tactical fix c739dec6 did NOT resolve the
      felt lag — user confirmed live 2026-08-29 ("that turn cancellation did
      NOT work"); user's call: fix it in the full python-sdk ACP-ification,
      i.e. this item. Scope: replace tui/acp/agent.py's transport layer with
      acp.spawn_agent_process/ClientSideConnection, keep the Textual widget
      + message surface. Cancel must preempt everything (see PLAN.md).
- [ ] TUI prompt attachments: image files must upload as ACP image content,
      not text. Bug (seen live 2026-08-29, session
      mindful-beneficial-groundhog-of-blizzard): `@photo.png` in a prompt
      went over session/prompt as text. Root cause:
      `tui/prompt/resource.py::load_resource` — `mimetypes.guess_file_type`
      gives png/jpeg/webp `encoding=None`, so they hit the
      `read_text(errors="replace")` branch and become mojibake text blocks.
      Fix: mime startswith `image/` → read bytes, and `tui/acp/prompt.py::build`
      emits `{"type": "image", "data": <b64>, "mimeType": ...}` (ACP
      ImageContentBlock — agent side already consumes these, see
      agent/prompt.py). Extensions to cover at least: png jpeg jpg webp gif
      bmp ico avif. Test: unit test on build() with a tiny real png fixture.
