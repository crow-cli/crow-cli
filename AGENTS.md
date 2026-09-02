# RULES

- Never mention the user's emotional state. I'm here to work, NOT be psychoanalyzed by a machine.

# TUI TERMINAL KNOWLEDGE (verified, don't re-derive)

- ANSI emulator resize semantics ARE the product: alternate-screen buffers
  must resize like pyte/real terminals (truncate columns on width shrink,
  top-trim/pad on height change, 1:1 grid rows <-> buffer lines, clamp
  cursor) — folding stale wide lines breaks CUP row addressing = garble.
  Scrollback (normal) screen keeps folding. Oracle test: pyte dev dep.
- Two terminal pathways by mandate: `tui/agent_terminal.py::AgentTerminal`
  (headless PTY + raw byte capture) backs the ACP terminal tool; the
  human-facing emulator (TerminalTool/EditorTerminal) is separate. A
  suspended conversation has window size 0 — never size a PTY from it.
- Textual gotchas: `Widget.screen` is a Textual property (name pyte
  screens `pyte_screen`); `Strip` API is cell-based in Textual 8
  (`crop_extend(0, w, None)`, `adjust_cell_length`); Textual 8.2.x breaks
  on rich>=15 (uses Style internals rich dropped) — pin rich<15.
- pyte color values are "default", ANSI names, or 6-char hex strings for
  BOTH 256-color and truecolor — never numeric palette indices (an
  all-digit hex like "281733" is truecolor).
- A TUI only sends DIFFS: any fresh out-of-process terminal client
  (riotermjs, reconnect) sees a blank/stale screen unless the child is
  forced to full-repaint (winsize nudge: set cols-1 then cols).
- sandbox/textual-term-toy: the terminal-in-a-column experiment + the
  riotermjs browser harness (bridge.py = PTY<->websocket; harness/ = page
  with importmap to ~/src/riotermjs dist). How to view the TUI in a
  browser: run bridge.py + `python -m http.server --directory harness`,
  open the page, screenshot via playwright-cli.

# TUI STREAMING & CANCELLATION (verified, don't re-derive)

- Textual has ONE message pump per app. A torrent of `session/update`
  starves key handling completely (measured: 0 Escape handlers ran while a
  mock agent blasted the pipe — starvation, not stolen bindings). Fix is to
  never render more than you can afford: `tui/acp/agent.py` coalesces chunks
  on `loop.call_later` (`STREAM_FLUSH_INTERVAL` = 30ms, early flush at 16 KB)
  and buffers wire logging O(1) instead of a task per line.
- `session/cancel` is a notification: `jsonrpc.MethodCall.wait()` returns
  immediately when `id is None`, so awaiting it proves nothing (the old code
  always reported success). `Agent.begin_cancel()` is synchronous by contract
  and writes to stdin before returning — nothing may be awaited in front of it.
- Turn ownership lives in `Agent.send_prompt` (`_turn_seq` / `_turn_open`), not
  in `acp_session_prompt`: prompts overlap when the user cancels and immediately
  re-prompts, and only the current turn may close it. A stale `_cancelling=True`
  silently swallows the *next* turn's updates — which is why `begin_cancel()`
  returns False when nothing is in flight.
- `Conversation.action_cancel` claims the cancelled turn's widgets by reference
  before deferring their removal; reading `self._loading` from a deferred
  callback races the turn that replaced it and orphans its spinner.
- Escape is bound to `cancel` with `priority=True` (priority bindings run
  App-down, before the focused widget's `_on_key`) so it survives saturation —
  and deliberately yields to a focused Terminal in `check_action`, because
  tap-tap Escape is how you leave one. The Cancel button in the prompt row is
  the mouse path; visible only while `Prompt.-streaming`.
- TCSS: `display` accepts only `block`/`none` (no `inline`). A Button inside a
  1-line row needs `border: none; height: 1; min-width: 0` or it adds two rows.
- Load tests: `tests/integration/test_cancel_under_load.py` drives the real
  CrowApp against `tests/integration/mock_acp_agent.py` (env knobs
  `CROW_MOCK_TOKENS_PER_SEC` / `_CHUNKS` / `_CHUNK_CHARS` / `_IGNORE_CANCEL` /
  `_LOG`). Under load never `pilot.pause()` — it waits for a queue that never
  drains: poll on the event loop, post `events.Key` straight to the app, and use
  `Button.press()` (it refuses to post when hidden).
- KNOWN GAP (open): per-append cost of one long `AgentResponse` is still
  superlinear (~0.24ms -> ~2.8ms over one answer) and `check_prune()` is only
  reachable from `Conversation.post()`, so a single in-flight turn is unbounded;
  fix is to roll to a new `AgentResponse` past a line cap.
