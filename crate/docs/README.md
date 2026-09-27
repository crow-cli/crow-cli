# docs

What is left here, and what each file is for. Everything Martty-era — the
Cordis plugin host, the dsh profile, the npm bundle, the Node migration plan,
the harness CLI, the architecture diagrams — has been deleted rather than left
to mislead. It is in the git history.

| | |
|---|---|
| [`sessions.md`](sessions.md) | session tabs, history, resume, and the per-tab message queue |
| [`composer-input.md`](composer-input.md) | the input widget: every keybinding, IME behaviour, and how it is wired to `ratatui-textarea`. Still in Chinese; it is accurate |
| [`tui-palette.v0.schema.json`](tui-palette.v0.schema.json) | the palette format |
| [`fixtures/`](fixtures/) | palettes that parse against that schema |

## fixtures/

Nothing in `src/` reads this directory at runtime. The files are test fixtures,
pulled in with `include_str!` from `tests/unit/`:

- the eight shipped palettes — `ayu`, `catppuccin`, `everforest`, `iceberg`,
  `kanagawa`, `one`, `solarized`, `tomorrow`
- `demo-skin.v0.json` — a light/dark pair used by the theme, palette, events
  and ui tests
- `demo-surface.v0.json` — referenced by nothing. Kept as a schema example

The `--demo-skin` flag that used to load the gallery skin is gone;
`tests/cli_help.rs` pins its absence.

## Not here

The constraints that actually govern this crate are in
[`../AGENTS.md`](../AGENTS.md), not in `docs/`. The build and test commands are
in [`../README.md`](../README.md).
