# TODO — Web build, editor themes, and the Electron GUI

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Sprint: turn the embedded `crow-web` binary into a clean desktop GUI and give the
editor real themes (not just dark vs light). Repo root = MAIN
(`~/.agents/crow/src/crow-cli`).

## Items (unordered)

- [x] Push main (the ACP v2 execute fix) — `a92fc4a3` → origin/main.
- [x] Confirm `crow-cli install web` is already wired
      (`src/crow_cli/cli/install_web.py`): `bun install` → `bun run web:build`
      → `cargo build --release -p crow-web` → `~/.local/bin/crow-web` + systemd
      user unit. Verify with `crow-cli install web --help`.
- [x] Editor theming: CodeMirror editor follows the app theme (latte/mocha/
      macchiato) by building its highlight style from the `--code-*` token
      variables instead of hardcoded `oneDark`/`defaultHighlightStyle`.
      Verify: `bun run web:typecheck` + `bun run web:build` exit 0; live browser
      shows editor token colours change with the theme dropdown.
- [ ] Electron shell: `packages/electron` (standalone, NOT a workspace member)
      whose main process spawns the `crow-web` binary (embedded SPA) and loads
      its loopback URL in a BrowserWindow. Pure spawn/parse logic in
      `launcher.cjs`, unit-tested with `bun test`.
      Verify: `bun test` green, `node --check main.cjs` clean.
- [ ] `crow-cli install gui`: build SPA + crow-web (reuse the web build), install
      the Electron app + a `~/.local/bin/crow-gui` launcher + a `.desktop` entry.
      Verify: `crow-cli install gui --help` lists it; `--dry-run` reaches the
      copy/launcher steps without downloading electron.
- [ ] Remove the `install desktop` / `install check` cruft that downloads
      `odellus/sidex` (a different repo) — the real GUI install replaces it.

**Floor gates (every item):** `bun run web:typecheck` + `bun run web:build` PASS.
