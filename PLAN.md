# PLAN — open files in helix inside a terminal tab

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

### The unlock (user, 30Aug2026)
Clicking a file in the TUI's project explorer must open **helix editing that
file inside a new session tab**, where the tab body is a **real terminal
emulator running the `hx` process**. NOT a fullscreen takeover of the TUI,
NOT an external editor — a terminal-shaped emulator *inside* the tab, as
pass-through as possible ("open the space for helix to fill like a good TUI
app"). `:wq!` (helix quitting) closes the tab. The tab model becomes generic:
`SessionTab: AcpClientChat | Terminal | Editor` (decoupled from session-id).
The `!command` fire-and-get-text-back shell stays as-is for now — do NOT
revolutionize the chat interface this sprint.

### Reuse, don't hand-roll
- `widgets/terminal_tool.py::TerminalTool(Terminal)` already does the full PTY
  dance (openpty, subprocess, read loop, `write_stdin`, `resize_pty`,
  `wait_for_exit`, `kill`). EditorTerminal subclasses it.
- Tabs are Textual **modes**: `CrowApp.new_session_screen(get_screen, title)`
  registers a mode + screen and tracks it in `SessionTracker`; the
  `SessionsTabs` widget renders tabs from `session_tracker` (it reads
  `app.session_tracker` + `app.current_mode`, so it works on ANY screen).
- `SessionClose` message + `MainScreen.on_session_close` already implement
  "switch to neighbour, close tracker entry, remove mode".

### Build/test gate
`uv --project . run pytest tests/unit -q` after each step (there is no TUI
test dir yet — create `tests/unit/tui/`). Live smoke in tmux session
`crowtui-test` (NEVER touch other sessions / the user's live rio windows;
this agent is itself a crow-cli instance — do not kill crow processes).
Commit when green, `Session-Id: terrific-heron-of-splendid-greatness` trailer.

## Steps

> STATUS (30Aug2026): steps 1–7 DONE. Steps 1–6 committed (a52e3d41,
> 296a568c, 3d8597e5); step 7 (slice 2) committed this segment. Live smoke
> green end-to-end: file click → helix renders inside the tab in the chat's
> column with the sidebar visible, keys pass through, `:wq!` writes & closes
> the tab; the tab `✕` affordance closes an editor tab gracefully (sends
> `:wq!\r`, helix exits, no orphan process) and a chat tab directly. Full
> gate green: 518 passed (unit + integration + e2e + memory).
>
> Root-cause fix landed in 3d8597e5: the child PTY was never made the
> controlling terminal, so helix read /dev/tty size from the OUTER terminal
> (187 cols) and never got SIGWINCH — that, not the ANSI state, caused the
> blank/garbled editor. Fixed via preexec setsid()+TIOCSCTTY + pre-spawn
> PTY sizing.
>
> Slice-2 notes: programmatic keys to helix must end in `\r` (TERMINAL_KEY_MAP
> maps `enter`→`\r`, and helix ignores `\n`). `kill()` now kills the whole
> process group (os.killpg) and `EditorTerminal.on_unmount` calls it, so a
> closed tab never leaks `sh`/`hx`.

1. ✅ **`tui/widgets/editor_terminal.py::EditorTerminal(TerminalTool)`**
   - Pure pass-through `on_key`: forward EVERY key incl. `escape` immediately
     (no double-tap-to-blur — helix needs ESC). `event.prevent_default();
     event.stop()` then `state.key_event_to_stdin` → `write_process_stdin`.
   - Override `update_size` to also `resize_pty(self._shell_fd, w, h)` so
     helix redraws on tab/window resize (TerminalTool only sizes once).
   - Post `Exited(return_code)` Message when the process exits.
   - CSS: fill the tab (`width:100%; height:1fr;`), no border/`-success` noise.
   - Verify: headless run_test with a trivial program (`cat`/`printf`) →
     output lands in the buffer; ESC/key bytes reach stdin; Exited fires.

2. ✅ **`tui/screens/editor.py::EditorScreen(Screen)` + `editor.tcss`**
   - compose: `SessionsTabs()`, `EditorTerminal`, `Footer()`.
   - on_mount: `terminal.start(w,h)` with the `hx <path>` command, focus it.
   - Handle `EditorTerminal.Exited` → post `SessionClose(self.id)` (tab closes
     when helix quits). Reuse the close semantics of MainScreen.on_session_close.
   - Session-nav bindings (`ctrl+[` / `ctrl+]`) so you can leave the tab;
     a `ctrl+q` binding → `quit_editor()` sends `:wq!\r` to stdin.
   - Verify: headless test opens EditorScreen with a quick-exit command →
     mounts, focuses terminal, closes on exit.

3. ✅ **Generic tab model** — `session_tracker.SessionDetails` gains
   `kind: Literal["chat","editor"]="chat"`; thread through
   `SessionTracker.new_session(title, kind)` and
   `CrowApp.new_session_screen(get_screen, title, kind)`. SessionsTabs may
   render an editor glyph by kind (keep minimal).
   - Verify: existing unit tests green; kind defaults to chat.

4. ✅ **`CrowApp.open_file_in_editor(path)`** — build `Command(editor.command,
   [str(path)], env, cwd=project)` and `new_session_screen(get_screen,
   title=f"hx {path.name}", kind="editor")`. Editor command from settings key
   `editor.command` (default `hx`) — add to `settings_schema.py` SCHEMA.
   - Verify: headless — call it, assert a new editor mode/screen exists.

5. ✅ **Rewire the explorer click** — `MainScreen.on_project_directory_tree_selected`
   → `self.app.open_file_in_editor(data.path)` (instead of
   `insert_path_into_prompt`). `@file` path-insert via path_search is unchanged.
   - Verify: simulate `DirectoryTree.FileSelected` → open_file_in_editor called.

6. ✅ **Live smoke (tmux `crowtui-test`)** — launch TUI, open a file from the
   explorer, confirm helix renders inside the tab, keys pass through, `:wq!`
   closes the tab and returns to chat. Capture frames to verify rendering.

7. ✅ **(slice 2) tab `x` close affordance** — every tab label renders a
   trailing `✕` (`session_tabs.CLOSE_GLYPH`); `SessionLabel.on_click`
   hit-tests `offset.x >= content_region.width` and posts
   `messages.SessionRequestClose(mode)`. `CrowApp.on_session_request_close`
   is graceful for editor tabs (sends `:wq!\r` — `\r`, not `\n` — and lets
   the resulting Exited→SessionClose cascade remove the tab) and direct for
   chat tabs. `terminal_tool.kill()` kills the process group and
   `EditorTerminal.on_unmount` calls it, so closing never orphans `sh`/`hx`.
   - Verify: unit `test_x_affordance_gracefully_closes_editor_tab` (asserts
     the editor received `:wq!` and the tab closes on exit) + live tmux
     smoke (click `✕` → helix exits, no orphan). Both green.

---

# PLAN — mature the ANSI emulator + editor tab = chat page

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

### The unlock (user, this segment)
Two user reports with screenshots:
1. **Editor tab must be the SAME page as the chat page** — "they're really
   the same page… align completely". Chat: tab bar INSIDE the right column
   (right of sidebar, top of the Conversation widget). Editor: tab bar
   full-width ABOVE the sidebar. Fix = move `SessionsTabs()` inside
   `#editor-body` and mirror Conversation's column CSS exactly.
2. **Holding `down` in helix garbles the display** — jumbled line numbers,
   statusline fragments scattered at the right edge, scroll dead.

### Research done (verified, don't redo)
- **pyte oracle**: our `TerminalState` matches pyte with 0 mismatches at
  fixed size (120×40, 100 downs) AND under the app's real resize sequence
  (headless 150×50 and user's 187×50). Core emulation is CORRECT.
- **The divergence is resize semantics**: our `TerminalState.update_size` →
  `_reflow()` FOLDS stale wide lines on width shrink; pyte `Screen.resize`
  TRUNCATES columns at the right and deletes rows from the TOP on height
  shrink. Folded stale alt-screen lines break CUP row addressing
  (fold-index ≠ row-index) → exactly the garble the user saw.
- **Copied notes from mitosch/textual-terminal** (the project doing exactly
  this — pyte inside a Textual widget): `on_resize` sets ncol/nrow from the
  widget size, tells the PTY via set_size, and calls `screen.resize(nrow,
  ncol)` — real-terminal semantics, NO folding, NO buffer wipes. Renders by
  iterating `screen.buffer[y][x]` Char cells; mouse toggled by sniffing
  DECSET 1000h/l (we already do the equivalent). Also noted:
  par-term-emu-tui-rust (Textual widget over Rust core) as the mature/perf
  option; neovim :terminal uses libvterm and still has resize-drift bugs.
- Widget mitigation (`update_size` wipes alt buffer on alt+size change)
  exists but is a lossy band-aid; the state itself must be grid-faithful.

## Steps

1. ✅ **pyte-semantics resize in `tui/ansi/_ansi.py::TerminalState.update_size`**
   - Alternate screen: width shrink → TRUNCATE every line at the new width
     (never fold — grid rows must stay 1:1 with buffer lines); height
     shrink → delete rows from the TOP; height grow → pad blank rows at the
     bottom; clamp the cursor; rebuild fold index; mark all lines updated.
   - Scrollback (normal) screen: keep the existing fold/reflow behavior
     (presentation wrapping is a chat feature).
   - Fix the `width is None` bug (compared `previous_width != width` with
     `width=None` → spurious reflow).
   - `widgets/terminal.py::update_size`: pass `self._height` (not the raw
     arg) to `state.update_size`; drop the lossy alt-buffer wipe — with
     grid-faithful resize the truncated content is exactly what a real
     terminal shows until the program's SIGWINCH repaint lands.
   - Verify: `tests/unit/tui/test_ansi_resize.py` — pyte-oracle regression
     (helix-shaped paint → shrink → repaint, 0 mismatches), CUP addressing
     after shrink lands on the right row, scrollback still folds.

2. ✅ **Editor tab = chat page** — `screens/editor.py` compose: move
   `SessionsTabs()` inside `#editor-body` (above EditorTerminal);
   `editor.tcss`: `#editor-body` gets Conversation's chrome (`padding-left:
   1`, `&.-column { max-width: 100; background: black 7%; }`) and
   `_apply_column_width` toggles `-column` exactly like MainScreen's
   `watch_column`. Verify: unit test asserts SessionsTabs is a descendant of
   #editor-body; live smoke compares both tabs' tab bars.

3. ✅ **Gate + live smoke** — `pytest tests/unit -q`, full gate, tmux
   `crowtui-test`: open file in helix, hold down (100 downs via SGR keys or
   repeated sends), resize the window, verify no garble; compare chat vs
   editor tab bar placement via capture-pane.

4. ✅ **Commit** (Session-Id trailer) + PLAN/TODO status updates.

## Deferred (still open, not this sprint)
- TUI image attachments as ACP image content (previous PLAN, steps preserved
  in TODO.md item).
- TUI ACP-client migration onto the official `acp` SDK (TODO.md item).
- `!command` shell UX improvements (reveal/scroll lag) — fire-and-forget is
  acceptable for now per user.
