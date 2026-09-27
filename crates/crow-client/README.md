# crow-term

A terminal, and the things that live in it.

This README is honest about the gap between the two: **what we are building
toward** is a monorepo of Rust apps that share one terminal, one agent protocol
and one theme. **What exists today** is one of those apps — an ACP client TUI —
plus a set of sibling checkouts that are not yet part of anything. Neither half
is finished, and the parts that are finished still carry branding from the
project this one was forked out of.

---

## What we are building toward

One terminal emulator, and a set of first-party apps that ship inside it,
preinstalled and preconfigured. You do not assemble this stack; you get it, and
you get **one theme selector** that drives all of it.

| name | what it is | where it comes from | license |
|---|---|---|---|
| **crow-term** | the terminal emulator itself — the base executable | fork of [rio](https://github.com/raphamorim/rio): `frontends/rioterm` for native, the wasm frontend for the browser | MIT |
| **crow** | the ACP client — talk to a coding agent inside the terminal | what the `crow-term` crate in this repo is *today*, renamed | MIT |
| **murdr** | a crow agent orchestrator: panes that keep running when you detach, per-pane agent state, several machines in one window | fork of [herdr](https://herdr.dev), rebranded and rebuilt around ACP instead of herdr's own socket API | Apache-2.0 |
| **starship** | the shell prompt | [starship/starship](https://github.com/starship/starship) | ISC |
| **fresh** | the text editor | [sinelaw/fresh](https://github.com/sinelaw/fresh) | GPL-3.0-or-later |
| **emeraldian** | notes — an Obsidian-shaped TUI over a plain folder of Markdown | [emeraldian](https://github.com/iamrohithrnair/emeraldian), on its `acp` branch | GPL-3.0-or-later |

The license column is not decoration. This crate is MIT; `fresh` and
`emeraldian` are GPL-3.0-or-later. Vendoring either into a shared workspace, or
linking them into one binary, changes what the result can be licensed as.
Shipping them as **separate executables** that the terminal launches does not.
That is an argument for keeping the monorepo a repo of independent binaries
rather than one linked product, and it has not been decided either.

Structurally this becomes a **monorepo with several crates that each compile to
an app**, rather than one binary crate. Whether a given component is forked into
the tree or consumed as a library dependency is decided per component and is
**not decided yet** — rio and herdr are the two we expect to fork, starship and
fresh are the two we expect to depend on, and emeraldian is genuinely open.

The load-bearing idea is the theme. Every one of those apps has its own theme
system today (rio's config, starship's palettes, fresh's themes, emeraldian's
`emeraldian-theme`, this repo's `tui-palette.v0`). One selector has to reach all
of them, which means either a shared palette format every app can read or a
config writer that speaks each app's dialect. That work has not started.

**None of the above is built.** It is the direction, written down so the
decisions below have something to be decided against.

---

## What exists today

### This repo: `crow-term` v0.2.39

A pure-Rust binary crate. No Node, no npm, no plugin host — the JavaScript layer
this project was forked out of is deleted, not dormant, and the git history is
full of it.

```
cargo build --release -j 6      # -> target/release/crow-term
cargo test --locked             # the only gate
```

What it does: spawns an [ACP](https://agentclientprotocol.com/) agent as a child
process over stdio and renders the conversation — streaming text, reasoning,
tool calls, plans, token usage, images, persisted sessions. The protocol is
**negotiated, never declared**: one union `initialize` goes out over the live
channel and the response decides whether `src/acp.rs` (v1) or `src/acp/v2.rs`
handles the connection. A harness is an argv, not a config schema.

- `agent-client-protocol` 2.0.0, behind `unstable_protocol_v2`
- `ratatui` 0.30.2 + `crossterm` 0.29, `tui-markdown`, `syntect`,
  `ratatui-textarea`, `ratatui-explorer`, `tui-tree-widget`
- settings at `~/.agents/crow/settings.json` — patched, never rewritten;
  an unparseable file is quarantined rather than replaced
- 24 slash commands, catalogued in `src/app/slash_catalog.rs`
- 8 palettes in `docs/fixtures/` against `docs/tui-palette.v0.schema.json`:
  ayu, catppuccin, everforest, iceberg, kanagawa, one, solarized, tomorrow
- `tests/startup_session_e2e.rs` drives the **shipped binary** on a real PTY
  against a stub ACP agent — that, not a mock, is how behaviour gets proven

Read [`AGENTS.md`](AGENTS.md) before changing anything. It is the list of
constraints that have already bitten an agent — protocol negotiation, the
single connection, the tokio runtime rule, the test layout.

### The sibling checkouts

These live next to this repo under `../` and are **not** wired into it. No
workspace, no shared build, no path dependencies.

| directory | remote | branch | state |
|---|---|---|---|
| `../rio` | `crow-cli/rio` | `main` | forked, full workspace: sugarloaf, corcovado, teletypewriter, rio-vt, `frontends/rioterm`, `frontends/wasm` |
| `../herdr` | `odellus/herdr` | `master` | forked; upstream is v0.9.x, Apache-2.0 |
| `../emeraldian` | `odellus/emeraldian` | `acp` | forked on an `acp` branch; workspace crates `acp`, `emeraldian-core`, `emeraldian-theme`, `emeraldian-agent`, `emeraldian` |
| `../fresh` | `sinelaw/fresh` | `master` | upstream clone, not forked |
| `../starship` | `starship/starship` | `main` | upstream clone, not forked |
| `../crow-cli` | `crow-cli/crow-cli` | `main` | the ACP *agent* crow-term talks to; Python, on PyPI |

### What is still vestigial here

Listed so nobody mistakes it for intent:

- `src/theme.rs` is a 1:1 map of DeepSeek's web design tokens, and
  `src/deepseek_logo.rs` and `assets/martty-lockup.svg` are still in the tree
- `/plugins`, `/cordis-plugins`, `/ui` and `/liang` are live slash commands
  pointing at a Cordis plugin host that no longer exists; `src/cordis.rs` and
  `src/slots.rs` are the same story
- `src/locale.rs` requires a Chinese description for every builtin command, so
  the command surface is bilingual by construction
- `docs/composer-input.md` is accurate and still in Chinese

---

## Docs

| | |
|---|---|
| [`docs/README.md`](docs/README.md) | index of what is left in `docs/` |
| [`AGENTS.md`](AGENTS.md) | the real constraints — protocol negotiation, the single connection, the tokio runtime rule, the test layout |
| [`docs/sessions.md`](docs/sessions.md) | sessions, history, message queues |
| [`docs/composer-input.md`](docs/composer-input.md) | the input widget: every keybinding, and how it is wired |
| [`docs/tui-palette.v0.schema.json`](docs/tui-palette.v0.schema.json) | the palette format, with `docs/fixtures/*.v0.json` as examples |

The Martty-era docs — Cordis plugins, the dsh profile, the npm bundle, the Node
migration plan, the harness CLI — have been deleted rather than left to mislead.
They are in the git history.

## License

MIT — see [LICENSE](LICENSE).
