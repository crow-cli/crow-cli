# Agent notes

## ⛔ READ THIS FIRST — what is vestigial, and what is not

**The product is one Rust binary. There is no Node in it, and none next to it
either.** The `npm/` layer, the `Makefile`, `.github/`, the `scripts/*.test.mjs`
suite, `scripts/real-agent-e2e.py` and `scripts/check-release-tag.mjs` are
deleted, not dormant. If a commit message, an old note here, or your own
recollection points at one of them, it is stale.

There is no plugin host, no profile system, no client-plugin tree, no
`ctx.acpClient`, no agent pool and no second process. Nothing answers the
`_crow/tui/*` extension family in `src/ext.rs` either, which is why four slash
commands are parked (below). The user runs `./target/release/crow` directly.

What *is* still vestigial, and exactly where:

- `src/theme.rs` is the palette layer and nothing else: the house ramp
  `CROW_50…CROW_900`, the six `BUILTIN_PALETTE_IDS` packs (`default` wears the
  house ramp; four Catppuccin flavors; one retained blue pack, listed last
  because it is the odd one out), and the protocol-0 parse. There is no logo
  module and no lockup asset anywhere in the tree.
- `/plugins`, `/dynamic-plugins`, `/ui` and `/liang` are **parked, not live**:
  commented out of `SLASH_COMMANDS` at their alphabetical positions, each with a
  note naming the machinery that is still compiled and tested. `src/ext.rs` is
  the wire-name table for the host that does not exist; `src/slots.rs` and
  `src/pet.rs` are the receiving ends. `run_slash` still resolves all four.
- **Anything that "arrives from a compositor slot snapshot" never arrives.**
  `app.harness_badge` is fed from the `conversation.harness` slot in
  `src/app/pump.rs`, so it is permanently empty. Chrome, badges and palettes
  must be driven from the Rust side (`CtlEvent` / `AppEvent`), never from a
  host that does not exist.
- Every builtin slash command still needs an explicit zh description in
  `src/locale.rs command_desc`, or
  `every_builtin_command_has_an_explicit_zh_desc` fails. A real gate on a
  vestigial requirement — do not "clean it up" without also removing the test.

Consequences that have already bitten an agent:

- **The `/` namespace has three sources, and builtins win.** `SLASH_COMMANDS`
  in `src/app/slash_catalog.rs` is resolved client-side in the painter. The
  agent's `availableCommands` arrive as host skills in the same menu
  (`skills_from_available_commands` at `events.rs:950`, fed from
  `acp.rs:1804-1819` and `acp/v2.rs:785`) — that path is live, and this
  repo's own agent uses it (`src/crow_cli/agent/main.py:566`). A compositor
  could also push client plugin commands over
  `_crow/tui/commands/update`; nothing does, so that source is parked with the
  four commands above. Both non-builtin sources are filtered against the
  builtin names (`app/slash.rs:43,74`), so a builtin can never be shadowed,
  and each group stays alphabetical.
- **The Rust suite is the only gate.** There is no other suite, and no CI.

Read [`README.md`](README.md) for what this repo is becoming versus what it is
today. [`docs/README.md`](docs/README.md) indexes what is left in `docs/`.

## Commands & verification

- **Rust is the only gate**: `cargo test --locked` and `cargo check --locked --tests`. `scripts/cargo-guard.sh` wraps cargo with cache-size and disk guards (`CROW_RUST_CACHE_MAX_GIB`); there is no Makefile, so call it directly or just run cargo. No clippy/fmt gate exists. Never run repo-wide `cargo fmt` — `acp.rs`, `app.rs` and `ui.rs` carry hundreds of pre-existing rustfmt markers; format only files that are entirely new, and check `rustfmt --check` line numbers against `git diff -U0` for existing ones.
- ⛔ `scripts/cargo-guard.sh` must **never** auto-clean the target dir. It used to `cargo clean` `$CROW_CARGO_TARGET_DIR` (= `$PWD/target`) at 20 GiB and deleted a release build mid-test-run. Over the limit it warns; pruning is explicit (`cargo-guard.sh prune`). The user builds with bare `cargo build --release -j 6` into `$PWD/target` and tests from it. Do not reintroduce auto-clean.
- Linker OOM: on small-RAM machines `cc`/`ld` can get killed (signal 9) linking the test binary. Retry with `RUSTFLAGS="-C link-arg=-fuse-ld=mold" cargo test` (mold is much lighter). `release` uses `lto = true` and is slow — verify with debug builds.
- Rust unit tests live in `tests/unit/*__tests.rs` but are wired in by a `#[cfg(test)] #[path = "../tests/unit/…"] mod tests;` include at the bottom of the owning `src/*.rs` file — add that include for new test files.
- No-TTY visual check: `cargo run -- --dump-frame 100x34` renders the canned demo frame as text; useful to diff transcript/markdown output before and after a rendering change.
- Demos: `crow --demo` runs the canned transcript on the built-in `default` theme. `--demo-skin` is gone and `tests/cli_help.rs` pins its absence — do not reintroduce it. The full flag list is `parse_args_from` in `src/main.rs`; nothing in the binary spawns `node`.
- Driving the real binary in tests: `tests/startup_session_e2e.rs` spawns the **shipped binary** on a real PTY against `tests/fixtures/stub_acp_agent.py` (dual-stack: `STUB_PROTOCOL=1|2`, `STUB_CAPS=load|resume|both|none`, `STUB_LOG` writes a wire log). That is how behaviour gets proven — a real PTY and the real binary, not a mock. Validate a Python fixture with `python3 -m py_compile`, never `ast.parse`.

## Release & versioning

- The version lives in one file: `Cargo.toml`. There is no npm package, no release-tag checker and no `.github/` — CI for this repo is not set up yet.
- `CHANGELOG.md` went with the rest of the fork's release scaffolding. There is no changelog process; do not recreate one without being asked. `PLAN.md` and `TODO.md` at the repo root are the rebrand sprint's working documents — they are supposed to be there, and they get updated as each phase lands.

## crow architecture — the constraints that ARE real

- **The protocol is negotiated, never declared.** `src/acp/negotiate.rs` sends
  one union `initialize` over an already-live `Channel`, then `classify` →
  `adopt` picks the stack: `src/acp.rs` (v1) or `src/acp/v2.rs`. A harness entry
  is an **argv** — there is no `protocol:` field and no pin override. v2 is
  gated behind the `unstable_protocol_v2` feature.
- **One connection serves every tab.** There is no per-agent pool. Replacing the
  agent means replacing the live connection: `Cmd::SwitchHarness { argv }` is
  intercepted by `relay_commands` *above* `run()` (a stack cannot recover
  `cmd_rx` — both move it into a forwarder thread that dies on send failure),
  and `run_blocking` is a supervisor loop that respawns and renegotiates.
- ⛔ **`run_blocking` keeps ONE tokio runtime for every generation.** Never
  `tokio::spawn` and drop the `JoinHandle` inside it — a detached task outlives
  its connection holding the transport, and the transport holds the child guard,
  so the agent process leaks. `negotiate_and_run` keeps the handle and calls
  `driver.abort()` on every path out. Making a runtime long-lived turns every
  detached task in it into a leak.
- The bus is `std::sync::mpsc`. Teardown is channel-close driven
  (`let Some(mut cmd) = cmd else { break }`), the same exit as `Cmd::Shutdown`.
  `AppEvent` and `PickerKind` have **no `Debug`**; `Cmd` derives `Debug, Clone`
  only, no `PartialEq`. Tests must map events to strings or use `matches!`.
- **Transcript paint comes from ACP `session/update`.** Live, the painter echoes
  user prompts locally and the parser skips the agent's copy; on replay the log
  is the only source. The discriminator is wire order — v2's `ReplayWindow`
  gates the echo on whether the update arrived before the `session/resume`
  response. Do not "fix" the double print by dropping the echo.
- `concat_text_blocks` joins with **no separator**. A test pins that. It is not a
  bug to fix.
- Settings live at `~/.agents/crow/settings.json` (`src/runtime.rs`). Writes
  **patch, never rewrite** (`serde_json` `preserve_order` is on transitively, so
  key order survives), create-if-absent, and **quarantine** a non-empty
  unparseable file rather than replace it.
- crow is a **binary crate**, edition 2021, built with rustc 1.98 → avoid
  `let_chains` (they are edition-2024-only). Unit tests live in
  `tests/unit/*__tests.rs` and are wired in by a `#[cfg(test)]
  #[path = "../tests/unit/…"] mod …;` include at the bottom of the owning
  `src/*.rs` (from `src/acp/*.rs` the path is `../../tests/unit/…`).
  Test modules sit inside the source module, so `use super::*` reaches private
  items. `cargo test --lib` fails — use `--bin crow`.
- Slash commands are `SLASH_COMMANDS` in `src/app/slash_catalog.rs`, **name-sorted and a test
  enforces it**. Every builtin needs an explicit zh description in
  `src/locale.rs command_desc` — `every_builtin_command_has_an_explicit_zh_desc`
  fails otherwise.
