# PLAN — chat → extension-only, delete the orphaned front ends

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Scope capture: `TODO.md`. Worktree `~/.agents/crow/src/worktrees/crow-cli-cleanup`
(branch `crow-cli-cleanup`). Every command below runs with `cwd` = the worktree
(`W`), never `main`.

Trajectory is numeric: 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7. Commit at each phase
boundary with the `Session-Id: jovial-ruby-bullfinch-of-brotherhood` trailer.
Never push.

**Gates (floor for every phase):**
- `bun install` (worktree root) — exit 0
- `bun run --cwd packages/chat typecheck` — exit 0
- `bun run --cwd packages/chat test` — 3 files, all pass
- `bun run --cwd packages/vscode-acp build` — exit 0, writes `dist/extension.cjs`
  + `dist/webview/chat.js` + `dist/webview/chat.css`
- `cargo build --release --bin crow-agent` — exit 0
- `uv --project . run pytest tests/unit -q` — no new failures vs the Phase 0 baseline

---

## Phase 0 — worktree environment + baseline (no repo change)

1. Share main's cargo target so the worktree does not rebuild 20G of deps:
   `ln -s ~/.agents/crow/src/crow-cli/target <W>/target` (`target/` is gitignored,
   so this is environment, not a change). `install_crow.py` reads
   `<repo>/target/release/crow-agent`, which resolves through the symlink.
2. `bun install` at `<W>`; `bun install` at `<W>/packages/vscode-acp`.
3. Record the baseline: run every floor gate once, plus
   `uv --project . run pytest tests/unit tests/integration -q`. Write the pass/fail
   counts into `TODO.md`'s "Floor gates" so later phases compare against a
   number, not a memory. **Measured:** chat typecheck 0; chat test 35/0;
   vscode-acp build 0 (+`dist/webview/{chat.js,chat.css,assets}`) and typecheck 0;
   `cargo build --release --bin crow-agent` 0 in 90s; `cargo test -p crow-client`
   982/0 **after step 3b**; pytest 1089 passed / 6 failed (the known
   environmental set — browser + child-agent spawns).
3b. **Item I — un-orphan the Rust integration tests.** `cargo test -p
   crow-client` is red on `main` (rc 101, 5 compile errors): `cli_help.rs` (3
   sites), `tcp_attach.rs`, `sigterm_cleanup.rs`, `startup_session_e2e.rs` all
   `env!("CARGO_BIN_EXE_crow")`, but `bc03c5c7` renamed the bin to `crow-agent`.
   Rename all six to `CARGO_BIN_EXE_crow-agent`.
   **Verify:** `cargo test -p crow-client --no-run` rc 0, then the full run is
   982 passed / 0 failed. Commit this on its own — it is a fix, not a deletion.
4. Confirm the extension build's coupling before touching anything:
   `packages/vscode-acp/vite.config.ts` has `root: ../chat` and
   `input: chat/src/vscode.tsx`; its `build` script invokes
   `bun ../chat/node_modules/vite/bin/vite.js`. **So chat's `vite` devDep and its
   `node_modules` are load-bearing for the extension** — prune runtime
   `dependencies` only, never `devDependencies`.
5. No commit.

## Phase 1 — `packages/chat` becomes the extension's webview source (TODO B)

Subtraction only. Every file the extension reaches stays **byte-identical**.

1. Delete these 35 files (the set unreachable from `src/vscode.tsx`, computed by
   walking `import … from` **and** bare `import "…"` **and** CSS `@import`/`url()`):
   ```
   src/App.tsx                                   src/main.tsx
   src/assets/svar-icons/wx-icons.css            src/lib/fs-client.ts
   src/assets/svar-icons/wx-icons.woff           src/lib/settings.ts
   src/assets/svar-icons/wx-icons.woff2          src/lib/term-store.ts
   src/components/app-header.tsx                 src/lib/time.ts
   src/components/app-sidebar.tsx                src/lib/work-store.ts
   src/components/directory-picker.tsx           src/components/explorer/explorer.css
   src/components/mcp-settings-dialog.tsx        src/components/explorer/explorer.tsx
   src/components/session-badge.tsx              src/components/terminal/terminal-pane.tsx
   src/components/ui/alert-dialog.tsx            src/components/terminal/terminal-view.tsx
   src/components/ui/badge.tsx                   src/components/work/editor-tabs.tsx
   src/components/ui/input.tsx                   src/components/work/work-pane.tsx
   src/components/ui/label.tsx                   src/components/work/work-split.tsx
   src/components/ui/popover.tsx                 src/hooks/use-mobile.ts
   src/components/ui/resizable.tsx
   src/components/ui/scroll-area.tsx
   src/components/ui/separator.tsx
   src/components/ui/sheet.tsx
   src/components/ui/sidebar.tsx
   src/components/ui/switch.tsx
   src/components/ui/tabs.tsx
   ```
2. **Keep** — unreachable by import but not dead: `src/lib/acp-tool.test.ts`,
   `src/lib/chat-attachments.test.ts`, `src/lib/markdown-math.test.ts` (bun test
   targets for reachable libs), `src/vite-env.d.ts` (`vite/client` types, needed
   by `tsc` for the `*.css` imports), `src/index.css`, `src/vscode.css`,
   `src/themes/{light,dark,macchiato}.css`.
3. `packages/chat/package.json`: drop the 7 runtime dependencies nothing left
   imports — `@crow/editor`, `@svar-ui/react-filemanager`, `@xterm/xterm`,
   `@xterm/addon-fit`, `react-resizable-panels`, `assistant-stream`,
   `@assistant-ui/store`. (The last two stay installed transitively: they are
   workspace deps of `@assistant-ui/{core,react,acp}`.) Drop the SPA scripts
   `dev`, `build`, `preview`, `build:watch`; keep `typecheck` and `test`.
   **Leave `devDependencies` exactly as they are.**
4. Delete the SPA scaffolding: `packages/chat/index.html`,
   `packages/chat/vite.config.ts` (its only jobs were the dev server's
   `/fs`,`/pty`,`/acp` proxies to crow-web and the SPA build),
   `packages/chat/tsconfig.node.json` (it includes only `vite.config.ts`) and its
   `{ "path": "./tsconfig.node.json" }` reference in `packages/chat/tsconfig.json`.
5. Root `package.json`: the `web:*` scripts all `--filter @crow/chat` into
   scripts that no longer exist. Replace them with extension-facing ones that run
   in `packages/vscode-acp` (`ext:build`, `ext:typecheck`, `ext:package`) and a
   `web:test` → chat's `bun test`. Keep the workspace list untouched here
   (Phase 2 owns `packages/editor`).
6. `bun install` to refresh `bun.lock`.
7. **Verify:** all floor gates. Additionally re-run the reachability walk and
   assert the dead set is now exactly the 4 kept-but-unreachable files
   (3 tests + `vite-env.d.ts`) — i.e. nothing orphaned survived and nothing
   reachable was deleted. `git status` shows only deletions + the 3 manifests.
8. Commit: `refactor(chat): chat is the extension's webview — drop the SPA, the work pane and the terminal`.

## Phase 2 — delete `packages/editor` (TODO C)

1. `git rm -r packages/editor`; remove `"packages/editor"` from the root
   `package.json` workspaces list; `bun install`.
2. **Verify:** floor gates (the extension build is the real check — it must not
   resolve `@crow/editor` anywhere). `git grep -n "@crow/editor\|packages/editor"`
   returns only `PLAN.md`/`TODO.md`/journal prose.
3. Commit: `chore: delete @crow/editor, orphaned by the chat subtraction`.

## Phase 3 — delete `crates/crow-web` and `packages/electron` (TODO D, E)

1. `git rm -r crates/crow-web packages/electron`.
2. Root `Cargo.toml`: members → `["crates/crow-client", "crates/crow-gui"]`
   (Phase 4 takes crow-gui). `default-members` is already `crates/crow-client`.
3. `cargo build` to refresh `Cargo.lock`; commit the lockfile with the deletion.
4. **Verify:** `cargo build --release --bin crow-agent` exit 0;
   `cargo test -p crow-client` unchanged vs baseline;
   `git grep -n "crow-web"` returns only (a) the `/usr/bin/crow-web` **IDE reh-web
   server** references in `install_crow.py` / `test_install_crow.py` / README,
   (b) the MCP slice label in `tests/e2e/test_mcp_multi_server.py:94`,
   (c) the docstring example in `src/crow_cli/mcp/server/main.py:14`,
   (d) `install.py`'s historical sentence, (e) plan/journal prose.
   Check each hit before accepting it.
5. Commit: `chore: delete crates/crow-web and its Electron shell`.

## Phase 4 — delete `crates/crow-gui` and the `--gui` runtime (TODO F)

Forced consequence, stated plainly: without `crates/crow-gui` there is no
ratatui-over-wgpu window, so `crow --gui` goes away and the deb's launcher entry
becomes the `Terminal=true` one.

1. `git rm -r crates/crow-gui`.
2. `crates/crow-client/Cargo.toml`: drop the optional `crow-gui` dep, the `gui`
   feature (leaving `default = []`), and the comment block that explains them;
   switch the deb asset `packaging/crow-gui.desktop` → `packaging/crow.desktop`
   and fix the comment above it.
3. `git rm -r crates/crow-client/src/gui`; in `src/main.rs` drop `#[cfg(feature =
   "gui")] mod gui;`, the `--gui` help line, the `gui` field + its `"--gui" =>`
   parse arm + initialiser, the `#[cfg(not(feature = "gui"))]` bail and the
   `#[cfg(feature = "gui")]` run branch (and the `#[cfg(all(test, feature =
   "gui"))]` block at the foot).
4. `git rm crates/crow-client/tests/unit/gui__tests.rs` and its `mod` line;
   remove the four `--gui` assertions from `tests/unit/main__cli_args_tests.rs`
   (keep the neighbouring cases intact).
5. `git rm crates/crow-client/scripts/build-web.sh
   crates/crow-client/scripts/test-web.sh crates/crow-client/web/index.html
   crates/crow-client/packaging/crow-gui.desktop tests/e2e/test_web_paint_live.py`.
6. Root `Cargo.toml`: members → `["crates/crow-client"]`; refresh `Cargo.lock`.
7. **Verify:** `cargo build --release --bin crow-agent` exit 0;
   `cargo test -p crow-client` green with `gui__tests` gone and no `--gui` in
   `crow-agent --help`; `cargo build --release --features gui` must now FAIL with
   an unknown-feature error (proof the feature is really gone) — record the
   message, do not "fix" it; `uv --project . run pytest tests/unit tests/e2e -q`
   shows `test_web_paint_live.py` gone and no new failures;
   `git grep -n "crow-gui\|crow_gui"` returns only `packages/crow-gui` (the IDE
   pipeline — a different thing) and prose.
8. Commit: `chore: delete crates/crow-gui and the --gui window runtime`.

## Phase 5 — docs and manifests (TODO G)

1. `README.md`: drop the `crow-web` row from the front-door table and the
   `### crow-web — the browser client` section; drop the `crates/crow-gui`
   sentence; fix the repo map (`crates/crow-gui/`, `crates/crow-web/`,
   `packages/editor/`, `packages/electron/` lines out); fix the cargo note that
   says `crow-web` and `crow-gui` want `-p <crate>`; drop `crow-web` from the
   prerequisites line.
2. `AGENTS.md`: the launch recipe loses the `cargo run -p crow-web …` block (the
   browser client is the IDE's `crow serve-web` now); the arg table loses the
   `--acp-url` / `--port,--root,--shell` `crow-web` rows and the `crow-web`
   mention under "Dials a running server"; `--agent/--agent-arg` (`crow-agent`)
   stays.
3. `crates/crow-client/README.md`: the `packaging/crow-gui.desktop` /
   `Exec=crow --gui` paragraph → the `Terminal=true` `packaging/crow.desktop`
   route the deb now ships.
4. Root `package.json` `description` no longer says "embedded in the crow-web
   binary".
5. **Verify:** `git grep -ni "crow-web\|crow-gui\|crow_gui\|@crow/editor\|electron"`
   — every remaining hit is `packages/crow-gui` (the pipeline), the IDE's
   `/usr/bin/crow-web`, an MCP label, or deliberate history. Docs-only phase: no
   test gate beyond the floor gates still passing.
6. Commit: `docs: the front doors are the extension and crow serve-web`.

## Phase 6 — the empty-editor watermark (TODO A) — separate, self-contained

1. `packages/crow-gui/make_icons.py`: add `write_letterpress()` and call it from
   `main()`. It reads the single `<path … d="…">` out of `art/crow-logo.svg`
   (assert exactly one, assert the `d` is non-empty) and writes the four files
   under `vscodium/src/stable/src/vs/workbench/browser/parts/editor/media/`,
   each as `40x40`-style header + `viewBox="0 0 1024 1024"` +
   `<g id="codium_grey_<variant>_letterpress">` + one `<path d=… fill=COLOUR
   [fill-opacity=OP] id="path6008"/>`. Variant table:
   `dark → (#B2B2B2, 0.3)`, `light → (#B2B2B2, 0.1)`, `hcDark → (#3C3C3C, None)`,
   `hcLight → (#B2B2B2, None)`.
   **The `style="fill:#ffffff;fill-opacity:1"` attribute must NOT be carried
   over** — inline style beats presentation attributes and would paint the
   watermark solid white. Comment that in the code, because it is the trap.
2. Run it: `uv --project ~/.agents/skills/use-uv run python
   packages/crow-gui/make_icons.py` (needs PIL). It regenerates the icons too —
   those must come out byte-identical (`git status` shows only the 4 letterpress
   files). If any icon file changes, stop and diff it before committing.
3. **Verify:** for each of the 4, assert the `<g id>` is unchanged, the fill /
   fill-opacity matches the table, there is no `style=` attribute, and the file
   parses as XML. Then rasterise one with inkscape
   (`inkscape letterpress-dark.svg --export-type=png --export-filename=/tmp/lp.png
   --export-width=256`) and assert with PIL: alpha bbox ≈ `(41,38,214,213)`
   (the 1024-box bbox `(166,152,856,853)` scaled by ¼), and the non-transparent
   pixels are `#B2B2B2` — not white.
4. Commit: `feat(ide): crow's mark is the empty-editor watermark`.
5. The end-to-end proof is Phase 7's build: an empty editor group in the
   installed IDE shows the crow glyph.

## Phase 7 — reproduce `crow-cli install crow` from the worktree (TODO H)

The gate that matters. Long (~40 min the first time) and needs network for
`npm ci` and the Open VSX vsix fetches.

1. Preflight: `fnm` has `v24.18.0` (`.nvmrc` wants it; host node is v22) ✓;
   `~/src/crow-gui/vscode` has the pinned commit `08d4889f9ec4a1685d257b9b95de036c8e1ce1e5`
   (tag 1.135.0) ✓ so `build.sh` seeds from the local clone instead of fetching
   340MB; `dpkg-dev` + `fakeroot` present (`deb_preflight`); 758G free ✓.
2. Dry run first, and check it resolves the **worktree**, not main:
   `uv --project <W> run crow-cli install crow --dry-run`.
   `repo_root()` walks up from `crow_cli/cli/install_crow.py`'s `__file__`, so it
   must print `pipeline: ~/…/worktrees/crow-cli-cleanup/packages/crow-gui`.
   If it prints main, stop — the venv is wrong.
3. The real run: `uv --project <W> run crow-cli install crow`. Expect, in order:
   `./build.sh --arch x64 --deb` in `packages/crow-gui` (get_repo from the local
   clone → `cp -rp src/stable/* vscode/` → `gulp compile-web` → prepare →
   package → `bundle-exts.sh` → **`bun install` + `bun run build` in
   `packages/vscode-acp`** → deb), then `cargo build --release --bin crow-agent`,
   then `sudo dpkg -i vscodium/assets/crow_*.deb`.
   Run it with a generous timeout / in the background and poll; do not kill it.
4. **Verify:** the build prints `crow-gui: built-in extension crow-acp →
   vscodium/VSCode-linux-x64/resources/app/extensions/crow-acp` (and the reh-web
   twin); `dist/webview/chat.js` + `chat.css` exist inside it; the deb installs;
   `crow --version`, `crow agent --help` (no `--gui`), and `crow serve-web`
   starts and prints a tokenised URL. Screenshot an empty editor group and confirm
   the crow watermark (Phase 6).
5. If the extension build fails on a missing chat module, the reachability walk
   in Phase 1 was wrong — fix chat, do not re-add `packages/editor`.
6. Commit anything the build proved needed (nothing should be): the phase is a
   gate, not a change.

## Done when

`git log` shows one commit per phase 1-6 on `crow-cli-cleanup`, all floor gates
green, `crow-cli install crow` reproduced from the worktree, and the empty
editor group wears crow's mark. Branch stays local — no push.
