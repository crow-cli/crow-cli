# TODO — chat is the extension's webview; delete the orphaned front ends

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Sprint: the product is the **vscode extension** (`packages/vscode-acp`) plus
**`crow serve-web`** (the IDE's own browser server). `packages/chat` now exists
*solely* as the extension's webview source. Remove the editor pane, the bottom
terminal and everything else the extension cannot reach; delete the orphaned
crates and shells that only the old "web IDE in a Rust server" route needed.
**Leave the Python alone** except for orphaned test/script files whose subject
is deleted. The workflow that must still work, from this worktree, is
**`crow-cli install crow`**.

Worktree: `~/.agents/crow/src/worktrees/crow-cli-cleanup` (branch
`crow-cli-cleanup`, off `main` @ 94510f6b). Ordered execution: `PLAN.md`.

## Items (unordered)

- [ ] **A. The empty-editor watermark is the wrong SVG.** *(separate item —
      written down before any deletion, and executed as its own phase)*
      What renders when an editor group has nothing to display is still
      VSCodium's codium glyph, not crow's:
      `packages/crow-gui/vscodium/src/stable/src/vs/workbench/browser/parts/editor/media/letterpress-{dark,light,hcDark,hcLight}.svg`.
      Those four files are the `background-image` of `.letterpress` in the
      editor-group watermark — upstream `src/vs/workbench/browser/parts/editor/media/editorgroupview.css:129-150`
      (one url per theme, `background-size: contain`, `aspect-ratio: 1/1`,
      `max-width: 256px`), element created at `editorGroupWatermark.ts:105`.
      Replace the glyph with crow's mark, keeping each file's theme colour and
      its `<g id="codium_grey_*_letterpress">` wrapper. Mechanism: extend
      `packages/crow-gui/make_icons.py` (it already generates
      `src/stable/src/vs/workbench/browser/media/code-icon.svg` into the same
      tree) with a `write_letterpress()`, run it, commit art + generated files —
      `build.sh` does `cp -rp src/stable/* vscode/` on **every** run, so the swap
      lands in the desktop app and in `serve-web` alike.
      Facts already established: `art/crow-logo.svg` is one `<path>` in a
      `0 0 1024 1024` viewBox, glyph alpha bbox `(166,152,856,853)` — centred,
      ~67% of the box, **no transform needed**. The path carries
      `style="fill:#ffffff;fill-opacity:1"`, which **overrides** its
      `fill="none" stroke="#000000" stroke-width="1"` attributes (inline style
      beats presentation attributes). That is why `make_icons.py`'s comment
      calls the art "a stroke-only outline that vanishes" and embeds a raster
      instead. The generated letterpress must therefore set `fill` as an
      attribute and **drop the `style`**, or the watermark renders solid white.
      Colours to preserve per variant: dark `#B2B2B2` @ `fill-opacity="0.3"`,
      light `#B2B2B2` @ `0.1`, hcDark `#3C3C3C` (no opacity), hcLight `#B2B2B2`
      (no opacity). Source of the art: the tracked, metadata-stripped
      `packages/crow-gui/art/crow-logo.svg` (same path data as
      `~/src/crow-gui/crow-logo.svg` minus the Inkscape/Sodipodi cruft).

- [x] **B. Refactor `packages/chat` down to what the extension imports.**
      Delete the 35 files unreachable from `src/vscode.tsx` (SPA entry, work
      pane, explorer, bottom terminal, their stores and clients, the SPA-only
      ui primitives), prune the 7 dependencies nothing left imports, and drop
      the SPA build scaffolding. Keep every reachable file **byte-identical** —
      this is a subtraction, not a redesign.

- [x] **C. Delete `packages/editor`** (`@crow/editor`). One consumer ever:
      `chat/src/components/work/work-pane.tsx`. Orphaned by B.

- [x] **D. Delete `crates/crow-web`** — the Rust state server (fs buffers, ptys,
      `/acp` proxy) that embedded `packages/chat/dist` via `rust-embed`. Nothing
      else reads that dist.

- [x] **E. Delete `packages/electron`** — an Electron shell whose whole job is
      spawning the `crow-web` binary (`main.cjs:startServer`). Orphaned by D.

- [x] **F. Delete `crates/crow-gui`** — the ratatui-over-wgpu/wasm UI service —
      and everything that hangs off it: crow-client's `gui` feature + optional
      dep, `src/gui/`, the `--gui` flag, `tests/unit/gui__tests.rs`, the `--gui`
      assertions in `main__cli_args_tests.rs`, `packaging/crow-gui.desktop` (the
      deb asset switches to `packaging/crow.desktop`), `scripts/build-web.sh`,
      `scripts/test-web.sh`, `web/index.html`, and
      `tests/e2e/test_web_paint_live.py`.

- [x] **I. Un-orphan `crates/crow-client`'s integration tests.** Five test files
      (`cli_help.rs`, `tcp_attach.rs`, `sigterm_cleanup.rs`,
      `startup_session_e2e.rs`) still say `env!("CARGO_BIN_EXE_crow")`, but
      `bc03c5c7` renamed the bin to `crow-agent`, so `cargo test -p crow-client`
      has been **red on main ever since** — 5 compile errors, no test results at
      all. Rename the six sites to `CARGO_BIN_EXE_crow-agent`. Without this the
      sprint has no Rust gate: Phase 4 has to prove `gui__tests.rs` is gone and
      the rest still pass.

- [ ] **G. Docs and manifests**: root `Cargo.toml` members, root
      `package.json` (description + the `web:*` scripts), `README.md`
      (the `crow-web` rows/sections, the repo map, the cargo `-p` note),
      `AGENTS.md` (the `cargo run -p crow-web` launch recipe and the arg table
      rows), `crates/crow-client/README.md` (the `crow-gui.desktop` /
      `Exec=crow --gui` paragraph).

- [ ] **H. Reproduce `crow-cli install crow` from this worktree.** The gate that
      matters: `./build.sh --arch x64 --deb` (seeds the VS Code checkout from
      `~/src/crow-gui/vscode`, which has the pinned `08d4889` / 1.135.0), the
      bun build of `packages/vscode-acp` **with chat as its webview root**, the
      bundled built-ins, `cargo build --release --bin crow-agent`, `dpkg -i`.

## Explicitly NOT in scope

- `packages/crow-gui` (the IDE build pipeline) — that IS the product. Only its
  `make_icons.py` + the four generated letterpress SVGs change (item A).
- `packages/aui/*` — chat imports `@assistant-ui/{acp,core,react,react-markdown}`.
- `crates/crow-client` itself (the TUI) — minus the `--gui` runtime (item F).
- `src/crow_cli/**` — the Python stays as-is. `install.py`'s docstring keeps its
  historical "the old `install web` / `install gui` are gone" sentence, which is
  still true and now doubly so.
- The name collision is real and stays: `/usr/bin/crow-web` shipped by the .deb
  is the **IDE's reh-web server**, unrelated to `crates/crow-web`. So are the
  `"crow-web"` MCP slice label in `tests/e2e/test_mcp_multi_server.py:94` and the
  docstring example in `src/crow_cli/mcp/server/main.py:14`.

## Floor gates (every item) — Phase 0 baselines, measured in this worktree

- `bun install` at the worktree root — exit 0 (773 packages)
- `bun run --cwd packages/chat typecheck` — exit 0
- `bun run --cwd packages/chat test` — **35 pass, 0 fail, 3 files**
- `bun run --cwd packages/vscode-acp build` — exit 0, writes `dist/extension.cjs`
  and `dist/webview/{chat.js,chat.css,assets/}` (this is the extension the IDE
  bundles; it compiles chat as its webview)
- `bun run --cwd packages/vscode-acp typecheck` — exit 0
- `cargo build --release --bin crow-agent` — exit 0, 90s (one pre-existing
  warning: `ui_preset` is never read)
- `cargo test -p crow-client` — **982 pass, 0 fail** (964 unit + 3 + 1 + 13 + 1),
  but only after item I: on `main` this is 5 compile errors, rc 101
- `uv --project . run pytest tests/unit tests/integration -q` — **1089 passed,
  6 failed** in 331s. The 6 are the known environmental set and are the
  baseline, not a regression: `test_run_screenshot_rides_the_row` (needs a real
  browser), `test_the_v2_prompt_lifecycle_lands_on_the_wire_in_order`,
  `test_a_child_that_dies_mid_turn_marks_the_task_failed`,
  `test_a_poke_for_a_foreign_session_is_dropped_without_disturbing_ours`,
  `test_a_child_that_dies_mid_turn_raises_instead_of_hanging`,
  `test_a_delegate_that_dies_is_reported_and_not_hung` (all four spawn a child
  agent process and die on `ConnectionError: Connection closed` / timeout).
- `git grep -n` for the deleted names returns only intentional history/prose
