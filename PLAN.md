# PLAN — Web → GUI (install web walkthrough, editor themes, Electron shell)

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Scope capture: `TODO.md`. Repo root = MAIN (`~/.agents/crow/src/crow-cli`).

**Gates (floor for every item):**
- `bun run web:typecheck` — PASS
- `bun run web:build` — PASS
- `cargo test -p crow-web` — PASS (unchanged, unless crow-web touched)
- `uv run pytest tests/unit -q` — PASS (unchanged, unless install_web/install touched)

Trajectory is numeric: 1 → 2 → 3 → 4. Commit at each phase boundary with the
`Session-Id:` trailer.

---

## Phase 1 — confirm `install web` is wired — (no code change) ✅ done

1. Explain the build pipeline in the chat response:
   - `bun install` (workspace)
   - `bun run web:build` → `@crow/chat` `tsc -b && vite build` → `packages/chat/dist`
   - `cargo build --release -p crow-web` → embeds `packages/chat/dist` via
     `rust-embed` (or reads it from disk under the `dev-web` feature)
   - binary → `~/.local/bin/crow-web` + `systemd --user` unit
2. Verify: `uv run crow-cli install web --help` prints the command and options.
3. Mark TODO item done; no commit.

## Phase 2 — editor theming (latte/mocha/macchiato) ✅ done

1. Rewrite `packages/editor/src/theme.ts`:
   - Drop `oneDark` + `defaultHighlightStyle`; import `HighlightStyle`,
     `syntaxHighlighting` from `@codemirror/language` and `tags` from
     `@lezer/highlight`.
   - Build one `HighlightStyle` from `var(--code-*)` for every Lezer tag, so
     the editor inherits whatever palette `<html data-theme>` publishes — no
     per-theme code, and future themes come free.
   - Export a single `editorTheme` extension = `[baseTheme,
     syntaxHighlighting(highlightStyle, { fallback: true })]`.
2. `packages/editor/src/code-editor.tsx`: drop the `scheme` prop and the
   `themeSlot` compartment; use `editorTheme` statically.
3. `packages/editor/src/index.ts`: export `editorTheme` (+ keep `baseTheme`),
   remove `getThemeExtensions`/`ColorScheme`.
4. `packages/chat/src/components/work/work-pane.tsx`: stop passing `scheme`;
   drop the now-unused `useColorScheme` import.
5. Add `@lezer/highlight` to `packages/editor/package.json` dependencies.
6. Verify: `bun run web:typecheck` + `bun run web:build` exit 0; live browser
   switches editor token colours with the theme dropdown.
7. Commit.

## Phase 3 — Electron shell ✅ done

1. `packages/electron/launcher.cjs`: pure `buildArgs` + `parsePort` (no electron
   import) so it is bun-testable.
2. `packages/editor/…` (no): `packages/electron/main.cjs`: `require("electron")`,
   spawn `crow-web --port 0`, parse the bound-port line, open a BrowserWindow.
3. `packages/electron/launcher.test.cjs`: `bun test` for the two pure helpers.
4. `packages/electron/package.json`: `main: main.cjs`, devDep `electron`,
   `scripts.test: bun test`. NOT added to the root workspace glob.
5. Verify: `bun test` green; `node --check main.cjs` clean.
6. Commit.

## Phase 4 — `crow-cli install gui` ✅ done

1. New `gui` command in `src/crow_cli/cli/install.py`, reusing
   `install_web.build(repo)` for the SPA + binary.
2. Install layout: `~/.local/share/crow/gui/{crow-web, main.cjs, launcher.cjs,
   package.json}`, then `bun install` there to fetch electron.
3. `~/.local/bin/crow-gui` launcher (env-overridable `CROW_ROOT`, `CROW_ACP_URL`,
   `CROW_WEB_BIN`) + `~/.local/share/applications/crow.desktop`.
4. Remove the `desktop`/`check` cruft (`odellus/sidex`) from `install.py`.
5. Verify: `crow-cli install gui --help`; `--dry-run` reaches the copy/launcher
   steps; `crow-cli install web --help` still intact.
6. Commit.
