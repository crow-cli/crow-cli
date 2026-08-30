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

> STATUS (30Aug2026): steps 1–6 DONE & committed (a52e3d41, 296a568c,
> 3d8597e5). Live smoke green: file click → helix renders inside the tab in
> the chat's column with the sidebar visible, keys pass through, `:wq!`
> writes & closes the tab. 274 unit tests pass. Next: step 7 (slice 2).
>
> Root-cause fix landed in 3d8597e5: the child PTY was never made the
> controlling terminal, so helix read /dev/tty size from the OUTER terminal
> (187 cols) and never got SIGWINCH — that, not the ANSI state, caused the
> blank/garbled editor. Fixed via preexec setsid()+TIOCSCTTY + pre-spawn
> PTY sizing.

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
     a `ctrl+q` binding → `quit_editor()` sends `:wq!\n` to stdin.
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

7. **(slice 2, after 1–6 green) tab `x` close affordance** — clicking `x` on
   an editor tab sends `:wq!` to helix (graceful), on a chat tab closes it.

## Deferred (still open, not this sprint)
- TUI image attachments as ACP image content (previous PLAN, steps preserved
  in TODO.md item).
- TUI ACP-client migration onto the official `acp` SDK (TODO.md item).
- `!command` shell UX improvements (reveal/scroll lag) — fire-and-forget is
  acceptable for now per user.
