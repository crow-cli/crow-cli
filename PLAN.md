# PLAN — crow-client: the deepseek/martty/dsh rebrand

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Worktree `~/.agents/crow/src/worktrees/crow-cli-rebrand`, branch
`client-rebrand`, off main @ `4eea50f1`. Scope capture lives in `TODO.md`.

**Gate (floor for every item):** `cargo check --locked --tests -j 6`
**Gate (before declaring a phase done):** `cargo test --locked --bin crow -j 6` — 934 tests at baseline
**Gate (any paint change):** `cargo run -- --dump-frame 100x34`, eyeballed against the pre-change frame
Commit at every phase boundary with the `Session-Id:` trailer.

Trajectory is numeric: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8. Phase 1 is first because
the user named it first ("removing from default models with built in providers
is first step imo") and because it is the one that has already cost a model its
mind: a client that defaults to `deepseek-official` / `deepseek-v4-flash` and
warns `DEEPSEEK_API_KEY not set` reads as "this product needs a DeepSeek key".
It does not. It needs an agent.

The rule that decides every ambiguous case: **the client owns no model config,
keeps no back-compat shim, and wears no one else's brand — but a deepseek
*palette* is a palette, and liang's machinery stays compiled.**

---

## Phase 1 — the client stops owning provider, model and credentials

The aggravation source. After this phase, nothing in the binary can make a model
or a user believe crow needs a DeepSeek account.

[x] 1.1 **Delete `MODEL_PRESETS`** (`app/slash_catalog.rs:134-140`, five deepseek
    ids) and rewire its two consumers to the ACP truth:
    `app/pickers.rs:329 open_model_picker` and `app/slash.rs:219` (the `/model`
    argument completion). Both already prefer `last_models` — the catalog the
    agent advertised — and fall back to the presets only when it is empty. The
    fallback becomes: the effective current model (`current_model()`), and
    nothing else. An empty picker that says "the agent has not advertised a
    catalog" is honest; five deepseek ids are a lie.
    *Verify:* `cargo test --locked --bin crow -j 6` green after updating
    `app__mode_tests.rs` / `ui__tests.rs` expectations that seeded from the
    presets; `grep -rn MODEL_PRESETS src tests` → 0.
    *Done:* grep → 0 hits in `src` and `tests`. `open_model_picker` seeds only
    the current-model row and titles itself "waiting for the agent catalog"
    when nothing is known; `/model` completion falls back to the current model
    only. Two pure helpers replaced the preset table: `model_picker_title` and
    `catalog_provider` (unique-id-only — duplicate ids stay honestly ambiguous).
    Rewritten pins: `host_catalog_model_picker_distinguishes_duplicate_ids_by_provider`,
    `model_picker_highlights_the_streamed_model_not_the_reported_session_model`,
    `slash_model_menu_preselects_the_running_model`, `model_picker_marks_only_the_current_provider_model_pair`,
    `slash_model_menu_marks_the_running_model` (now feeds a real `CtlEvent::Catalog`).

[x] 1.2 **`RuntimeConfig` loses the model-config fields it should never have had.**
    `runtime.rs:80-95`: delete `provider`, `model`, `max_tokens`, `base_url`,
    `api_key`, and `cordis`. Every consumer of `cfg.provider` / `cfg.model`
    (`ui.rs:2170,2186-2187`, `app/info.rs:163-164,324`, `app/modes.rs:141-146,
    158-159,164-167,201-209`, `app/pickers.rs:356-366`, `app/pump.rs:773-800`,
    `app/slash.rs:593-594`, `controller.rs:340,346,759-760,838-839`) moves to
    the two facts the client actually has: the model the agent reported for the
    session (`session_model` / `current_model()`), and the provider that came
    with each catalog entry (`CatalogModel.provider`). Where a display needs a
    value and none has arrived, it shows nothing rather than a default.
    *Verify:* `cargo check --locked --tests -j 6` clean with no `unwrap_or`
    invented to silence it; the `/status` and `/session` overlays still render —
    `cargo run -- --dump-frame 100x34` eyeballed.
    *Done:* `RuntimeConfig` is `{bin, workspace, session_root, startup_session}`
    with a doc comment saying why it holds no route. All six fields deleted, no
    `unwrap_or` invented to paper over a hole. The two facts replaced them:
    `app.session_provider` (new, adopted from each catalog entry via
    `adopt_session_provider`) and `current_model()` =
    `selected_model → transcript.last_model → session_model → ""`, displayed
    through `model_identity()` = `provider · model` / `model` / `not reported`.
    `session_provider` is parked/restored with the slot and cleared at all three
    reset sites. 49 `RuntimeConfig` literals across 17 unit files stripped
    (located with `agp` `find_all('RuntimeConfig { $$$ }')`, applied with the
    `edit` subtool). `/status` and `/session` render; dump-frame is
    byte-identical to baseline.

[x] 1.3 **The flag surface.** `main.rs`: delete `--provider`, `--base-url`,
    `--api-key`, `--max-tokens` from `Args`, `parse_args_from` and `HELP`;
    keep `--model` (an explicit "run THIS model", still applied on bind through
    `app.startup_model`, `main.rs:440`) and keep `CROW_MODEL`; delete the
    `DSH_MODEL` alias (`main.rs:263`). Rewrite the `HELP` block: no
    `deepseek-official`, no `deepseek-v4-flash`, no `DEEPSEEK_*`, and
    `--theme <dark|light>` stops calling itself the "DeepSeek Web UI palette".
    `build_config` (`main.rs:218-271`) loses `runtime::legacy_dsh()` and the
    "Route defaults borrow the legacy dsh install" comment with it.
    *Verify:* `cargo run -- --help` printed and read top to bottom — not one
    brand name, not one credential flag; `tests/cli_help.rs` and
    `main__cli_args_tests.rs` updated to pin the *absence* of the removed flags
    the way `--demo-skin`'s absence is already pinned.
    *Done:* `--help` printed and read top to bottom. Header is
    `crow — terminal-native ACP client UI`; the only env vars named are
    `$CROW_HOME`, `$CROW_MODEL`, `$CROW_AGENT`; `--theme` now reads "colour
    palette"; `--demo` reads "scripted turns, no agent needed"; `--model` reads
    "ask the agent to run this model". No brand, no credential flag. New
    `startup_model(args)` = `--model` else `$CROW_MODEL` (`DSH_MODEL` gone),
    wired at `app.startup_model`. Absence pinned by
    `cli_help.rs::help_offers_no_provider_route_and_no_credentials` (integration)
    and `main__cli_args_tests.rs::{removed_runtime_aliases_are_rejected,
    help_offers_no_provider_route_and_no_credentials, model_flag_becomes_the_startup_request,
    no_model_flag_means_the_agent_chooses}`.

[x] 1.4 **`child_env()` stops being a credential courier.** `runtime.rs:99-131`:
    no `DEEPSEEK_BASE_URL`, no `DEEPSEEK_API_KEY`, no `legacy_dsh()` fallback,
    no `CROW_CORDIS_CONFIG`. `CROW_SESSION_ROOT` and `CROW_CWD` stay (crow-named,
    informational), and the `settings.json` harness `env` block still applies
    and still wins — that is the one legitimate way to give an agent environment,
    and `harness_env_applies_only_to_the_configured_agent` pins it.
    *Verify:* that test still green, plus a new assertion that no `DEEPSEEK_*`
    key can appear in `child_env()` output at all; `grep -rn DEEPSEEK src` → 0.
    *Done:* `child_env()` = `CROW_SESSION_ROOT`, `CROW_CWD`, then the
    settings.json harness `env`; `harness_env_applies_only_to_the_configured_agent`
    still green. New `child_env_carries_no_provider_and_no_credentials` asserts
    no key containing `API_KEY`, `BASE_URL`, `MODEL` or `PROVIDER` reaches an
    agent. **Correction to the grep target:** `grep -rn DEEPSEEK src` is 32, not
    0 — every hit is the `theme.rs` colour ramp, `logo.rs` and `markdown.rs`
    borrowing it, and `deepseek_logo.rs`. Mandate rule 3 keeps the palette, so
    those are Phase 4.2/4.3/4.1 work, not Phase 1. What Phase 1 owed is
    `grep -rn "DEEPSEEK_" src` → 0 *env vars*, which holds: no `DEEPSEEK_*`
    string is read from or written to the environment anywhere in `src`.

[x] 1.5 **Delete the legacy dsh credential store reader.** `runtime.rs:160-247`:
    `LegacyDsh`, `legacy_dsh()`, `unquote()`, `yaml_top_level_env()`,
    `yaml_agent_default_model()` — the hand-rolled yaml scraper for
    `~/.dsh/.credentials.yaml` and `~/.dsh/settings.yaml`. Then
    `has_credentials()` and `credential_source()`, whose only remaining inputs
    were `--api-key`, `$DEEPSEEK_API_KEY` and that scraper.
    *Verify:* `cargo check --locked --tests` clean; `grep -rn "legacy_dsh\|LegacyDsh\|has_credentials\|credential_source" src tests` → 0.
    *Done:* grep → 0 in `src` and `tests`. `unquote`, `yaml_top_level_env`,
    `yaml_agent_default_model` and `CROW_CORDIS_CONFIG` went with them;
    `runtime.rs` no longer parses yaml at all. `cargo check --locked --tests`
    rc 0, still exactly the 3 pre-existing warnings.

[x] 1.6 **The credential UI tells the truth.** `ui.rs:4241-4263`: the
    `app.attached` branch ("managed by Agent · source not reported") already
    covers every live run — `main.rs:435` sets `attached` for anything that is
    not `--demo` — so the `credential_source()` branch and the
    `⚠ DEEPSEEK_API_KEY not set — export it, or relaunch with --demo` line
    (EN + zh) delete, and demo mode uses the same honest line.
    `app/info.rs:113-119` likewise: the `api key present · {src}` /
    `DEEPSEEK_API_KEY not set` tail becomes the ACP auth state, which the
    branches above it already compute.
    *Verify:* `ui__tests.rs::welcome_info_uses_the_active_acp_runtime_and_reported_session_model`
    and the banner tests green; `cargo run -- --demo --dump-frame 100x34` shows
    no credential warning; `grep -rn "API_KEY" src` → 0.
    *Done:* the banner collapsed to one honest `else` — "managed by Agent ·
    source not reported"; the `⚠ DEEPSEEK_API_KEY not set` EN and zh lines are
    gone, and `info.rs`'s creds else-branch matches. `/session` and `/status`
    print `- model · {model_identity()}`; `app__right_slot_tests.rs:465` pins
    `- model · not reported`. `welcome_model` is now
    `displayed_model().unwrap_or("waiting for ACP")` and `displayed_model` lost
    its demo `cfg.model` tail. **Correction to the grep target:**
    `grep -rn "API_KEY" src` is 1, not 0 — the single hit is the 1.4 guard
    assertion at `runtime.rs:181`, which has to name the string to forbid it.
    *Note on the dump-frame check:* `--demo --dump-frame 100x34` shows no
    credential warning, but it never did — `main.rs:876` sets
    `show_banner = false` for the dump, so the banner is not in that path. The
    frame is byte-identical to the pre-phase frame (1822 bytes both), which is
    the no-regression evidence; the banner removal is pinned by the
    `ui__tests.rs` banner tests instead.

[x] 1.7 **The legacy JSON-RPC attach path loses the params it no longer has.**
    `controller.rs:757-764` and `836-843`: the `initialize` params keep `cwd`
    and drop `provider`, `model`, `maxTokens` (all three were `RuntimeConfig`
    fields, deleted in 1.2). `controller.rs:340,346` test-fixture configs
    likewise. The path itself stays — `--demo` and `--attach-*` are live flags.
    *Verify:* `cargo test --locked --bin crow -j 6` green; `cargo run -- --demo --dump-frame 100x34`
    renders the canned transcript.
    *Done:* both `initialize` calls send `json!({ "cwd": cfg.workspace })` and
    nothing else; `controller_loop(cfg)` lost its `mut` and `handle_prompt`
    takes `&RuntimeConfig` (2 call sites); `SelectModel` builds a display label
    from model/effort instead of mutating `cfg`; `Cmd::FetchEfforts` carries
    `provider: Option<String>, model: Option<String>` and omits what it does not
    know. `cargo test --locked --bin crow -j 6` → 938 passed, 0 failed (934
    baseline + 4 new). `--demo --dump-frame 100x34` renders the canned
    transcript. The demo `FetchCatalog` fixtures at `controller.rs:339-346`
    still carry deepseek ids — that is Phase 4.4/6.3 vocabulary, not a route.

**Phase 1 gate result:** `cargo check --locked --tests -j 6` rc 0, exactly the 3
pre-existing warnings; `cargo test --locked --bin crow -j 6` → **938 passed,
0 failed**; `cargo test --locked --test cli_help` → 3 passed; `--dump-frame
100x34` byte-identical to the pre-phase frame built from `41b7922d`.

**Commit:** `refactor(client)!: the client owns no provider, no model list and no credentials`

---

## Phase 2 — no martty shims, no dsh shims, no legacy homes

Breaking pre-rebrand installs is the point, per the mandate.

[x] 2.1 **`crow_home_from`** (`runtime.rs:14-38`): `CROW_HOME` → `~/.agents/crow`,
    full stop. `MARTTY_HOME` and `DSH_HOME` deleted; the signature drops both
    parameters. `rewrite the doc comment` — it currently advertises the shim.
    *Verify:* `main__cli_args_tests.rs` — the test named
    `a pre-rebrand MARTTY_HOME keeps its data` becomes
    `a pre-rebrand MARTTY_HOME is not read`: same inputs, opposite assertion.
    *Done:* `crow_home_from(crow_home: Option<&str>, user_home: &str)` — the
    signature dropped both parameters, so the shim cannot be called even by
    accident. Doc comment rewritten to state the precedence and why there is no
    fallback. *Correction:* `a pre-rebrand MARTTY_HOME keeps its data` was an
    assert message inside `crow_home_precedence_owns_the_default_session_root`,
    not a test name; it is now a real test,
    `a_pre_rebrand_martty_home_is_not_read`, which exports `MARTTY_HOME` and
    `DSH_HOME` and asserts `crow_home()` is explained entirely by `CROW_HOME` +
    `HOME`. Setting them is race-free precisely because nothing reads them.
    `crow_home_precedence_owns_the_default_session_root` also gained an
    empty-`CROW_HOME` case.

[x] 2.2 **`legacy_settings_paths_from` / `legacy_settings_paths`**
    (`runtime.rs:56-79`) deleted with every caller — `~/.martty/settings.json`
    and `~/.dsh-tui/sessions/dsh-tui-settings.json` are not read anymore.
    *Verify:* `legacy_settings_come_from_the_martty_home_then_dsh_tui` rewritten
    to pin that only `settings_path(session_root)` is consulted;
    `grep -rn "legacy_settings" src tests` → 0 outside that rewritten test.
    *Done:* both functions deleted, plus both callers — the `app.rs` import and
    `app/prefs.rs load_settings`, which lost its whole migrate-and-copy loop and
    is now one read of `settings_path(session_root)` with `unwrap_or_default()`.
    grep → 0 in `src`; the two surviving mentions in `tests` are the rewritten
    test's own comment. Rewritten as `settings_come_from_the_configured_root_only`:
    seeds valid settings into *both* legacy filenames, asserts `load_settings`
    returns the default, then asserts the configured file is the one source.
    A fourth pin fell out of running the suite:
    `lang_switch_repaints_immediately_and_persists_for_the_workspace` seeded
    `dsh-tui-settings.json` and asserted it migrated to `settings.json`. It now
    seeds `settings.json` directly and asserts the legacy file is neither read
    nor overwritten — the migration it used to prove no longer exists.

[x] 2.3 **`sessions.rs:42-62`**: `session_roots_from` returns the configured root
    only. `~/.crow-term/sessions`, `~/.martty/sessions`, `~/.dsh/sessions`,
    `~/.dsh-tui/sessions` deleted, and the module doc (lines 9-13) stops
    listing them.
    *Verify:* `sessions_from_the_martty_and_dsh_homes_remain_discoverable`
    becomes `sessions_are_discovered_in_the_configured_root_only` — writes a
    session under each legacy home, asserts `/resume` sees none of them and
    sees the configured root's.
    *Done:* `session_roots_from(cfg_root, home)` and its `session_roots` wrapper
    collapsed into one `session_roots(cfg_root)`; `$HOME` is no longer read, so
    the four legacy roots are unreachable by construction. Module doc rewritten.
    The test does exactly what the verify line asked: a real session log under
    each of the four abandoned homes plus one under the configured root, then
    `list_sessions` must return only `crow-here`. Also pins that a configured
    root which does not exist yields no roots.

[x] 2.4 **`app/keys_router.rs:237`**: the `DSH_TUI_KEYDEBUG` legacy alias goes;
    `CROW_KEYDEBUG=1` is the only spelling.
    *Verify:* `grep -rn "DSH_" src` → 0; the key-debug test still green.
    *Done:* `grep -rn "DSH_\|MARTTY_" src` → 0. *Correction:* there was no
    alias in the code — `app.rs:585` already read only `CROW_KEYDEBUG`. What
    survived was a stale comment at `keys_router.rs:237` advertising an alias
    that did not exist; the comment now names `CROW_KEYDEBUG` alone.

**Phase 2 gate result:** `cargo check --locked --tests -j 6` rc 0, exactly the 3
pre-existing warnings; `cargo test --locked --bin crow -j 6` → **939 passed, 0
failed**; `--dump-frame 100x34` byte-identical to the Phase-1 frame (`main.rs`
untouched, so `--help` is unchanged too).

**Commit:** `refactor(client)!: delete the martty and dsh compatibility shims`

---

## Phase 3 — liang unregistered, machinery kept

[x] 3.1 **Comment out the `/liang` entry in `SLASH_COMMANDS`**
    (`app/slash_catalog.rs:72-76`) with a note that says where the machinery
    lives (`src/pet.rs`, `assets/pet/liang-*.png`, the `app.pet_*` fields, the
    `ui.rs` pet rect, the `slash.rs:457-467` handler) and why it is parked:
    a crow pet replaces it, and the sprite/kitty plumbing is the expensive part.
    Keep the entry commented rather than deleted so the shape is right there.
    *Verify:* `locale__tests.rs::every_builtin_command_has_an_explicit_zh_desc`
    and the name-sort assertion both green (they iterate the catalog, so a
    parked entry cannot fail them); `app__mode_tests.rs:298
    liang_toggle_is_transient_and_keeps_the_empty_welcome_centered` and
    `pet__tests.rs` still green because `run_slash("liang", …)` still resolves —
    that is the proof the machinery survived; `cargo run -- --dump-frame 100x34`
    shows no pet (he was already off by default).
    *Done:* the entry is commented in place, with a note naming every piece of
    the machinery that stays compiled — `src/pet.rs`,
    `assets/pet/liang-{idle,working}.png` (both present), `App::pet_visible` /
    `pet_pixels` / `pet_want`, `ui.rs pet_rect`, the `slash.rs` handler and its
    `on|off` completion, and the zh `command_desc` arm. *Correction:* the
    handler is at `slash.rs:454-466`, not `457-467`; the note names the file
    rather than a line range so it cannot go stale. zh-desc gate and name-sort
    gate green (the catalog is still sorted — `lang`, then `model`);
    `liang_toggle_is_transient_and_keeps_the_empty_welcome_centered` and
    `pet__tests.rs` green; `--dump-frame 100x34` byte-identical to the Phase-2
    frame and contains no pet.

[x] 3.2 **The `/liang` menu absence gets pinned**, the way `login`/`logout` absence
    already is (`app__mode_tests.rs:4265,4390`): one assertion that
    `SLASH_COMMANDS` has no `liang`, so a future agent does not silently
    re-register it without deciding to.
    *Verify:* that new test green; the zh `command_desc` arm for `liang`
    (`locale.rs:91`) stays — it is dead but harmless, and it is the string a
    re-registered pet would need.
    *Done:* `liang_is_parked_out_of_the_menu_but_the_machinery_still_runs`,
    next to the `login`/`logout` pins. It asserts three things, because the
    mandate is "unregister, don't amputate": no `liang` in `SLASH_COMMANDS`, no
    `liang` offered when the input reads `/liang`, and `run_slash("liang",
    "on"/"off")` still flips `app.pet_visible` both ways. The zh
    `command_desc` arm at `locale.rs:91` is untouched. 939 → 940 tests.

**Phase 3 gate result:** `cargo check --locked --tests -j 6` rc 0, exactly the 3
pre-existing warnings; `cargo test --locked --bin crow -j 6` → **940 passed, 0
failed**; `--dump-frame 100x34` byte-identical to the Phase-2 frame.

**Commit:** `feat(client): park /liang — the pet machinery stays, the command does not`

---

## Phase 4 — brand art out, the palette stays a palette

[x] 4.1 **The deepseek logo is branding, not a theme.** Delete the
    `ui_preset == "deepseek"` banner branch (`ui.rs:4114-4125`, including the
    "Into the Unknown" / 探索未知 slogan), `src/deepseek_logo.rs` (10K) and its
    `mod` line (`main.rs:13`), `assets/martty-lockup.svg` and
    `scripts/render-martty-lockup.swift`. `logo.rs`'s crow-cli lockup becomes
    the only banner. `slots.rs:181,352-356` stops accepting `"deepseek"` and
    `"martty"` as logo names, keeping `crow` / `crow-term`.
    *Verify:* `cargo test --locked --bin crow -j 6` green;
    `cargo run -- --dump-frame 100x34` diffed against the pre-phase frame — the
    banner must be the crow lockup in both, since `default` was already the
    preset; `grep -rn "deepseek_logo\|martty" src` → 0.
    *Done:* the `ui_preset == "deepseek"` branch is gone (whale + "Into the
    Unknown" / 探索未知), so `banner_lines` has two arms left: a `welcome.hero`
    slot snapshot, else the crow lockup. `slots.rs` validates
    `crow | crow-term` only and lost both the `name == "deepseek"` render arm
    and `"martty"` from the crow arm. `mod deepseek_logo;` is out of `main.rs`.
    *Corrections:* the branch was at `ui.rs:4112-4123`, not `4114-4125`. The
    PLAN named two asset files; **nine** went, because the rest were unreferenced
    DeepSeek/martty brand art with no code or doc link left —
    `src/deepseek_logo.rs`, `assets/martty-lockup.{svg,png}`,
    `assets/deepseek_favicon.{ico,png}`, `assets/tui-{whale,lockup,wordmark}.svg`,
    `scripts/render-martty-lockup.swift`. `assets/` is now
    `crow-cli-ascii.txt, pet, promo, screenshots`; `assets/screenshots/liang.png`
    stays because it documents parked machinery. Four tests in
    `tests/unit/ui__tests.rs` pinned the old art and were rewritten to pin the
    new one, not deleted: the two `welcome.hero` slot tests now drive
    `name:"crow"` with `crow-hero:*` ids and assert the crow lockup's
    `└────────────┘` foot; `deepseek_hero_preserves_the_original_whale_geometry`
    became `a_brand_logo_name_is_not_a_tui_primitive` (accepts `crow` /
    `crow-term`, rejects `deepseek` / `martty` / `dsh` / `whale` with
    `unknown tui logo primitive: {name}`); and
    `composed_deepseek_preset_keeps_balanced_outer_padding` became
    `composed_hero_keeps_balanced_outer_padding`. `grep -rn
    "deepseek_logo\|martty" src` → **0**; `--dump-frame 100x34` byte-identical
    to the Phase-3 frame (the banner never renders in it — `main.rs` sets
    `show_banner = false`, and `default` was already the preset).

[x] 4.2 **The default palette stops wearing DeepSeek blue.** `theme.rs`: the
    `DEEPSEEK_50…900` ramp stays (it is a palette, and the mandate says a
    deepseek theme is fine) but becomes a *named* pack rather than the source
    of the builtin `default`'s `brand` / `brand_soft` (`theme.rs:174-175` dark,
    `195-196` light). `default` takes crow's purple — the house brand already
    in `docs/styles/purple.css` and `docs/img/crow-icon-purple.svg`. The module
    doc (lines 1-10) stops claiming to be a 1:1 map of DeepSeek's web tokens
    and says what it is now: crow's token ramp, plus the deepseek ramp kept as
    a palette. `logo.rs:12,58-59` (which borrows `DEEPSEEK_50`/`DEEPSEEK_200`
    for the lockup gradient) moves to the crow tokens.
    *Verify:* `theme__tests.rs` and `app__palette_tests.rs` green; the 8
    `docs/fixtures/*.v0.json` palettes still load; `--dump-frame` eyeballed for
    the purple brand and diffed against the 4.1 frame — this is the one item in
    the sprint that changes what the product looks like, so it gets looked at.
    *Done:* `CROW_50…CROW_900` is the house ramp and `default` wears it —
    `DEFAULT_DARK.brand/brand_soft = CROW_400/CROW_300`, `DEFAULT_LIGHT =
    CROW_600/CROW_500`. Every value is read off crow's own brand, not invented:
    `CROW_200 #c4b5fd` and `CROW_300 #a78bfa` are `purple.css`'s link-hover and
    link, `CROW_400 #8b5cf6` its admonition border, `CROW_800 #2600ab` its
    button/border and the crow icon's own fill, `CROW_900 #1c005f` its page
    background. The blue ramp keeps its constants and gains a section of its
    own: `DEEPSEEK_DARK`/`DEEPSEEK_LIGHT` are `..DEFAULT_DARK`/`..DEFAULT_LIGHT`
    with only the two brand slots overridden, so selecting the pack changes the
    accent and nothing else; `PalettePack::deepseek()` (id `deepseek`, label
    `DeepSeek Blue`, `preferred_mode: None`, source `static`) is appended last to
    `builtin_packs()` and to `BUILTIN_PALETTE_IDS` — last because it is a
    retained palette, not a family. `logo.rs` borrows `CROW_50`/`CROW_200` for
    the lockup gradient and its `ocean_top`/`ocean_bottom` locals are now
    `brand_top`/`brand_bottom`. The module doc says what the file is now.
    *Correction:* the PLAN's verify assumed `theme__tests.rs` and
    `app__palette_tests.rs` were written generically against
    `BUILTIN_PALETTE_IDS`. They are not — **11 tests failed**, all pinning the
    old blue as "what the default pack looks like": `brand_is_deepseek_blue` and
    `default_toggled_still_uses_deepseek_blue` in `theme__tests.rs`, plus nine in
    `app__palette_tests.rs` that import `DEEPSEEK_450` as shorthand for the
    default dark brand. All were rewritten to pin crow purple
    (`brand_is_crow_purple`, `default_toggled_still_uses_crow_purple`, and the
    palette tests' import becoming `CROW_400`), and one test was **added**:
    `the_deepseek_palette_survives_as_a_pack_and_nothing_more`, which is the
    executable form of mandate rule 3 — the blue is reachable through the
    `deepseek` pack and through nothing else, and that pack differs from
    `default` in `brand` only. 940 → **941** tests.
    `builtin_packs_are_the_catalog_the_menu_calls_builtin` passed untouched, as
    predicted. The 8 `docs/fixtures/*.v0.json` gallery palettes still parse
    (`gallery_fixtures_parse_both_modes`) — they carry their own hex, so the
    ramp rename cannot reach them.
    *Eyeballed:* `ui::dump_frame` emits `symbol()` only, so the plain frame is
    colour-blind and stayed byte-identical — it cannot show this change. The
    paint was captured instead by temporarily teaching `dump_frame` to emit
    `38;2;r;g;b` SGR (reverted afterwards; `grep 'x1b\[38;2' src` → 0), and by
    running under a clean `CROW_HOME` — the developer's own
    `~/.agents/crow/settings.json` persists `"theme":
    "catppuccin-macchiato"`, so the default pack never renders unless the
    settings root is empty. Two frames, both with zero DeepSeek-ramp cells:
    the banner frame's lockup `cr` half runs `#f4f1ff` (CROW_50) → `#8b5cf6`
    (CROW_400) top to bottom against the unchanged mint `-cli` half
    (`#afeac5` → `#4ed17e`), and the conversation frame's brand accents are
    `#a78bfa` (CROW_300) on the `▎` blockquote bars and `#8b5cf6` (CROW_400) on
    the composer `❯`. Structure identical throughout: same 35 rows.

[x] 4.3 **`DeepSeekStyleSheet`** (`markdown.rs`, 5 sites) renamed to say what it
    does. `markdown.rs`'s deepseek-harness references in comments likewise.
    *Verify:* `grep -rni deepseek src/markdown.rs` → 0; markdown render tests green.
    *Done:* `ThemeStyleSheet` — it maps markdown onto whatever theme is active,
    which is the truth of it now that the default is purple and five other
    builtin packs exist. All 5 sites (the two `Options::new` call sites, the struct, the
    impl, and the `CODE_FENCE_SENTINEL` doc that points at
    `code_block_fence`), located with `ast_grep_py` and written with `edit`.
    The module doc's two palette claims went with it — line 4 "maps its output
    onto the DeepSeek palette" → "onto the active theme", line 24 "Colors stay
    inside the DeepSeek palette: … brand-blue accents" → "inside the active
    theme: … brand accents" — and `heading_style`'s six-step ramp now reads
    `CROW_200…CROW_600` dark / `CROW_400…CROW_900` light under a "house purple
    ramp" comment. `markdown__tests.rs:433` pinned the dark H1 colour as
    `DEEPSEEK_200` and now pins `CROW_200`; that was the only test the rename
    broke. `grep -rni deepseek src/markdown.rs` → **0**.
    *Decision, recorded:* `theme.rs:780`'s field doc read
    `--dsw-alias-brand-primary-new-color… — the DeepSeek blue accent`, and the
    colour claim became false the moment `default` went purple, so the claim
    went (`— the house accent`). The `--dsw-alias-*` token names themselves
    stay: they are the CSS custom properties these tokens were mapped from, i.e.
    provenance, and all 16 of them belong to the Phase 7.5 provenance sweep
    rather than to this item.

[x] 4.4 **`demo.rs`**: the two whale passages (lines ~277, ~419) and the three
    `"provider": "deepseek-official", "model": "deepseek-v4-flash"` payloads
    (~107, ~265, ~295) become crow-shaped; the `deepseek-harness SDK runtime`
    module doc (line 4) too. The demo is a rendering fixture — its content is
    free to change, its *shape* (streaming text, reasoning, tool calls, plans,
    usage, images) is not.
    *Verify:* `cargo run -- --demo --dump-frame 100x34` renders the same cell
    kinds as before (diff the frame against the pre-change one: same structure,
    new words); `grep -rni "deepseek\|whale" src/demo.rs` → 0.
    *Done:* the module doc now says the shape is the **crow-cli agent
    runtime**'s. All three `assistant/message` payloads advertise
    `"provider": "demo", "model": "demo-flash"` — a demo fixture should not
    claim a real provider it is not, and `demo` matches the `runtime demo` line
    the banner already prints. Both whale passages became crow passages ("the
    crow cocked its head, cawed once in approval, and flew off" / "…and flew
    back to the wire"), and the 🐋 went with them. `grep -rni
    "deepseek\|whale" src/demo.rs` → **0**.
    *Also done, same category, not in the PLAN:* `controller.rs`'s demo-only
    `Cmd::FetchCatalog` fixture advertised `deepseek-official` /
    `deepseek-v4-flash` / `deepseek-v4-pro` and is now `demo` / `demo-flash` /
    `demo-pro` (`Demo Flash`, `Demo Pro`, vision flags unchanged); and
    `describe_server`'s `.unwrap_or("deepseek-harness")` — the name shown when
    an ACP server does not identify itself — is now `.unwrap_or("agent")`,
    because a client that owns no model config has no business asserting which
    harness it is talking to. No test pinned either.
    *Not touched, deliberately:* `whale` survives elsewhere in `src/` as the
    **liang pet's** XS half-block fallback (`pet.rs:12,470`, `ui.rs:407,1668`,
    `theme.rs:865 whale_gradient`) — that is parked machinery under mandate
    rule 4, not brand art. `app.rs:248`'s `show_banner` doc did get fixed: it
    still advertised a "whale + wordmark" banner that 4.1 deleted.
    *Frame:* `--dump-frame 100x34` diffs against the Phase-3 frame in exactly
    two places and keeps all 35 rows — the concluding sentence re-wraps onto the
    same two lines with the new words, and the composer's model chip reads
    `demo-flash · demo` instead of `deepseek-v4-flash · demo`. `--demo` and
    plain remain byte-identical to each other.

**Phase 4 gate result:** `cargo check --locked --tests -j 6` rc 0, exactly the 3
pre-existing warnings; `cargo test --locked --bin crow -j 6` → **941 passed, 0
failed** (940 → 941: one test added, four rewritten in 4.1, twelve repointed in
4.2/4.3, none deleted); `--dump-frame 100x34` byte-identical to the Phase-3
frame through 4.1–4.3, then a two-line textual diff in 4.4 with the structure
intact. `grep -rni deepseek src` → **37**, and every one is accounted for:
33 in `theme.rs` (the retained ramp, its two token maps and its pack — mandate
rule 3), 2 in `pet.rs:1,5` (the parked liang homage, rule 4), and the four
provenance module docs `events.rs:1`, `transcript.rs:3`, `file_ref.rs:3`,
`proto.rs:1` (Phase 7.5). `grep -rn martty src` → **0**. The 3 remaining
`\bdsh\b` hits (`acp_auth.rs:114`, `cordis.rs:33-34`) are Phase 5's.

**Commit:** `refactor(client)!: crow brand art and crow purple default; the deepseek ramp stays as a palette`

---

## Phase 5 — the last `_dsh` on the wire: the extension family

Machinery kept, namespace crow's. Nothing implements this protocol today, so
the rename cannot break a peer.

[x] 5.1 **`cordis.rs` → the crow extension namespace.** The 22 wire constants
    `_dsh/cordis/tui/*` → `_crow/tui/*`, `_dsh/plugins/list` →
    `_crow/plugins/list`, `_dsh/cordis/plugins/{start,stop}` →
    `_crow/plugins/{start,stop}`; the capability key the client reads in
    `advertised_by_agent` (`agentCapabilities._meta.dsh.cordis.protocol`) and
    advertises itself in `acp_auth.rs:114-115` (`"dsh"` + `{cordis:{protocol}}`)
    → `_meta.crow.tui.protocol`. Rename the module file itself to something
    that says what it holds (`ext.rs`), and update `main.rs:12`'s `mod` line.
    *Verify:* `grep -rn "_dsh\|cordis::" src` → 0; the extension-path tests in
    `acp__tests.rs` / `events__tests.rs` green with the new method strings.
    *Done:* `git mv src/cordis.rs src/ext.rs` — `ext` because what the module
    holds is the client's extension contract, and the `mod` line moved to its
    alphabetical slot after `mod events;`. All 22 method strings are crow's: 18
    under `_crow/tui/*` plus the four plugin methods. `PROTOCOL` is documented
    as the version advertised in `agentCapabilities._meta.crow.tui.protocol`
    and checked against that same key, `advertised_by_agent` reads that path,
    and `acp_auth.rs:113-116` advertises
    `meta.insert("crow", {"tui": {"protocol": …}})`. `crate::cordis::` →
    `crate::ext::` at 163 sites (57 in `src`, 106 in `tests`).
    *Correction — the collision this item did not see:* mapping
    `_dsh/cordis/plugins/{list,start,stop}` → `_crow/plugins/{list,start,stop}`
    puts `_dsh/cordis/plugins/list` and `_dsh/plugins/list` on the **same** new
    name, and they are two live methods with different shapes and different
    callers: `StaticPluginItem` is the read-only Loader inventory fetched by
    `Cmd::FetchStaticPlugins`, `DynamicPluginItem` is the agent's own registry,
    fetched by `Cmd::FetchDynamicPlugins` and driven by start/stop/approvals.
    That static/dynamic axis already exists in the crate (`app.static_plugins`,
    `fetch_dynamic_plugins`), so the rename follows it instead of flattening
    it: the dynamic trio went under the family prefix as
    `_crow/tui/plugins/{list,start,stop}`, `_crow/plugins/list` stays the one
    method outside the family, and `PLUGINS_LIST` → `DYNAMIC_PLUGINS_LIST` says
    which is which. The old inside/outside-the-family split survives exactly —
    only the vendor segment is gone — and `ext.rs`'s module doc records the
    two-level rule so the next reader does not have to rediscover it.
    *Also, because a rename that leaves the tests on the old dialect is half a
    rename:* `acp__tests.rs:251` asserted the client's own advertised
    `_meta.dsh.cordis.protocol` and now asserts `_meta.crow.tui.protocol`; the
    mock agent at `acp__tests.rs:278-282` advertised the old key too, which
    after the rename meant that test's agent had **silently stopped
    advertising the family** — it still passed, because the compositor paths do
    not require the capability (exactly what the two
    `does_not_require_agent_extension_capability` tests pin), i.e. it was green
    for the wrong reason. Both fixtures now speak `crow`/`tui`. The last three
    hardcoded `_dsh/…` strings anywhere in the crate
    (`app__mode_tests.rs`'s two `agents/select`, `app__palette_tests.rs`'s
    `theme/remove`) became `crate::ext::AGENTS_SELECT` / `THEME_REMOVE`.
    *Verify result:* `grep -rni "cordis\|_dsh" src` → **0**;
    `grep -rn "_dsh" tests` → **0**; the extension-path tests in
    `acp__tests.rs` / `events__tests.rs` green on the new method strings.

[x] 5.2 **The Rust identifiers.** `Cmd::FetchCordisPlugins`,
    `Cmd::SetCordisPluginEnabled`, `Cmd::RespondCordisApproval`,
    `CtlEvent::CordisPlugins`, `PickerKind::CordisPlugin|CordisApproval`,
    `CordisApprovalsSnapshot`, `CordisPluginItem`, `PendingCordisApproval`,
    `app.cordis_plugins`, `app.pending_cordis_approvals`,
    `ensure_agent_cordis`, `surface.cordis`, `draw_cordis_approval`,
    `open_cordis_plugin_picker`, `open_cordis_approval_picker`,
    `cancel_plugin_overlays`'s cordis references, and the `RuntimeConfig.cordis`
    display string already deleted in 1.2. Use `sg` for the identifier renames
    (AST, not substring — `cordis_plugins` must not touch a `plugins` local).
    *Verify:* `cargo check --locked --tests -j 6` clean; `grep -rni cordis src` → 0;
    full `cargo test --locked --bin crow -j 6` green.
    *Done:* 82 replacements, longest-first, located with `ast_grep_py` and
    written with `edit`. Every new name lands on the crate's **existing**
    static/dynamic axis rather than a third vocabulary:
    `CordisPluginItem` → `DynamicPluginItem`,
    `PendingCordisApproval` → `PendingPluginApproval`,
    `CtlEvent::CordisPlugins` → `DynamicPlugins`,
    `Cmd::FetchCordisPlugins` → `FetchDynamicPlugins`,
    `SetCordisPluginEnabled` → `SetDynamicPluginEnabled`,
    `RespondCordisApproval` → `RespondPluginApproval`,
    `PickerKind::CordisPlugin` → `DynamicPlugin`,
    `CordisApproval` → `PluginApproval`,
    `CordisApprovalsSnapshot` → `PluginApprovalsSnapshot`,
    `app.cordis_plugins` → `dynamic_plugins`,
    `pending_cordis_approvals` → `pending_plugin_approvals`,
    `ensure_agent_cordis` → `ensure_agent_ext`, `surface.cordis` →
    `surface.ext`, `draw_cordis_approval` → `draw_plugin_approval`,
    `open_cordis_plugin_picker` → `open_dynamic_plugin_picker`,
    `open_cordis_approval_picker` → `open_plugin_approval_picker`.
    Prose followed the identifiers: `acp.rs`, `acp/control.rs:116`, six `bus.rs`
    docs, `controller.rs:644`, `events.rs:148`, four `theme.rs` sites, both
    picker titles in `harness.rs:205-206` (" dynamic plugins · enter manage ·
    esc close " / " 动态插件 · enter 管理 · esc 关闭 "), the `slash.rs:515-516`
    tips, `controller.rs:984`'s "The stock agent modes", and `acp.rs:1700`'s
    refusal message, which now reads "agent does not advertise _crow/tui".
    *Also done, and not in the PLAN — the tests' own vocabulary.* Five test
    names still said cordis (`cordis_plugin_inventory_opens_…`,
    `pending_cordis_approval_renders_…`,
    `cordis_requests_stay_local_when_the_agent_did_not_advertise_cordis`,
    `client_compositor_catalog_does_not_require_agent_cordis_capability`,
    `client_compositor_command_does_not_require_agent_cordis_capability`), two
    assert messages did, and six canned payloads used `"cordis"` /
    `"name": "Cordis"` as the agent-advertised preset id. The names moved to
    the new axis (`dynamic_plugin_inventory_…`, `pending_plugin_approval_…`,
    `extension_requests_stay_local_when_the_agent_did_not_advertise_the_family`,
    `…_does_not_require_agent_extension_capability`); the fixture id became a
    neutral `studio` / `Studio`, which preserves every assertion's meaning —
    an opaque advertised id is precisely what those tests exercise. This is
    Phase 6's *category* but not Phase 6's *list* (6.1–6.3 name `dsh-*`,
    `martty-*`, `deepseek-*`), and leaving it would have made Phase 5 a
    half-rename of the one concept Phase 5 exists to rename.
    *Verify result:* check rc 0 with exactly the 3 permanent warnings — the
    unused-`ctl` one moved from `ui__tests.rs:3582` to `:3602` because 5.3's
    rewrite added 20 lines above it; same warning, same binding.
    `grep -rni cordis src` → **0**, and over `src` **and** `tests` → exactly
    one hit: `main__cli_args_tests.rs:128`'s `"--cordis"`, the Phase-1 pin that
    the removed flag stays *rejected*. Deliberate, in the same category as
    `MARTTY_HOME` in `a_pre_rebrand_martty_home_is_not_read`. Full suite green
    at **941**.

[x] 5.3 **The three vestigial plugin commands.** `/plugins`, `/cordis-plugins`,
    `/ui` (`slash_catalog.rs:37-41,97-101,122-126`, handlers in `slash.rs:513+`,
    zh descs in `locale.rs:84,86-87`) aim at a plugin host that does not exist.
    Decision, recorded rather than guessed: **park them the way 3.1 parks
    `/liang`** — commented out of `SLASH_COMMANDS` with a note that the
    extension machinery in `ext.rs` / `acp/control.rs` / `app/pickers.rs` is
    intact and re-registering them is a one-line uncomment, because shipping
    three menu entries that always answer "agent does not advertise _crow/tui"
    is worse than not shipping them. `AGENT_MODES`'s `cordis` "Creator mode"
    seed and its "Shipped creator id is `cordis`" comment go with them.
    *Verify:* the zh-desc gate and name-sort gate green; absence pinned by one
    assertion per command next to the `login`/`logout` ones;
    `cargo run -- --dump-frame 100x34` unchanged.
    *Done:* all three commented out at their alphabetical positions, each with
    a `/liang`-style note naming every surviving piece — the three `Cmd`s,
    `ensure_agent_ext` and `fetch_{static,dynamic}_plugins` in `acp.rs`, the
    handlers in `acp/control.rs`, `CtlEvent::{StaticPlugins,DynamicPlugins}`,
    `StaticPluginItem` / `DynamicPluginItem` / `PendingPluginApproval`,
    `App::{static_plugins,dynamic_plugins,pending_plugin_approvals,ui_plugins}`,
    `PickerKind::{DynamicPlugin,PluginApproval,UiPlugin}`, the three
    `open_*_picker`s, `draw_plugin_approval`, the alt-key answer in
    `keys_router.rs`, the grouped render in `ui.rs`, the `_crow/tui/ui/update`
    + `ui/selected` projection in `app/pump.rs`, the `"ui"` argument-completion
    arm, the `slash.rs` handlers and the three zh `command_desc` arms (which
    stay, exactly as `liang`'s does). Handlers untouched, so `run_slash` still
    resolves all three.
    `/cordis-plugins` was renamed **`/dynamic-plugins`** on the way out
    (`slash_catalog.rs`, the `slash.rs:510` arm, `locale.rs:87`'s zh desc →
    "查看或管理动态插件", `app.rs:342`, `session_slot.rs:85`), so what is parked is
    a command crow would actually ship and re-registering is one uncomment, not
    a rename plus an uncomment. `AGENT_MODES`'s fourth seed went with them; the
    doc above the constant explains why **without using the removed brand
    name** — the gate is `grep -rni cordis src` → 0, so even a historical note
    has to avoid the word. Three modes now.
    *Correction — the mode-count pin lived in four tests, not zero:*
    `controller__tests.rs::stock_presets_cover_the_four_web_ui_modes` (renamed
    `stock_presets_cover_the_shipped_agent_modes`: neither "four" nor "web ui"
    is true any more),
    `app__mode_tests.rs::slash_agent_opens_the_agent_preset_picker`,
    `ui__tests.rs::mode_picker_renders_modes_and_marks_the_current_one` (drops
    "Creator mode" from the asserted list) and
    `locale__tests.rs::zh_command_desc_covers_every_builtin_and_plugin_command`
    (the zh key is `dynamic-plugins` now). All four rewritten to pin three
    modes; none deleted.
    *Correction — the absence pin landed next to the `/liang` park pin, not
    next to `login`/`logout`:* same region of `app__mode_tests.rs`, and liang is
    the closer precedent because it is also a park-not-delete. The failing
    `slash_menu_offers_the_dynamic_plugin_manager` (which asserted `/plug`
    matches exactly one entry, `plugins`) was rewritten — relocated, not
    dropped — into
    `the_plugin_commands_are_parked_out_of_the_menu_but_the_machinery_still_runs`:
    one registry-absence assertion per command, a menu-absence pass over
    `/plug`, `/dynamic` and `/ui`, and one machinery assertion,
    `run_slash("ui", "")` still opening `PickerKind::UiPlugin`. The two
    inventory fetches keep their own tests
    (`plugins_slash_fetches_the_static_loader_inventory`,
    `dynamic_plugins_slash_fetches_the_dynamic_inventory`), so the pin points at
    them instead of duplicating them. Test count unchanged: **941 → 941**.
    *Also rewritten, same category:*
    `ui__tests.rs::cordis_protocol_id_is_rendered_as_creator` still passed, but
    its fixture was a removed concept. It is now
    `an_advertised_preset_renders_by_its_catalog_name_not_its_raw_id`, and it
    pins *more* than the test it replaces: the old fixture's id was in
    `AGENT_MODES`, so it was implicitly pinning "the catalog name outranks the
    stock demo label" as well as "never the raw id". Two presets now pin both
    halves explicitly — `nightshift`, an id crow never shipped, and `standard`,
    one it does have a stock label for.
    *Verify result:* the zh-desc gate and the name-sort gate green (the catalog
    is still name-sorted with three entries commented out in place, and every
    registered builtin still has a zh desc); `--dump-frame 100x34`
    byte-identical to the Phase-4 frame — 1815 bytes, 35 rows — under both the
    developer's `CROW_HOME` and a clean one, and `--demo` byte-identical to
    plain.

**Phase 5 gate result:** `cargo check --locked --tests -j 6` rc 0 with exactly
the 3 permanent warnings; `cargo test --locked --bin crow -j 6` → **941 passed,
0 failed** (941 → 941: one test rewritten and relocated, one rewritten in
place, four repointed to the new mode count / zh key / wire constants, none
added, none deleted). The other four test targets green as well: `cli_help` 3,
`startup_session_e2e` 12, `sigterm_cleanup` 1, `tcp_attach` 1.
`--dump-frame 100x34` byte-identical to the Phase-4 frame (1815 bytes, 35 rows)
under both the developer's `CROW_HOME` and a clean one, and `--demo` identical
to plain — a namespace rename repaints nothing.
`grep -rni "cordis\|_dsh" src` → **0**; `grep -rn "_dsh" tests` → **0**;
`grep -rni cordis` over `src` + `tests` → **1**, the deliberate `"--cordis"`
rejection pin. The crate's 8 other `cordis` hits are prose in `README.md:128-129,147`,
`AGENTS.md:11,19-20,22` and `docs/README.md:4` — 7.4's, and now doubly stale:
those lines still call `/plugins`, `/cordis-plugins`, `/ui` and `/liang` "live
slash commands" and still point at `src/cordis.rs`, which is `src/ext.rs` now.

*Carried forward, not caused here:* the bin-profile build warns
`field ui_preset is never read` (`app.rs:177`). Phase 4.1 deleted its last
reader, the `ui_preset == "deepseek"` banner branch; the `--tests` gate cannot
see it because the settings round-trip tests read the field, and the field has
to stay — `UiSettings` has no `flatten`/unknown-key map, so dropping it would
drop the `uiPreset` key out of `settings.json` on the next patch-write. Left
alone deliberately rather than `#[allow]`-ed: whether `uiPreset` should drive
something now (a palette pack, the slot logo) is a product call for 7.4/7.5 or
later, not a drive-by inside a rename phase.

**Commit:** `refactor(client)!: the _dsh/cordis extension family is now _crow/tui`

---

## Phase 6 — the test vocabulary

~400 hits. Mechanical, and the reason it is last-but-one: every earlier phase
rewrites some of these files anyway, so renaming first would just be churn.

[x] 6.1 **`dsh-*` fixture names** — `dsh-test` (156), `dsh-acp` (22), `dsh-tui`,
    `dsh-runtime`, `dsh-newest|past|alpha|old|new|cur|fb|blank|mid|start`,
    `agent-dsh-test` — become `crow-*` equivalents across
    `app__mode_tests.rs`, `ui__tests.rs`, `app__session_tabs_tests.rs`,
    `acp__tests.rs`, `sessions__tests.rs`, `app__resume_tests.rs`.
    *Verify:* the test count is unchanged by this item (a rename adds and
    removes nothing) and the suite is green.
    *Done:* an ordered 67-pair map, longest-first so `dsh-sess-limit` is
    replaced before `dsh-sess`, applied with the `edit` subtool
    (`replace_all`) across all 54 `tests/**/*.rs`: **329 replacements in 23
    files**. `dsh-test`→`crow-test`, `dsh-acp`→`crow-acp`,
    `dsh-runtime`→`crow-runtime`, `dsh-tui-*`→`crow-*`, every `dsh-<sess>`
    id→`crow-*`, `builtin-dsh`→`builtin-agent`.
    *Correction:* the test count is indeed unchanged (941 → 941) but the suite
    was **not** immediately green — `crow-` is one char wider than `dsh-`, and
    three tests pin geometry rather than vocabulary:
    - `app__session_tabs_tests.rs` (2 tests) — an untitled tab's label is
      `short_id(session_id)` (`app/staging.rs:118`: the first **8** chars), so
      `dsh-test` rendered whole while `crow-test` renders as `crow-tes`. Both
      assertions now compare against `short_id("crow-test")` rather than a
      literal, which pins the real contract instead of a width accident, plus
      `assert_eq!(parked, "crow-tes")` so the clamp itself is stated. The
      `open_eight_tabs` doc comment (tab 0 = 13 cols, rest 12) was still
      arithmetically right but for the wrong reason; it now says the label
      clamps to 8.
    - `ui__tests.rs::session_picker_rows_align_label_and_meta_columns` — the
      fixture's meta is hand-padded to imitate `session_picker_row`'s
      `{short:<8}` (`app/staging.rs:143`). `dsh-alp` is 7 chars so it carried
      two spaces; `crow-alp` is exactly 8 so it carries one. Dropping the space
      reproduces what production emits — it is not a nudge to force the
      assertion green (61 vs 60 cols was the failure).

[x] 6.2 **`martty-*`** temp dirs, env vars and test names (`MARTTY_SHELL_TEST`,
    `/opt/martty`, `work/acme/martty`, `martty-file-ref-*`,
    `martty-proto-wedge-*`, `martty-shell-*`, `martty-at-menu-ws-*`) → `crow-*`.
    *Verify:* `grep -rni martty tests` → 0; suite green.
    *Done:* `MARTTY_SHELL_TEST`→`CROW_SHELL_TEST`,
    `martty-{shell,file-ref,proto-wedge,at-menu-ws}`→`crow-*`, and
    `/work/acme/martty`→`/work/acme/client` — 17 chars → 17 chars, so the
    narrow-terminal geometry the `composer_cap_*` tests pin is untouched.
    *Correction:* the verify as written is **wrong**. `grep -rni martty tests`
    is 10, not 0, and every surviving hit is an *absence pin* that stops
    meaning anything if it is renamed: `main__cli_args_tests.rs` 8
    (`MARTTY_HOME`, `/opt/martty`, `~/.martty/settings.json`,
    `a_pre_rebrand_martty_home_is_not_read`), `sessions__tests.rs:95`
    (`.martty/sessions` seeded with `martty-gone`, proving the legacy root is
    never scanned), `ui__tests.rs:1807` (`for name in ["deepseek","martty",
    "dsh","whale"]` — the guard that no logo primitive of that name survives).
    Restated verify: **every surviving hit is an absence pin**; suite green.

[x] 6.3 **`deepseek-*` model ids and provider ids in canned payloads** → neutral
    crow-shaped ids, except where a test is specifically about the deepseek
    *palette* (4.2), which keeps its name on purpose.
    *Verify:* `grep -rni deepseek tests` returns only palette tests; suite green.
    *Done:* the map took `deepseek-v4{-pro,-flash}`→`acme-v4*`,
    `DeepSeek V4`→`Acme V4`, `deepseek-v3`→`acme-v3`, `deepseek/m1`→`acme/m1`,
    `deepseek-official`→`acme-official`,
    `current-deepseek-model`→`current-agent-model`,
    `@deepseek-ai/dsh-tool-bash`→`@acme-ai/acme-tool-bash`. Then, by hand, the
    payloads a name map cannot reach because they are *prose the assertions
    read*: `{"provider":"deepseek"}`→`"acme"` and `"DeepSeek API key"`→
    `"Acme API key"` (`acp__tests.rs:1234/1245`);
    `"Log in with a DeepSeek API key"`→`"Log in with an Acme API key"` at
    `acp_auth__tests.rs:7` **and** `:150`, which asserts it, plus that
    fixture's `…shared with the dsh Web UI` description;
    `uiPreset:"deepseek"`→`"acme-compositor"` (`app__mode_tests.rs:217/235` —
    `UiSettings` has no flatten map, so an unknown key has to round-trip
    verbatim or the save drops it); the `/ui` catalog and overlay-select
    plugin fixtures → `Alpha`/`Beta` with id `beta` (**not** `Standard`, whose
    `position()` would find the "Standard mode" chrome chip first);
    `_meta.dsh`→`_meta.acme` (`events__tests.rs:964/974` — deliberately *not*
    `crow`, which is this client's own capability namespace, and the test's
    whole point is that the key is opaque pass-through); the
    `deepseek-harness-tui` workspace paths in `sessions__tests.rs:30-31` and
    `ui__tests.rs:125/134/143/151`; and two skill/auth descriptions at
    `app__mode_tests.rs:4260/4287`.
    *Correction:* the verify as written is **wrong**. `grep -rni deepseek
    tests` is 9, and only 6 are palette tests (`theme__tests.rs`:
    `builtin("deepseek")`, `"DeepSeek Blue"`, `DEEPSEEK_450/500`,
    `the_deepseek_palette_survives_as_a_pack_and_nothing_more` — kept on
    purpose by mandate rule 3). The other 3 are absence pins: `cli_help.rs:40`
    and `main__cli_args_tests.rs:151` (both `!HELP.contains("DEEPSEEK")`) and
    `ui__tests.rs:1807`. Restated verify: **every surviving hit is an absence
    pin or the palette**; suite green.

**The negative assertions a rename would have made vacuous.** A `!contains`
that used to exclude brand vocabulary passes forever once the vocabulary is
gone, so each one became a positive pin on the behaviour it was really about —
this is the "rewritten, never silently deleted" rule applied to assertions
rather than tests:

- `codex_model_chip_waits_for_acp_then_uses_the_reported_session_model` —
  `!pending.contains("deepseek-chat")` → `!pending.contains("gpt-5.6-codex")`
  (the model this test itself reports at `:454`), and the trailing negative →
  `assert_eq!(displayed_model(&app).as_deref(), Some("gpt-5.6-codex"))`.
- `attached_landing_does_not_guess_runtime_before_initialize_or_after_failure`
  → `assert_eq!(displayed_model(&app), None, "{text}")` — `ui.rs:2164-2173`:
  the client has no model of its own to display.
- `new_tab_landing_never_falls_back_to_old_runtime_or_auth` →
  `assert!(text.contains("waiting for ACP"))`, which is what `active_runtime`
  yields for an attached non-demo app whose `server_info` a new tab cleared.
- `welcome_info_uses_the_active_acp_runtime_and_reported_session_model` →
  `!pending.contains("gpt-5.6-sol")` before the report and
  `!reported.contains("waiting for ACP")` after it.
- `welcome_auth_distinguishes_pending_and_failed_authenticate` —
  `!failed.contains("host dsh")` → `failed.contains("Log in with Google")`.
  *Correction:* this row is built by `ui.rs:4189-4196`, **not** `info.rs:102`
  or `:270`; the copy is `sign-in failed · {method_name} · /auth`, so the
  method name is the honest positive pin. `info.rs:102`'s `ACP authenticate
  failed` is the `/session` *overlay*'s copy and only appears when
  `auth.message` is None there — asserting it on the welcome row would have
  been a green-for-the-wrong-reason in reverse.
- `live_deepseek_landing_also_uses_acp_instead_of_startup_provider_and_model`
  → `live_landing_also_uses_acp_instead_of_startup_provider_and_model`.
- `ui__rpc_probe.rs:201`'s comment read "crow-acp folds userQuestions into
  one" after the map ran. That is the *agent*'s behaviour, and the mechanical
  rename had turned a true statement about someone else's runtime into a false
  one about ours — now "the agent folds userQuestions into one".

**Phase 6 gate result:** `cargo check --locked --tests -j 6` rc 0 with exactly
the 3 permanent warnings (unused `Path` @ `main__cli_args_tests.rs:2`, unused
`ctl` @ `ui__tests.rs:3602`, non-snake-case `dd_kills_the_line_and_gg_G_jump` @
`input__vim__tests.rs:74`); `cargo test --locked --bin crow -j 6` → **941
passed, 0 failed** (941 → 941: no test added or deleted, and three test fns
renamed to match their new fixtures — `dsh_acp_terminal_login_…` →
`crow_acp_terminal_login_…`, `dsh_question_schema_…` →
`agent_question_schema_…`, `live_deepseek_landing_also_uses_acp_…` →
`live_landing_also_uses_acp_…` — plus the `dsh_acp_methods` helper; a rename
changes a test's name, not what it pins);
`--dump-frame 100x34` → 1815 chars / 35 rows, **byte-identical** to
`/tmp/rebrand-p4-baseline.frame` (saved as `/tmp/rebrand-p6-clean.frame`);
`cli_help` 3, `startup_session_e2e` 12, `sigterm_cleanup` 1, `tcp_attach` 1 —
all green. 23 files changed, 377 insertions, 373 deletions.

Surviving brand vocabulary in `tests/`, every hit deliberate: `liang` 43
(parked pet machinery, rule 4), `dsh` 12 (absence pins —
`main__cli_args_tests.rs` 8, `sessions__tests.rs` 2, `app__mode_tests.rs:123`'s
retired `dsh-tui-settings.json` cache pin, `ui__tests.rs:1807`), `martty` 10
(absence pins), `deepseek` 9 (6 palette + 3 absence pins), `whale` 4 (pet and
logo-primitive guards), `cordis` 1 (`main__cli_args_tests.rs:128`'s
`"--cordis"` rejection pin — the rest of the `cordis` *fixture* vocabulary was
already swept in 5.2, which is why Phase 6 never listed it), `openma` 0.

For Phase 7, two counts that will otherwise be misread: `grep -rni dsh src` →
5, and **all 5 are the substring "handshake"** (`acp.rs` 4,
`acp/negotiate.rs` 1) — false positives, not brand vocabulary. And
`grep -rni deepseek src` → 37: `theme.rs` 31 (the palette, rule 3), `pet.rs` 2
(rule 4), and the 4 provenance module docs (`events.rs:1`, `file_ref.rs:3`,
`proto.rs:1`, `transcript.rs:3`) that 7.5 owns.

**Commit:** `test(client): the fixture vocabulary is crow's`

---

## Phase 7 — docs, assets, scripts, packaging

[x] 7.1 `assets/promo/build.py:89` — `github.com/openma-ai/deepseek-harness-tui` →
    the crow repo; sweep the rest of that script for brand text baked into
    promo images.
    *Done:* `assets/promo/` is deleted outright — `build.py`, `DESIGN.md`,
    `social-preview.png` — together with six old-brand screenshots
    (`banner-v020`, `agent-turn`, `skills-menu`, `harness-add`,
    `harness-switch`, `image-preview`.png). Each of the seven images was
    looked at with `vision` before it went: whale logo, "DEEPSEEK HARNESS"
    lockup, `dsh --profile martty` command lines, `deepseek-v4-*` model chips,
    a live `/liang` menu entry, the openma URL. Nothing references any of them
    — `Cargo.toml`'s `include` list carries only the two pet PNGs (both still
    present), no `include_bytes!` points at them, no doc links them.
    `assets/screenshots/liang.png` stays (the Phase 4 decision, rule 4), so
    `assets/` is now `crow-cli-ascii.txt`, `pet/*` and that one screenshot.
    `.gitignore` dropped `/npm-martty`; `Cargo.toml:14`'s comment over the
    asset list reads "Screenshots and docs".
    *Correction:* there is no URL to retarget. `build.py` composed the promo
    image from source JPEGs that were **never committed** — `git log` finds no
    trace of them at any point — so the script could not run in this repo even
    before the sprint. Rewriting its URL would leave a script that still
    cannot run, beside a `DESIGN.md` whose entire subject is a whale lockup.
    For assets, "no shim" means delete.

[x] 7.2 `docs/tui-palette.v0.schema.json` `$id`
    (`https://openma.ai/dsh-tui/tui-palette.v0.schema.json`) → crow-ai.dev, and
    the `$schema` reference in each of the 8 `docs/fixtures/*.v0.json`.
    *Verify:* the palette loader tests still parse every fixture (they read
    `$schema`-tagged files from `docs/fixtures/` at `$CARGO_MANIFEST_DIR`).
    *Done:* `$id` → `https://crow-ai.dev/crow-client/tui-palette.v0.schema.json`;
    `title` → "crow-client palette protocol 0"; and the `$comment`, which
    called the file the "Plugin ABI for `tuiTheme.register`" — a JS API that
    left with the npm layer — now says what the schema actually pins:
    "Palette ABI: what a pack must carry to be selectable." The title and the
    `$comment` are both invisible to 7.5's grep, which is why 7.2 owns them.
    All 10 fixtures still parse as JSON; the file is documentation for an
    outside editor, nothing in `src/` reads it.
    *Correction:* the second half of the item describes files that do not
    exist. **No** fixture carries a `$schema` key — 0 of the 10 files in
    `docs/fixtures/`, not 8 of 8 — and they *cannot*: `PalettePack::from_json`
    rejects any key outside `id`/`label`/`dark`/`light`/`background`
    (`theme.rs:526-533`, "unknown palette field"), so a `$schema` annotation
    would be a hard parse error, not something the loader looks past. The
    fixtures are pulled in with `include_str!` and parsed by that function, so
    the schema file is documentation for an outside editor and nothing else —
    which is exactly why its `$id` was the only thing here that could go
    stale. The verify still holds as written: every fixture parses, 941 green.

[x] 7.3 `scripts/collect-freeze-diag.sh` — pgreps `martty` binaries and writes
    `/tmp/martty-freeze-diag.*`; retarget at `crow`.
    *Done:* six sites — the header comment ("when the crow TUI looks frozen"),
    the `mktemp` prefix (`/tmp/crow-freeze-diag.XXXXXX.txt`), the
    `pgrep -f 'vendor/[^ ]*/crow|target/(devlocal|debug|release)/crow'`
    pattern, `pgrep -xo crow`, the `== candidate crow processes:` heading and
    the `(none found — is the TUI actually a crow process?)` hint. `bash -n`
    clean; `grep -rni martty scripts` → 0.

[x] 7.4 `README.md`, `AGENTS.md`, `docs/README.md` — the "what is still vestigial
    here" lists describe the pre-sprint state and will be wrong. Rewrite them
    to the post-sprint truth: what is parked and where the machinery lives,
    what the palette situation is, and that the client owns no model config.
    *Verify:* read top to bottom; every claim checked against the tree, not
    against memory.
    *Done — `README.md`:* the intro's "still carry branding from the project
    this one was forked out of" is now the honest post-sprint statement (one
    surviving attribution, `LICENSE:3`, pending an attribution pass); the app
    table's `crow` row says what it is built from (`the crow-client crate in
    this repo is *today*; the binary is crow`); the heading is
    `### This repo: crow-client v0.1.0, binary crow` and the build line points
    at `target/release/crow`; "24 slash commands" → **20 live + 4 parked**;
    "8 palettes" → **9 palette fixtures + `demo-surface.v0.json`**; and the
    whole "What is still vestigial here" list was rewritten rather than
    patched — no provider/model/credentials and `/model`+`/auth` are the
    agent's over ACP, `theme.rs` is the house ramp plus packs with one
    retained blue pack that is *selectable and nothing more*, the four parked
    commands with the file each piece of machinery lives in
    (`src/ext.rs`, `src/pet.rs`, `assets/pet/liang-*.png`, the pickers, the
    `run_slash` handlers, the zh descriptions), `slots.rs` +
    `app.harness_badge` permanently empty, `locale.rs`'s zh requirement,
    `docs/composer-input.md` still Chinese, `LICENSE:3`. The trailing
    "docs from the Martty era" sentence is de-branded.
    *Done — `AGENTS.md`:* "no Cordis host, no dsh profile" → no plugin host,
    no profile system, and nothing answers `_crow/tui/*` in `src/ext.rs`,
    which is *why* four commands are parked; the `theme.rs` bullet no longer
    claims a 1:1 DeepSeek token map or points at `src/deepseek_logo.rs` and
    `assets/martty-lockup.svg` (neither file exists) — it states the palette
    layer: `CROW_50…CROW_900`, the six `BUILTIN_PALETTE_IDS`, protocol-0
    parse, no logo module, no lockup asset; `/plugins, /cordis-plugins, /ui,
    /liang are live` → `/plugins, /dynamic-plugins, /ui, /liang are **parked,
    not live**` with `src/ext.rs` as the wire-name table and `src/slots.rs` +
    `src/pet.rs` as the receiving ends (`src/cordis.rs` does not exist);
    "arrives from a Cordis slot snapshot" → "compositor slot snapshot" (the
    claim itself is still true and still load-bearing);
    `DSH_TUI_RUST_CACHE_MAX_GIB` → `CROW_RUST_CACHE_MAX_GIB` and
    `$DSH_TUI_CARGO_TARGET_DIR` → `$CROW_CARGO_TARGET_DIR`, both matching
    `scripts/cargo-guard.sh:6-10`; the release line no longer says `PLAN.md`
    and `TODO.md` were deleted (they are this sprint's working docs at the
    repo root — `CHANGELOG.md` is the one that is gone); and `rustc 1.95` →
    `rustc 1.98`, with the reason `let_chains` are avoided restated correctly
    (they are edition-2024-only and this crate is edition 2021, so the
    toolchain version was never the real constraint).
    One more stale claim the sweep cannot see, caught by the read-top-to-bottom
    the verify asks for: "**There is no plugin command namespace to collide
    with** … a builtin name is the only thing that exists" was false even
    before this sprint. The agent's `availableCommands` become host skills in
    the same `/` menu (`skills_from_available_commands`, `events.rs:950`, fed
    from `acp.rs:1804-1819` and `acp/v2.rs:785`), and this repo's own agent
    sends them (`src/crow_cli/agent/main.py:566`) — which is exactly why
    `app/slash.rs:43,74` filters both non-builtin sources against the builtin
    names. Rewritten as "the `/` namespace has three sources, and builtins
    win", with the third source (compositor-pushed plugin commands) named as
    parked. A constraint file that says a collision is impossible is worse
    than one that says nothing, because the dedupe code reads like paranoia.
    *Done — `docs/README.md`:* only lines 3-6 were wrong ("Everything
    Martty-era — the Cordis plugin host, the dsh profile…"), now "Everything
    that came from the project this one was forked out of — the plugin host,
    the profile system…". The rest was checked and is accurate: 8 shipped
    palettes + `demo-skin` + `demo-surface` (referenced by nothing), nothing
    in `src/` reads `docs/fixtures/` at runtime, `--demo-skin` gone and pinned
    absent by `tests/cli_help.rs`.
    *Every number above was read out of the tree, not remembered:* 20 live
    entries by counting uncommented `name:` in `slash_catalog.rs` (a naive
    `name:\s*"…"` regex says 24 — it counts the four parked ones);
    `BUILTIN_PALETTE_IDS` = 6; `docs/fixtures/` = 10 files;
    `harness_badge` fed at `app/pump.rs:408` from `conversation.harness`
    (`slots.rs:274`); `cargo-guard.sh` env vars; `rustc --version` = 1.98.1;
    `src/deepseek_logo.rs`, `src/cordis.rs`, `assets/martty-lockup.svg`
    absent.

[x] 7.5 Final sweep: `grep -rni "deepseek\|martty\|dsh\|openma\|liang\|cordis"`
    over the whole crate. The only surviving hits are the intentional ones —
    the deepseek palette in `theme.rs`, the parked `/liang` registry comment and
    its `pet.rs` machinery, `assets/pet/liang-*.png`, and `LICENSE:3`
    (deferred by the user). Anything else is a miss; fix it.
    *Done — the src pass first, so the sweep had something to converge on:*
    `theme.rs`'s struct doc and its 15 `--dsw-alias-*` /
    `--dsw-specific-bubble` field docs now say what each token *does* instead
    of which web token it mirrors (15 doc lines in `theme.rs` alone;
    `grep -rn dsw` over the whole crate is 0 now, but only because the sweep
    below caught a sixteenth, in `transcript.rs`); the
    provenance module docs were de-branded in place — `events.rs:1`,
    `proto.rs:1`, `transcript.rs:1-6`, `file_ref.rs:3-6` keep the "this shape
    was learned from a web UI" fact without wearing the name. `theme.rs` is
    now only the palette pack, which is what rule 3 permits.
    *Done — the sweep,* run as
    `grep -rniE 'deepseek|martty|dsh|cordis|openma|whale|liang'` over the
    whole crate (`whale` added: it is the pet's fallback art and the name of
    the deleted logo primitive, so it belongs in the net). **133 lines, every
    one classified:**
    - `src/` 70 — `theme.rs` 31 deepseek (the palette, rule 3) + 2 whale
      (`whale_gradient()`, the pet fallback's two colours); `pet.rs` 6 liang +
      3 whale + 1 deepseek (line 1's homage, rule 4); `ui.rs` 9 whale + 1
      liang (`WHALE_XS` half-block fallback, `pet_rect`); `app.rs` 2 liang
      (the `pet_*` field docs); `app/slash.rs` 4 liang (the parked handler and
      its two zh strings); `app/slash_catalog.rs` 6 liang (the parked entry's
      note); `locale.rs` 1 liang (the zh `command_desc` arm); `acp.rs` 4 +
      `acp/negotiate.rs` 1 `dsh` — the substring "handshake", exactly as
      Phase 6 predicted.
    - `tests/` 56 — absence pins (`main__cli_args_tests.rs`: martty 8, dsh 8,
      cordis 1, deepseek 1; `sessions__tests.rs` 3; `ui__tests.rs:1807`'s
      logo-primitive guard; `cli_help.rs:40`; `app__mode_tests.rs:123`'s
      retired `dsh-tui-settings.json`), the palette (`theme__tests.rs` 6), the
      pet (`pet__tests.rs` 9, `ui__tests.rs` 7, `app__mode_tests.rs` 11).
    - `docs/`, `scripts/`, `assets/`, `packaging/`, `web/`, `fixtures/`,
      `.gitignore` — **0**. `Cargo.toml` — 2, the `assets/pet/liang-*.png`
      asset lines. `LICENSE:3` — `OpenMA contributors`, deferred by the user.
    - Filename sweep (grep cannot see these): the only brand-named paths left
      are `assets/pet/liang-{idle,working}.png` and
      `assets/screenshots/liang.png`, all three kept by rule 4.
    *Five misses found and fixed.* Phase 6's inventory called all 43 `liang`
    lines in `tests/` pet machinery; 19 of them were not — they were plugin
    fixtures that happened to be named after the old brand. The fifth is a
    token name no brand grep can see:
    - `liang-effort` / `"Liang reasoning effort"` → `effort-slider` /
      `"Reasoning effort"`: the client-plugin command fixture
      (`app__mode_tests.rs:3269-3312`) and the three overlay-slider fixtures
      (`app__mode_tests.rs:3522/3552`, `:3857/3884`, `ui__tests.rs:2656-2684`).
      The typed prefixes became `/effort-sli` and `/effort-slider`;
      `slash_matches` filters with `name.starts_with(prefix)`
      (`app/slash.rs:26,42`), so the builtin `/effort` cannot collide and
      `matches.len() == 1` still pins what it pinned. The new title is 6
      chars shorter than the old one, so the 100×30 frame assertion is if
      anything safer.
    - `"whenTheme": "liang"` → `"no-such-theme"`
      (`app__mode_tests.rs:3271`). The test is
      `client_plugin_command_catalog_does_not_interpret_legacy_theme_metadata`;
      the value's whole job is to be a theme id the client does not know, and
      saying so is a stronger pin than a brand name that happens to be
      unknown.
    - `/opt/liang/stage-00.png` → `/opt/crow/stage-00.png`
      (`ui__tests.rs:280`, `theme__tests.rs:197/205`) — a palette *background*
      path with nothing to do with the pet, and `/opt/crow` is already Phase
      6's vocabulary.
    - `src/pet.rs:5-6` — "hammers away on a tiny terminal while **DeepSeek**
      runs. `/liang` toggles him; see README "The /liang meme"" → "while the
      agent runs", and the dangling pointer now points at the parked entry's
      note in `src/app/slash_catalog.rs`. No README in this repo's history has
      ever had that section (`git log -S'The /liang meme'` → empty), so it was
      stale before the sprint started. Lines 1-2 stay: naming Liang Wenfeng is
      attribution for retained art, in the same class as the 29
      grok-provenance comments.
    - One more that the pattern cannot catch: `src/transcript.rs:1553`'s
      "the user bubble uses `--dsw-specific-bubble`" — a CSS custom-property
      name from the deleted web UI, and the last `dsw` in the crate. It now
      names the tokens the code actually reads (`bubble_bg` / `bubble_fg`).
    *After:* `grep -rni liang tests` 43 → **24** lines, `grep -rni deepseek
    src` 37 → **32** (4 provenance docs + `pet.rs`'s "while DeepSeek runs"),
    `grep -rni dsw` → **0**, `martty` 10 (all absence pins), `cordis` 1 (the
    `--cordis` rejection pin), `dsh` 17 (src 5 = "handshake", tests 12 =
    absence pins), `whale` 18 (pet fallback art + the logo-primitive guard),
    `openma` 1 (`LICENSE:3`, deferred).

**Phase 7 gate result:** `cargo check --locked --tests -j 6` rc 0 with exactly
the 3 permanent warnings (unused `Path` @ `main__cli_args_tests.rs:2`, unused
`ctl` @ `ui__tests.rs:3602`, non-snake-case `dd_kills_the_line_and_gg_G_jump` @
`input__vim__tests.rs:74`); `cargo test --locked --bin crow -j 6` → **941
passed, 0 failed** (941 → 941 again: 7.5 renamed fixtures and comments, not
tests); `cli_help` 3, `startup_session_e2e` 12, `sigterm_cleanup` 1,
`tcp_attach` 1 — all green; `--dump-frame 100x34` → 1815 chars / 35 rows /
2819 bytes on disk, **byte-identical** to `/tmp/rebrand-p4-baseline.frame`
(saved as `/tmp/rebrand-p7-clean.frame`).

The green is a *built* green, not a replayed one: cargo replays cached
warnings for a unit it considers fresh, so a stale artifact and a real pass
look identical in the output. Both binaries were checked against the clock —
`target/debug/deps/crow-e748d5d90d72350e` (the test bin) rebuilt at 15:29:31
and `target/debug/crow` at 15:29:37, against a last source edit at 15:24:29
(`src/transcript.rs`). Also run: `bash -n scripts/collect-freeze-diag.sh` rc 0,
the schema and all 10 `docs/fixtures/*.json` re-parsed with `json.loads`, and
`git log -S` on the two claims about history (build.py's source JPEGs, the
README's missing `/liang meme` section). Seven images went, 4.63 MB / 4.41 MiB
of old brand art; nothing was added.

**Commit:** `docs(client): the rebrand, written down`

---

## Phase 8 — the whole gate, and the record

[x] 8.1 `cargo check --locked --tests -j 6` and `cargo test --locked --bin crow -j 6`
    from clean; the 3 pre-existing warnings still exactly 3.
    *Done:* rc 0 / **941 passed, 0 failed**, exactly **3** warnings — unused
    `Path` @ `main__cli_args_tests.rs:2`, unused `ctl` @ `ui__tests.rs:3602`,
    non-snake-case `dd_kills_the_line_and_gg_G_jump` @
    `input__vim__tests.rs:74` — all three on **stderr** in short format, zero
    warning lines on stdout. Same three lines, same bindings as the Phase-7
    gate.
    *"From clean" was made to mean something,* because cargo replays stored
    warnings for a unit it considers `Fresh`, so a cached green and a built
    green are byte-identical in the output. Three steps, in order: (a) artifact
    mtimes compared against the last source edit; (b) a syntax error injected
    into `src/pet.rs` → check rc **101** in 7.4 s, which proves the gate
    actually compiles this crate rather than replaying it (restored at once;
    tree clean afterwards); (c) this crate's debug artifacts deleted by hand —
    `target/debug/{.fingerprint/crow-client-*,deps/crow-*,crow,incremental/crow-*}`,
    27 paths, **23.7 GiB** reclaimed — leaving every third-party dep in place
    and running no `cargo clean` anywhere (AGENTS.md forbids it and the target
    dir is shared with the other worktrees). Rebuilt from that state: bin test
    **941 passed** in 86.5 s with the 3 warnings freshly compiled, check rc 0 /
    3 warnings in 8.2 s. Warm re-run at the end of the phase: check 0.2 s, bin
    test 3.4 s — same 3, same 941.
[x] 8.2 `cargo build --release -j 6`, then drive the shipped binary the way
    `tests/startup_session_e2e.rs` does — a real PTY against
    `tests/fixtures/stub_acp_agent.py` — and `cargo run --release -- --demo`
    plus `--dump-frame` eyeballed.
    *Done:* `cargo build --release -j 6` rc 0 in 127.9 s →
    `target/release/crow`, 11,896,024 bytes, carrying exactly one warning — the
    known-deliberate `field ui_preset is never read` (`app.rs:177`, recorded
    under the Phase 5 gate, kept because the settings patch-write would
    otherwise drop `uiPreset`).
    The e2e suite was then run **in release**, which is the only way to point it
    at the shipped binary: `tests/startup_session_e2e.rs:309` hardcodes
    `env!("CARGO_BIN_EXE_crow")` with no env override, so the profile is what
    selects the path. `cargo test --release --locked --test
    startup_session_e2e -j 6` → **12 passed, 0 failed** (1.78 s of test, 97.9 s
    wall including the release harness build). That it drove the release binary
    and not the debug one is checked, not assumed: the harness
    `target/release/deps/startup_session_e2e-9bd8c126ff9ce174` contains the
    bytes `target/release/crow` and does **not** contain `target/debug/crow`.
    The other three integration tests followed in release — `cli_help` 3,
    `sigterm_cleanup` 1, `tcp_attach` 1 — so **17** release tests green, and
    the debug profile re-ran the same four at the same counts (3 / 12 / 1 / 1).
    `--dump-frame 100x34` from the release binary → 1815 chars / 35 rows / 2819
    bytes on disk, **byte-identical** to `/tmp/rebrand-p4-baseline.frame` (saved
    as `/tmp/rebrand-p8-release.frame`); the debug binary re-checked in the same
    pass, also byte-identical. `--help` → 1484 chars, crow-branded, zero
    `DEEPSEEK`.
    `--demo` was driven on a **real PTY**, not a pipe, because a TUI that sees a
    non-tty stdout takes different branches: a local `pty_drive()` helper
    (openpty → fork → setsid/TIOCSCTTY → TIOCSWINSZ 110×30 →
    `execve(target/release/crow)`, 5 s of captured output, SIGTERM, `waitpid`)
    → exit code **0**, 5897 chars. On screen: the `CROW_CLI` block wordmark
    (`logo.rs:15-22` — both the `██▓▓▓▒▒░░░░░▒▓` and the `└────────────┘` rows
    are present in the capture; this is *not* `assets/crow-cli-ascii.txt`,
    which no `include_str!` anywhere reads), `https://crow-ai.dev`,
    `version crow 0.1.0`, `runtime demo`, `model waiting for ACP`,
    `mode demo — scripted turns, no API calls`, `session crow-65c7c5f0`,
    `/keys shortcuts`, `esc interrupt`. Zero occurrences of `deepseek`,
    `martty`, `dsh` or `api key` in 5897 chars of live UI: the demo never asks
    anyone for a credential.
[x] 8.3 The Python side is untouched by this sprint, but the repo is one workspace:
    `uv run pytest tests/unit -q` from the worktree root, to prove it.
    *Done:* **788 passed**, rc 0, 27.4 s. "Untouched" is proven rather than
    asserted: across the 95 files this branch changes, `git diff --stat
    $(git merge-base HEAD main) HEAD -- '*.py' pyproject.toml tests/ src/`
    returns exactly one entry — the *deletion* of
    `crates/crow-client/assets/promo/build.py` (105 lines, Phase 7's
    unrunnable promo script). Nothing under `src/crow_cli/` or `tests/` moved.
    *The first run was red, and the red was chased instead of waved off:*
    1 failed / 787 passed —
    `tests/unit/test_tools_web.py::test_run_screenshot_rides_the_row`,
    Playwright `Page.captureScreenshot: Unable to capture screenshot` against a
    local `http://127.0.0.1:37717/js`. "Environmental" is a claim that needs
    evidence, so three independent checks: (a) the test passes alone, 1.8 s;
    (b) the full suite re-runs green, 788 passed; (c) the branch changes zero
    Python. All three agree — a headless-Chromium screenshot flaking under the
    load of a 788-test run, not a regression.
[x] 8.4 `TODO.md` and `PLAN.md` fully checked, each with its evidence line; the
    deferred list intact with its reasons.
    *Done:* PLAN 8.1–8.5 each carry their evidence (this block) and TODO's Gate
    section gains a **Phase 8 gate result** paragraph after Phase 7's. The
    deferred list is intact at five items with their reasons — the LICENSE
    attribution line, `crate/target`'s 71 GiB, the Cordis/plugin subsystem's
    existence, `locale.rs`'s bilingual-by-construction rule, the legacy
    JSON-RPC attach path — plus the open `- [ ]` LICENSE scope bullet. There is
    no Phase 8 bullet in the scope capture to tick, and that is correct: Phase 8
    adds no scope, it re-proves Phases 1–7 against the shipped artifact, and
    every bullet it re-proves was already `[x]`.
    One source fix rode along — the only non-documentation change of the phase.
    The root `Cargo.toml:14-18` comment over `[profile.devlocal]` advertised
    `DSH_TUI_CARGO_PROFILE=devlocal`, a `scripts/devlocalinstall.sh` that does
    not exist (`scripts/` is ten Python migration and e2e scripts), and "the
    shipped npm packages", which left in Phase 5 (`crates/crow-client/npm/` does
    not exist). It now names only what is real: `cargo build --profile devlocal`
    while iterating, and `[profile.release]` (fat LTO, stripped) as what ships.
    The profile itself is real and untouched, and `devlocal` still appears in
    `scripts/collect-freeze-diag.sh:12` — correctly, since that is a `pgrep`
    process matcher for a running binary's path, not a build instruction.
[x] 8.5 Report: what changed, what was verified, what is deferred, and the one
    visible difference a user will notice (the default palette is purple now,
    and the binary no longer asks anyone for a DeepSeek key).
    *Done:* delivered as the sprint's closing report. The one visible difference
    a user meets: **the default palette is crow purple, and the binary never
    asks anyone for a DeepSeek key** — credentials belong to the agent, and ACP
    `authenticate` is the only sign-in story. Verified on the *shipped* release
    binary, not on a debug build: `--help` (1484 chars) offers no credential
    flag and names no brand; `--demo` on a real PTY reports
    `model waiting for ACP` with zero occurrences of `api key`; and Phase 1's
    pin `child_env_carries_no_provider_and_no_credentials` still holds inside
    the 941.

**Phase 8 gate result:** both profiles, same green. *Debug* — `cargo check
--locked --tests -j 6` rc 0 with exactly the 3 permanent warnings (unused
`Path` @ `main__cli_args_tests.rs:2`, unused `ctl` @ `ui__tests.rs:3602`,
non-snake-case `dd_kills_the_line_and_gg_G_jump` @ `input__vim__tests.rs:74`,
all on stderr in short format); `cargo test --locked --bin crow -j 6` → **941
passed, 0 failed**; `cli_help` 3, `startup_session_e2e` 12, `sigterm_cleanup`
1, `tcp_attach` 1. *Release* — `cargo build --release -j 6` rc 0 with only the
deliberate `field ui_preset is never read`; the same four integration tests
against the shipped binary → 3 / **12** / 1 / 1, **17** release tests green.
`--dump-frame 100x34` → 1815 chars / 35 rows / 2819 bytes, **byte-identical**
to `/tmp/rebrand-p4-baseline.frame` from *both* binaries (release saved as
`/tmp/rebrand-p8-release.frame`). `--help` 1484 chars, no brand, no credential
flag. `--demo` on a real PTY: exit 0, crow wordmark, `version crow 0.1.0`,
`model waiting for ACP`, and zero hits for `deepseek` / `martty` / `dsh` /
`api key`. Python: `uv run pytest tests/unit -q` → **788 passed**.

The debug green is a *built* green, not a replayed one, and 8.1 records how that
was established rather than asserted: an injected syntax error in `src/pet.rs`
turned the gate red in 7.4 s (rc 101), then this crate's 27 debug artifact
paths were deleted by hand — 23.7 GiB, deps untouched, no `cargo clean` — and
the 941 plus the 3 warnings were recompiled from scratch in 86.5 s. The release
green is pointed at the right artifact by construction and then verified: the
e2e harness bakes `env!("CARGO_BIN_EXE_crow")` at
`tests/startup_session_e2e.rs:309`, and
`target/release/deps/startup_session_e2e-9bd8c126ff9ce174` contains
`target/release/crow` and not `target/debug/crow`. One red was seen all phase
and it was not this gate's: a Playwright screenshot flake under load in the
Python suite, disproved three ways in 8.3.

**Commit:** `chore(client): phase 8 — the shipped binary, driven`

**Merged to `main`:** `41ddb4c8`, a `--no-ff` merge of `5df74182` into
`29f3fb43`. The two sides share no file — main had moved on to `goal_start` /
`goal_reset` / `/goal` help (`src/crow_cli/**`, `ACP_V2.md`) while this branch
was entirely `crates/crow-client/**` plus the root `PLAN.md` / `TODO.md` /
`Cargo.toml` — and `git merge-tree --write-tree` reported the clean merge
before it was run. Re-proved on the merged tree, in the main worktree: check
rc 0 with exactly the 3 permanent warnings, `--bin crow` **941 passed**,
`cli_help` 3 / `startup_session_e2e` 12 / `sigterm_cleanup` 1 / `tcp_attach`
1, `--dump-frame 100x34` byte-identical to `/tmp/rebrand-p4-baseline.frame`,
`--help` 1484 chars with no brand and no credential flag, and
`uv run pytest tests/unit -q` → **806 passed** (the branch's 788 plus main's
18 goal tests). The main worktree's uncommitted work — the crate `description`
and the `0.1.46` bump in `pyproject.toml`/`uv.lock` — was stashed *by path*
for the merge and popped back intact: `crates/crow-client/Cargo.toml` now
carries both this branch's `include`-list comment and the user's description
edit on top, still uncommitted, still theirs.

---

## Rules for this sprint

- The client owns no model config. When tempted to add a default "so the UI has
  something to show", show nothing instead.
- No shim, no fallback, no `or_else(|| legacy_…())`. Deleted means deleted.
- Rename with `sg` (AST), not with substring replacement — `cordis_plugins`
  must not rewrite a local named `plugins`, and `dsh` must not touch `dshaped`.
- A test that pinned the old behaviour is rewritten to pin the new one. Deleting
  it silently is how a shim comes back.
- Parked machinery stays compiled and stays tested. Commented-out registry
  entries get a note saying where the rest of it lives.
- Paint changes get eyeballed with `--dump-frame`, not just compiled.
- Commit at every phase boundary, `Session-Id:` trailer, never a force-push.
