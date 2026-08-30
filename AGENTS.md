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
