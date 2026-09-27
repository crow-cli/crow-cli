# TODO — the crow-client rebrand: no deepseek, no martty, no dsh

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Sprint origin: 2026-09-27, session `amorphous-refreshing-peacock-of-psychology`.
Worktree `~/.agents/crow/src/worktrees/crow-cli-rebrand`, branch
`client-rebrand`, off main @ `4eea50f1`.

The previous sprint in these two files (`/goal` on the task guts) is complete —
every item checked. It lives in git history; these files are now this sprint.

## The mandate, in the user's words

> I think having a deepseek theme is fine and dandy.
>
> Defaulting to deepseek url and api keys is not. it cause considerable
> aggrevation for previous model because it thought we needed deepseek api keys
> (it's not very smart). So removing from default models with built in providers
> is first step imo. it makes zero sense for an ACP client to be handling that on
> its side. the agent has the model configurations it exposes to the client.
> that's how ACP works. there's no "hand providers to ACP agent" channel of ACP.
> The agent exposes the models it can select from to client, which can then
> choose.
>
> env contract - yeah this is really important we clean this up and make this NOT
> DEEPSEEK OR MARTTY SHAPED. No martty shims. NO deepseek shims. rebrand. break
> "existing installs" whatever the fuck that's supposed to mean. we do not want
> backwards compatibility with martty that's daft.
>
> yeah this is not deepseek harness's client anymore. this is crow-cli's harness.
> we want to rename in a way that's intelligent.
>
> we want to get rid of liang for now but keep machinery in case we want to add
> our own crow pet later. so don't delete but just comment out of whereever it's
> included in slash command registry or whatever for now.
>
> okay so the other agent is done cleaning up our system prompt. let's start
> hacking on the client and getting rid of deeseek, martty, and dsh branding

Four rules fall out of that, and they decide every ambiguous case below:

1. **The client owns no model config.** No built-in provider, no built-in model
   list, no base-url, no api key. The agent advertises its models over ACP; the
   client picks from what arrives.
2. **No back-compat shims.** Martty homes, dsh credential stores, dsh settings
   files, dsh env aliases: deleted, not fallback-ed. Breaking a pre-rebrand
   install is the intended outcome.
3. **A deepseek *palette* may stay.** Brand *art*, brand *defaults*, brand *wire
   names* and brand *env vars* may not.
4. **Liang: unregister, don't amputate.** The pet machinery stays compiled and
   tested; only the slash-command registry entry goes, so a crow pet can be
   dropped in later.

## Gate (floor for every item)

```
cd ~/.agents/crow/src/worktrees/crow-cli-rebrand
cargo check --locked --tests -j 6          # ~30s warm
cargo test  --locked --bin crow -j 6       # 934 tests at baseline
cargo run -- --dump-frame 100x34           # no-TTY visual diff
```

`cargo test --lib` fails by design — the unit tests are `#[path]`-included into
the bin. Never run repo-wide `cargo fmt`. Baseline is green with 3 pre-existing
warnings (unused `Path` import, unused `ctl`, non-snake-case
`dd_kills_the_line_and_gg_G_jump`) — do not "fix" them as a drive-by, and do not
add a fourth.

**Phase 1 gate result:** `cargo check --locked --tests -j 6` rc 0 with exactly
those 3 warnings; `cargo test --locked --bin crow -j 6` → **938 passed, 0
failed** (934 baseline + 4 new pins); `cargo test --locked --test cli_help` → 3
passed (1 new); `--dump-frame 100x34` byte-identical to the pre-phase frame.
Committed `40d15472`.

**Phase 2 gate result:** check rc 0, still exactly those 3 warnings;
`cargo test --locked --bin crow -j 6` → **939 passed, 0 failed** (one shim pin
promoted to its own test); `--dump-frame 100x34` byte-identical to the Phase-1
frame — no paint change, and `main.rs` is untouched. Committed `30ee65fb`.

**Phase 3 gate result:** check rc 0, still exactly those 3 warnings;
`cargo test --locked --bin crow -j 6` → **940 passed, 0 failed**; `--dump-frame
100x34` byte-identical to the Phase-2 frame.

**Phase 4 gate result:** recorded in PLAN.md — check rc 0, still exactly those
3 warnings; **941 passed, 0 failed** (940 → 941); `--dump-frame 100x34`
byte-identical through 4.1–4.3, then a two-line textual diff in 4.4 (the
re-wrapped demo conclusion and the `demo-flash · demo` chip) with all 35 rows
intact. Committed `b05bd263`.

**Phase 5 gate result:** check rc 0, still exactly those 3 warnings (the
unused-`ctl` one moved `ui__tests.rs:3582` → `:3602` — 5.3's rewrite added 20
lines above it; same warning, same binding); `cargo test --locked --bin crow
-j 6` → **941 passed, 0 failed** (941 → 941: one test rewritten and relocated,
one rewritten in place, four repointed, none added, none deleted); `cli_help` 3,
`startup_session_e2e` 12, `sigterm_cleanup` 1, `tcp_attach` 1 all green.
`--dump-frame 100x34` byte-identical to the Phase-4 frame under both the
developer's `CROW_HOME` and a clean one, `--demo` identical to plain — a
namespace rename repaints nothing.
*Not a gate, but recorded:* the bin-profile build warns `field ui_preset is
never read` (`app.rs:177`) — 4.1 deleted its last reader, the `--tests` gate
cannot see it because the settings round-trip tests read the field, and the
field must stay or the next patch-write drops `uiPreset` out of
`settings.json`. Whether it should drive something now is a product call for
7.4/7.5, not a drive-by `#[allow]` inside a rename phase.

**Phase 6 gate result:** check rc 0, still exactly those 3 warnings (same three
lines, same bindings — a fixture rename moves nothing in `src`); `cargo test
--locked --bin crow -j 6` → **941 passed, 0 failed** (941 → 941: none added,
none deleted; three test fns renamed to match their new fixtures —
`dsh_acp_terminal_login_…`, `dsh_question_schema_…`,
`live_deepseek_landing_also_uses_acp_…` — plus the `dsh_acp_methods` helper;
nine assertions rewritten from vacuous negatives into positive pins; three
geometry fixtures corrected); `cli_help` 3, `startup_session_e2e` 12,
`sigterm_cleanup` 1, `tcp_attach` 1 all green. `--dump-frame 100x34` → 1815
chars / 35 rows, byte-identical to `/tmp/rebrand-p4-baseline.frame` under a
clean `CROW_HOME` — test vocabulary never reaches the paint. 23 files changed,
377 insertions, 373 deletions.

**Phase 7 gate result:** check rc 0, still exactly those 3 warnings (same three
lines, same bindings — docs, comments and fixture names move nothing in `src`);
`cargo test --locked --bin crow -j 6` → **941 passed, 0 failed** (941 → 941:
none added, none deleted, none renamed — 7.5 changed fixture *vocabulary* and
prose, not test identities); `cli_help` 3, `startup_session_e2e` 12,
`sigterm_cleanup` 1, `tcp_attach` 1 all green. `--dump-frame 100x34` → 1815
chars / 35 rows / 2819 bytes on disk, byte-identical to
`/tmp/rebrand-p4-baseline.frame` (saved as `/tmp/rebrand-p7-clean.frame`) —
deleting 4.63 MB of brand art and rewriting three prose files repaints nothing,
because none of it was ever loaded at runtime. Crate diff: 25 files changed,
138 insertions, 245 deletions.
*Recorded because a cached green looks exactly like a real one:* cargo replays
stored warnings for a unit it considers fresh, so both binaries were checked
against the clock — test bin `crow-e748d5d90d72350e` rebuilt 15:29:31,
`target/debug/crow` 15:29:37, last source edit 15:24:29. Also verified out of
band: `bash -n scripts/collect-freeze-diag.sh` rc 0, the palette schema and all
10 `docs/fixtures/*.json` re-parsed, and `git log -S` for the two historical
claims 7.1/7.5 rest on.

**Phase 8 gate result:** the whole gate, in both profiles, on the artifact that
ships. *Debug:* check rc 0 with exactly those 3 warnings (same three lines, same
bindings, all on stderr in short format); `cargo test --locked --bin crow -j 6`
→ **941 passed, 0 failed**; `cli_help` 3, `startup_session_e2e` 12,
`sigterm_cleanup` 1, `tcp_attach` 1; `--dump-frame 100x34` → 1815 chars / 35
rows / 2819 bytes, byte-identical to `/tmp/rebrand-p4-baseline.frame`.
*Release:* `cargo build --release -j 6` rc 0 in 128 s → `target/release/crow`,
11.9 MB, one warning — the deliberate `field ui_preset is never read`
(`app.rs:177`); the same four integration tests re-run with `--release` → 3 /
**12** / 1 / 1, so **17** tests drove the shipped binary; its `--dump-frame` is
byte-identical to the same baseline (saved `/tmp/rebrand-p8-release.frame`);
`--help` 1484 chars with no brand and no credential flag; `--demo` on a **real
PTY** (openpty/fork/`execve`, TIOCSWINSZ 110×30, 5 s, SIGTERM) exits **0**
showing the crow wordmark, `https://crow-ai.dev`, `version crow 0.1.0`,
`runtime demo`, `model waiting for ACP`, `mode demo — scripted turns, no API
calls`, `session crow-65c7c5f0` — and **zero** occurrences of `deepseek`,
`martty`, `dsh` or `api key` in 5897 chars of live UI. *Python:*
`uv run pytest tests/unit -q` from the worktree root → **788 passed**.
The release e2e really points at the release binary: the harness bakes
`env!("CARGO_BIN_EXE_crow")` (`tests/startup_session_e2e.rs:309`, no env
override, so the profile selects the path), and
`target/release/deps/startup_session_e2e-9bd8c126ff9ce174` contains the bytes
`target/release/crow` and not `target/debug/crow`.
*Recorded because a cached green looks exactly like a real one:* 8.1 did not
trust the warm artifacts. A syntax error injected into `src/pet.rs` turned check
rc **101** in 7.4 s (proving the gate compiles this crate, then restored); then
only this crate's debug artifacts were deleted by hand —
`target/debug/{.fingerprint/crow-client-*,deps/crow-*,crow,incremental/crow-*}`,
27 paths, **23.7 GiB** reclaimed, every third-party dep left in place and no
`cargo clean` (AGENTS.md forbids it; the target dir is shared) — and from that
state the 941 and the 3 warnings were recompiled in 86.5 s / 8.2 s. Warm
timings for comparison: check 0.2–1.7 s, bin test 3.4–13 s.
*One red, chased not waved off:* the first Python run was 1 failed / 787 passed
— `test_tools_web.py::test_run_screenshot_rides_the_row`, Playwright
`Page.captureScreenshot: Unable to capture screenshot`. Disproved as a
load flake three ways: it passes alone in 1.8 s, the full suite re-runs **788
passed**, and the branch changes zero Python (`git diff --stat` over
merge-base…HEAD for `*.py`/`src/`/`tests/` returns one entry — the *deletion*
of `crates/crow-client/assets/promo/build.py`).
*The phase's one source change* is the root `Cargo.toml:14-18` comment over
`[profile.devlocal]`, which advertised `DSH_TUI_CARGO_PROFILE=devlocal`, a
nonexistent `scripts/devlocalinstall.sh` and "the shipped npm packages" (gone in
Phase 5). It now names only what exists; the profile itself is untouched, and
`collect-freeze-diag.sh:12`'s `devlocal` stays — that is a `pgrep` path matcher,
not a build instruction.

## Scope capture (unordered)

- [x] **The client stops owning provider/model/credentials.** `MODEL_PRESETS`
      (five hardcoded deepseek ids) is the seed for `/model` when no agent
      catalog has arrived — it goes, and the picker seeds from `last_models`
      plus the effective current model only. `RuntimeConfig.provider`/`.model`
      stop being `String`s with deepseek defaults. `--provider`, `--base-url`,
      `--api-key`, `--max-tokens` leave the flag surface; `--model` stays (an
      explicit "run THIS", applied on bind via the same wire path ctrl+p uses)
      and `CROW_MODEL` stays, `DSH_MODEL` goes.
      *Done (PLAN 1.1–1.3).* `grep -rn MODEL_PRESETS src tests` → 0.
      `RuntimeConfig` is now `{bin, workspace, session_root, startup_session}`;
      the picker seeds from the agent catalog plus `current_model()` only, and
      says "waiting for the agent catalog" when nothing has arrived.
      `crow --help` read top to bottom: no brand name, no credential flag,
      `--model <id>  ask the agent to run this model (default: $CROW_MODEL)`.
      Absence pinned by `tests/cli_help.rs::help_offers_no_provider_route_and_no_credentials`
      and `main__cli_args_tests.rs::removed_runtime_aliases_are_rejected`.
- [x] **`legacy_dsh()` and everything it feeds, deleted.** `~/.dsh/.credentials.yaml`,
      `~/.dsh/settings.yaml` (`agent-default-model`), the two hand-rolled yaml
      scrapers, `LegacyDsh`, `has_credentials()`, `credential_source()`.
      *Done (PLAN 1.5).* `grep -rn "legacy_dsh\|LegacyDsh\|has_credentials\|credential_source" src tests` → 0.
      Gone with them: `unquote`, `yaml_top_level_env`, `yaml_agent_default_model`,
      `CROW_CORDIS_CONFIG`. No fallback was left behind — `runtime.rs` reads
      `settings.json` and nothing else.
- [x] **`child_env()` stops injecting `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL`**
      and stops exporting `CROW_CORDIS_CONFIG` (nothing has ever read it —
      verified: zero consumers in crow-cli's `src/`, `tests/`, `docs/`).
      The harness `env` from `settings.json` still applies.
      *Done (PLAN 1.4).* `child_env()` is now `CROW_SESSION_ROOT`, `CROW_CWD`,
      then the settings.json harness `env` — which still wins, still pinned by
      `harness_env_applies_only_to_the_configured_agent`. New pin
      `runtime.rs::child_env_carries_no_provider_and_no_credentials` asserts no
      key containing `API_KEY`, `BASE_URL`, `MODEL` or `PROVIDER` can reach an
      agent. `grep -rn DEEPSEEK src` → 32 hits, every one a Phase-4 palette or
      logo site (`theme.rs` ramp, `logo.rs`, `markdown.rs` heading ramp,
      `deepseek_logo.rs`); zero env vars.
- [x] **The credential UI becomes ACP-only.** `ui.rs:4248-4262` (the
      `⚠ DEEPSEEK_API_KEY not set` line, EN + zh) and `info.rs:113-119`
      (`api key present · --api-key flag`) collapse into the branch that
      already exists and already tells the truth: credentials are the agent's,
      and ACP `authenticate` is the only sign-in story.
      *Done (PLAN 1.6).* The banner is one honest `else`: "managed by Agent ·
      source not reported". `/status` and `/session` now print
      `- model · {model_identity()}` (`provider · model` / `model` /
      `not reported`) instead of a client-owned `- provider · p / m`;
      `app__right_slot_tests.rs:465` pins `- model · not reported` for the
      nothing-reported case. `grep -rn "API_KEY" src` → 1 hit, and it is the
      guard assertion above, not a credential. `--dump-frame 100x34` (plain and
      `--demo`) is byte-identical to the pre-phase frame — `main.rs:876` sets
      `show_banner = false` for the dump, so the banner was never in it; the
      removal is pinned by the `ui__tests.rs` banner tests instead.
- [x] **No martty/dsh homes.** `crow_home_from` keeps `CROW_HOME` →
      `~/.agents/crow` and loses `MARTTY_HOME` + `DSH_HOME`;
      `legacy_settings_paths*` (`~/.martty/settings.json`,
      `~/.dsh-tui/sessions/dsh-tui-settings.json`) deleted with its callers;
      `sessions.rs` discovers only the configured root, not `~/.crow-term`,
      `~/.martty`, `~/.dsh`, `~/.dsh-tui`; `DSH_TUI_KEYDEBUG` alias deleted
      (`CROW_KEYDEBUG` only).
      *Done (PLAN 2.1–2.4).* `crow_home_from(crow_home, user_home)` — two
      params, one precedence. `legacy_settings_paths*` deleted with both
      callers (`app.rs` import, `app/prefs.rs load_settings`, which is now a
      single read of `settings_path(session_root)` and no migration write).
      `session_roots_from(cfg_root, home)` collapsed into `session_roots(cfg_root)`:
      `$HOME` is no longer consulted at all. `grep -rn "DSH_\|MARTTY_" src` → 0.
      *Correction:* `DSH_TUI_KEYDEBUG` was already dead code — `app.rs:585`
      reads only `CROW_KEYDEBUG`; what survived was a stale comment at
      `keys_router.rs:237` claiming the alias existed. The comment is fixed.
- [x] **The tests that PIN those shims get rewritten, not deleted.**
      `sessions_from_the_martty_and_dsh_homes_remain_discoverable`,
      `legacy_settings_come_from_the_martty_home_then_dsh_tui`,
      `a pre-rebrand MARTTY_HOME keeps its data` currently assert the behaviour
      we are removing. Each becomes the opposite assertion — legacy homes are
      NOT discovered — so the contract stays pinned.
      *Done.* All three inverted, none deleted:
      `sessions_are_discovered_in_the_configured_root_only` writes a real
      session log under each of the four abandoned homes and asserts
      `list_sessions` returns only the configured root's;
      `settings_come_from_the_configured_root_only` seeds valid settings into
      both legacy filenames and asserts `App::load_settings` ignores them;
      `a_pre_rebrand_martty_home_is_not_read` (new, promoted from an assert
      message) exports `MARTTY_HOME`/`DSH_HOME` and asserts `crow_home()` is
      explained entirely by `CROW_HOME` + `HOME`. A fourth shim pin surfaced
      only when the suite ran: `lang_switch_repaints_immediately_and_persists_for_the_workspace`
      seeded `dsh-tui-settings.json` and asserted it migrated — now it seeds
      `settings.json` and asserts the legacy file is neither read nor
      overwritten. 938 → 939 tests, all green.
- [x] **`/liang` out of `SLASH_COMMANDS`** (commented, with a note pointing at
      `pet.rs` + `assets/pet/*.png`), handler and pet machinery untouched.
      `locale__tests.rs` iterates the catalog for the zh-desc gate and for
      name-sort, so both stay green; `run_slash("liang", …)` still works, which
      is what `app__mode_tests.rs:298` and `pet__tests.rs` drive.
      *Done (PLAN 3.1–3.2).* Commented in place with a note naming every
      surviving piece. Both gates green; the catalog is still name-sorted.
      New pin `liang_is_parked_out_of_the_menu_but_the_machinery_still_runs`
      asserts the absence from `SLASH_COMMANDS`, the absence from the menu, and
      that `run_slash("liang", …)` still toggles `pet_visible` — unregister,
      don't amputate. 939 → 940 tests; `--dump-frame` unchanged, no pet.
- [x] **The deepseek *logo* is not a theme.** The `ui_preset == "deepseek"`
      banner branch, `src/deepseek_logo.rs`, `assets/martty-lockup.svg` and
      `scripts/render-martty-lockup.swift` go; `logo.rs` (the crow-cli lockup)
      is the only banner. `ui_preset` keeps its `default`.
      *Done (PLAN 4.1).* Nine files went, not the three named here — the other
      six were unreferenced DeepSeek/martty brand art with no link left.
      `slots.rs` now validates `crow | crow-term` only. Four `ui__tests.rs`
      tests rewritten to pin the new art, none deleted. `grep -rn "deepseek_logo\|martty" src` → 0.
      *Note:* `ui_preset` keeps its `"default"` and its round-trip tests, but
      4.1 deleted its last rendering consumer — it survives as a
      compositor-owned key crow preserves and never reads, which is what
      `settings_io.rs` already claimed it was.
- [x] **The deepseek palette stays a palette.** `theme.rs`'s `DEEPSEEK_50…900`
      ramp survives as a *named* pack; the builtin `default` pack stops wearing
      DeepSeek blue as its brand and wears crow's purple instead
      (`docs/styles/purple.css`, `docs/img/crow-icon-purple.svg` are the house
      brand). `--theme <dark|light>` help text stops saying "DeepSeek Web UI
      palette".
      *Done (PLAN 4.2).* `CROW_50…CROW_900` added, every value read off
      `purple.css` / `crow-icon-purple.svg`; `default` wears `CROW_400`/`CROW_300`
      dark and `CROW_600`/`CROW_500` light. The blue ramp became
      `PalettePack::deepseek()` — `"DeepSeek Blue"`, last in `builtin_packs()`
      and `BUILTIN_PALETTE_IDS`, differing from `default` in the two brand slots
      only. *Correction:* the `--theme` help text was already clean
      (`main.rs:74` reads "colour palette (default: persisted, then dark)");
      `grep -rni "DeepSeek Web UI" src` → 0 before this phase touched anything.
      *Correction:* 11 tests pinned the old blue and were rewritten, not the
      zero the PLAN predicted; one new test
      (`the_deepseek_palette_survives_as_a_pack_and_nothing_more`) now pins rule
      3 itself. 940 → 941. Paint eyeballed under a clean `CROW_HOME` with a
      temporary SGR-emitting `dump_frame` (reverted): lockup `cr` runs
      `#f4f1ff` → `#8b5cf6`, accents `#a78bfa` / `#8b5cf6`, **zero**
      DeepSeek-ramp cells, structure identical.
- [x] **`DeepSeekStyleSheet`** in `markdown.rs` (5 sites) renamed to something
      that says what it is, not who it was copied from.
      *Done (PLAN 4.3).* → `ThemeStyleSheet`, plus the module doc's two palette
      claims and `heading_style`'s ramp (now `CROW_*`). One test repointed
      (`markdown__tests.rs:433`). `grep -rni deepseek src/markdown.rs` → 0.
      Also fixed `theme.rs:780`'s field doc, which still called `brand` "the
      DeepSeek blue accent" — the `--dsw-alias-*` token names stay as
      provenance for the Phase 7.5 sweep.
- [x] **`demo.rs`**: the DeepSeek whale prose (2 passages), and the
      `"provider": "deepseek-official", "model": "deepseek-v4-flash"` in three
      canned JSON payloads, become crow-shaped. `--demo` and `--dump-frame`
      must still render.
      *Done (PLAN 4.4).* Whale prose → crow prose, 🐋 gone; payloads advertise
      `"provider": "demo", "model": "demo-flash"`. Same category, not in the
      PLAN: `controller.rs`'s demo `FetchCatalog` fixture (`demo-flash` /
      `demo-pro`) and `describe_server`'s `.unwrap_or("deepseek-harness")` →
      `.unwrap_or("agent")`. `grep -rni "deepseek\|whale" src/demo.rs` → 0.
      Both `--demo` and `--dump-frame` render; the frame keeps all 35 rows and
      diffs in exactly two (the re-wrapped conclusion, the model chip). The
      pet's XS half-block whale is parked machinery, not brand art, and stays.
- [x] **The `_dsh/cordis` extension family renamed, machinery kept.**
      `cordis.rs`'s 22 wire constants (`_dsh/cordis/tui/*`, `_dsh/plugins/list`),
      the `_meta.dsh.cordis.protocol` capability key the client both reads
      (`advertised_by_agent`) and advertises (`acp_auth.rs:114`), and the Rust
      identifiers around them (`Cmd::FetchCordisPlugins`,
      `CtlEvent::CordisPlugins`, `PickerKind::CordisPlugin|CordisApproval`,
      `pending_cordis_approvals`, `cordis_plugins`, `ensure_agent_cordis`,
      `surface.cordis`, `draw_cordis_approval`, `open_cordis_*_picker`,
      `CordisApprovalsSnapshot`, `CordisPluginItem`, `PendingCordisApproval`).
      Nothing implements this protocol today — AGENTS.md: "anything that arrives
      from a Cordis slot snapshot never arrives" — so renaming the namespace is
      free, and it is the last `_dsh` on the wire.
      *Done (PLAN 5.1–5.2).* `git mv src/cordis.rs src/ext.rs`; all 22 method
      strings are crow's, the capability key is `_meta.crow.tui.protocol` in
      both directions (`advertised_by_agent` reads it, `acp_auth.rs` advertises
      it), and `crate::cordis::` → `crate::ext::` at 163 sites. 82 identifier
      replacements, all landing on the crate's existing static/dynamic axis
      (`DynamicPluginItem`, `Cmd::FetchDynamicPlugins`,
      `PickerKind::DynamicPlugin`, `PendingPluginApproval`,
      `app.dynamic_plugins`, `ensure_agent_ext`, `surface.ext`, …).
      `grep -rni "cordis\|_dsh" src` → **0**; over `src` + `tests` → **1**, the
      Phase-1 pin that `"--cordis"` stays *rejected*.
      *Correction:* PLAN's `_dsh/cordis/plugins/{start,stop}` →
      `_crow/plugins/{start,stop}` collides with `_dsh/plugins/list` →
      `_crow/plugins/list` — two live methods, one name. The dynamic trio went
      under the family prefix (`_crow/tui/plugins/{list,start,stop}`) and
      `PLUGINS_LIST` → `DYNAMIC_PLUGINS_LIST`; the static inventory keeps
      `_crow/plugins/list`, the one method outside the family.
      *Correction:* a mock agent in `acp__tests.rs:278` advertised the old
      `_meta.dsh.cordis.protocol`, so after the rename it had silently stopped
      advertising the family — and still passed, because the compositor paths
      do not require the capability. Green for the wrong reason; fixed.
- [x] **`AGENT_MODES` demo seeds**: the `cordis` "Creator mode" entry and the
      "Shipped creator id is `cordis`" comment.
      *Done (PLAN 5.3).* Fourth seed deleted; three modes now. The doc above the
      constant explains why without using the brand name — the gate is
      `grep -rni cordis src` → 0, so even a historical note has to avoid the
      word. *Correction:* the mode count was pinned in four tests, not zero
      (`stock_presets_cover_the_four_web_ui_modes`, renamed
      `stock_presets_cover_the_shipped_agent_modes`;
      `slash_agent_opens_the_agent_preset_picker`;
      `mode_picker_renders_modes_and_marks_the_current_one`; and the zh-desc
      gate's key). All four rewritten, none deleted.
- [x] **The vestigial plugin slash commands** `/plugins`, `/cordis-plugins`,
      `/ui` — they aim at a plugin host that does not exist. Rename away from
      cordis at minimum; whether they stay registered is a decision to record,
      not to guess at silently.
      *Done (PLAN 5.3).* Decision recorded, not guessed: **parked the way
      `/liang` is** — commented out of `SLASH_COMMANDS` at their alphabetical
      positions, each with a note naming every surviving piece, handlers and zh
      descs untouched so `run_slash` still resolves all three. Shipping three
      menu entries whose only possible answer is "agent does not advertise
      `_crow/tui`" is worse than not shipping them. `/cordis-plugins` was
      renamed **`/dynamic-plugins`** on the way out (`slash_catalog.rs`,
      `slash.rs:510`, `locale.rs:87`, `app.rs:342`, `session_slot.rs:85`), so
      re-registering is one uncomment rather than a rename plus one.
      Absence pinned by
      `the_plugin_commands_are_parked_out_of_the_menu_but_the_machinery_still_runs`
      — one registry assertion per command, a menu pass over `/plug`,
      `/dynamic`, `/ui`, and `run_slash("ui", "")` still opening
      `PickerKind::UiPlugin`. It is the rewrite of the failing
      `slash_menu_offers_the_dynamic_plugin_manager`, relocated next to the
      `/liang` park pin (the closer precedent) rather than next to
      `login`/`logout` as PLAN said. 941 → 941 tests.
- [x] **Test fixture vocabulary**: ~400 hits — `dsh-test` (156), `dsh-acp` (22),
      `dsh-tui`, `dsh-runtime`, `martty-*` temp dirs and env names,
      `deepseek-*` model ids in canned payloads. Renamed to crow-shaped names
      with every assertion's meaning preserved.
      *Done (PLAN 6.1–6.3).* A 67-pair longest-first map applied with
      `edit(replace_all)` over all 54 `tests/**/*.rs`: **329 replacements in 23
      files** (`dsh-*`→`crow-*`, `MARTTY_SHELL_TEST`→`CROW_SHELL_TEST`,
      `martty-*`→`crow-*`, `deepseek-v4*`→`acme-v4*`, `deepseek-v3`→`acme-v3`,
      `deepseek/m1`→`acme/m1`, `current-deepseek-model`→`current-agent-model`,
      `@deepseek-ai/dsh-tool-bash`→`@acme-ai/acme-tool-bash`,
      `builtin-dsh`→`builtin-agent`), then 19 hand edits for the payloads a
      name map cannot reach: auth-method prose the assertions read,
      `uiPreset:"deepseek"`→`"acme-compositor"` (must round-trip verbatim —
      `UiSettings` has no flatten map, so a save would drop it), the `/ui`
      catalog and overlay-select plugin fixtures → `Alpha`/`Beta` with id
      `beta`, `_meta.dsh`→`_meta.acme` (opaque pass-through, and deliberately
      *not* `crow`, which is this client's own capability namespace), and the
      `deepseek-harness-tui` workspace paths.
      "With every assertion's meaning preserved" turned out to be the actual
      work. **Nine `!contains` assertions** would have gone vacuous — a
      negative pin on vocabulary that no longer exists passes forever, green
      for no reason — so each became a positive pin on the behaviour
      underneath: `displayed_model` is `None` until the agent reports one, the
      failed-auth row names the *method*, a new tab's runtime reads `waiting
      for ACP`, the codex chip shows exactly `gpt-5.6-codex`. Three further
      tests pin geometry rather than vocabulary and `crow-` is one char wider
      than `dsh-`: an untitled tab label is a `short_id` (8 chars, so
      `crow-test` renders as `crow-tes`) and picker meta is `{short:<8}`
      padded. All three were fixed against the production contract
      (`app/staging.rs:118,143`) rather than nudged until green.
      941 → 941; check rc 0 with exactly the 3 permanent warnings;
      `--dump-frame` byte-identical to the Phase-4 baseline.
      *Correction:* PLAN's verifies for 6.2 (`grep -rni martty tests` → 0) and
      6.3 ("returns only palette tests") were both wrong as written — 10
      `martty` and 9 `deepseek` hits survive, and every one is an absence pin
      (`MARTTY_HOME`, `/opt/martty`, `~/.martty/settings.json`,
      `.martty|.dsh|.dsh-tui/sessions`, `!HELP.contains("DEEPSEEK")`, the
      `["deepseek","martty","dsh","whale"]` logo-primitive guard) or the
      palette pack mandate rule 3 keeps. Itemised in PLAN. The `cordis`
      fixture vocabulary was already swept in 5.2, which is why Phase 6 never
      listed it; one hit survives, the `"--cordis"` rejection pin.
- [x] **Docs, assets, scripts, packaging**: `assets/promo/build.py:89`
      (`github.com/openma-ai/deepseek-harness-tui`), `docs/tui-palette.v0.schema.json`
      `$id` (`https://openma.ai/dsh-tui/…`) and the `$schema` refs in the 8
      fixtures, `scripts/collect-freeze-diag.sh` (pgreps `martty`),
      `crates/crow-client/README.md` + `AGENTS.md` + `docs/README.md` prose
      (the "what is still vestigial here" list describes the old state).
      *Done (PLAN 7.1–7.5).* `assets/promo/` deleted outright (`build.py`,
      `DESIGN.md`, `social-preview.png`) along with six old-brand screenshots
      (`banner-v020`, `agent-turn`, `skills-menu`, `harness-add`,
      `harness-switch`, `image-preview`) — all seven looked at with `vision`
      first, and all seven pure old brand: whale lockup, "DEEPSEEK HARNESS",
      `dsh --profile martty`, `deepseek-v4-*` chips, a live `/liang` menu, the
      openma URL. Nothing references them (`Cargo.toml`'s include list carries
      only the two pet PNGs, both still present), 4.63 MB gone;
      `assets/screenshots/liang.png` stays by rule 4. Schema `$id` →
      `https://crow-ai.dev/crow-client/…`, plus its `title` and `$comment`,
      which named the old product and a JS API that left with the npm layer.
      `collect-freeze-diag.sh` retargeted at `crow` in six sites. All three
      prose files rewritten to the post-sprint truth, every number read out of
      the tree rather than remembered: **20** live slash commands + 4 parked (a
      naive `name:` regex says 24 — it counts the commented-out ones), **6**
      `BUILTIN_PALETTE_IDS`, **10** files in `docs/fixtures/`, `harness_badge`
      still fed at `app/pump.rs:408` from `conversation.harness`
      (`slots.rs:274`), `CROW_RUST_CACHE_MAX_GIB` / `CROW_CARGO_TARGET_DIR`
      per `cargo-guard.sh:6-10`, rustc **1.98.1** — and the reason
      `let_chains` stay out is edition 2021, not the toolchain, so AGENTS.md
      now says that. `src/deepseek_logo.rs`, `src/cordis.rs` and
      `assets/martty-lockup.svg` are confirmed absent before being called
      absent. Reading AGENTS.md top to bottom also turned up a constraint
      that was false before the sprint — "there is no plugin command namespace
      to collide with … a builtin name is the only thing that exists" — when
      in fact the agent's `availableCommands` land in the same `/` menu as
      host skills (`events.rs:950` ← `acp.rs:1804-1819` / `acp/v2.rs:785`, and
      this repo's agent sends them at `src/crow_cli/agent/main.py:566`), which
      is why `app/slash.rs:43,74` dedupes against the builtin names. Now "the
      `/` namespace has three sources, and builtins win". The 7.5 sweep
      (`whale` added to the pattern) classified all
      **133** surviving lines and caught **five misses**: the `liang-effort` /
      "Liang reasoning effort" plugin-command and overlay-slider fixtures →
      `effort-slider` / "Reasoning effort" (`slash_matches` filters on
      `name.starts_with(prefix)`, so builtin `/effort` cannot collide and
      `matches.len() == 1` still pins what it did); `"whenTheme": "liang"` →
      `"no-such-theme"`, which states the pin instead of implying it;
      `/opt/liang/stage-00.png` → `/opt/crow/stage-00.png`; `pet.rs`'s "while
      DeepSeek runs" and its pointer to a README section that has never
      existed in this repo (`git log -S` → empty); and `transcript.rs:1553`'s
      `--dsw-specific-bubble`, the last `dsw` in the crate and one no brand
      grep can see. `grep -rni liang tests` 43 → 24, `grep -rni deepseek src`
      37 → 32, `dsw` → 0, `martty`/`cordis`/`dsh`/`whale`/`openma` all
      accounted for line by line in PLAN 7.5.
      *Correction:* PLAN 7.1 as written cannot be done — `build.py` composes
      its promo image from `assets/screenshots/banner.jpg` and `plugin-turn.jpg`,
      which were **never committed**, so the script could not run at any point
      in this repo's history. Retargeting its URL would leave a script that
      still cannot run next to a `DESIGN.md` whose whole subject is a whale
      lockup; for assets, "no shim" means delete. PLAN 7.2's "the `$schema`
      reference in each of the 8 fixtures" describes keys that do not exist:
      **0** of the 10 fixtures carry `$schema`, and none could —
      `PalettePack::from_json` rejects any key outside
      `id`/`label`/`dark`/`light`/`background` (`theme.rs:526-533`), so the
      annotation would be a parse error, not something the loader looks past.
- [ ] **`crates/crow-client/LICENSE:3`** still reads `Copyright (c) 2026 OpenMA
      contributors`. Deferred to the attribution pass the user said happens
      after the rebrand — recorded here so it is not lost, not touched now.

## Explicitly deferred (write the reason, do not do the work)

- **The LICENSE attribution line.** User, on the record: "we can properly
  attribute after we're finished with rebrand". Not this sprint.
- **`crate/target` — 71 GiB of stale build cache** at the repo root, from
  before the `crate/` → `crates/` move (`6ccafb8d`). Nothing builds into it.
  AGENTS.md forbids auto-cleaning target dirs, so this is a human decision:
  `rm -rf crate/target` reclaims 71 GiB. Flagged, not done.
- **The Cordis/plugin subsystem's existence.** This sprint renames it. Whether
  crow wants an agent-driven extension protocol at all — overlays, agent-pushed
  palettes, slot snapshots — is a product question that outlives a rebrand.
- **`src/locale.rs`'s bilingual-by-construction rule** (every builtin command
  needs a zh description, gated by a test). DSH-era inheritance, but it is not
  branding and the user did not ask; the gate stays.
- **The legacy JSON-RPC attach path** (`proto.rs` `RuntimeProcess`,
  `Controller::start`) that `--demo`/`--attach-*` still use. It loses its
  provider/model/maxTokens params because `RuntimeConfig` loses those fields,
  but the path itself stays: `--demo` is a documented flag with a pinned test
  surface.
  *The param loss itself was Phase 1 work and is done (PLAN 1.7):* both
  `initialize` calls now send `json!({ "cwd": cfg.workspace })` and nothing
  else; `SelectModel` builds a display label instead of mutating `cfg`;
  `Cmd::FetchEfforts` carries `Option`s and omits what it does not know.
  `--demo --dump-frame 100x34` still renders the canned transcript. What stays
  deferred is the path's *existence*, not its params.
