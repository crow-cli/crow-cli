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

5.1 **`cordis.rs` → the crow extension namespace.** The 22 wire constants
    `_dsh/cordis/tui/*` → `_crow/tui/*`, `_dsh/plugins/list` →
    `_crow/plugins/list`, `_dsh/cordis/plugins/{start,stop}` →
    `_crow/plugins/{start,stop}`; the capability key the client reads in
    `advertised_by_agent` (`agentCapabilities._meta.dsh.cordis.protocol`) and
    advertises itself in `acp_auth.rs:114-115` (`"dsh"` + `{cordis:{protocol}}`)
    → `_meta.crow.tui.protocol`. Rename the module file itself to something
    that says what it holds (`ext.rs`), and update `main.rs:12`'s `mod` line.
    *Verify:* `grep -rn "_dsh\|cordis::" src` → 0; the extension-path tests in
    `acp__tests.rs` / `events__tests.rs` green with the new method strings.

5.2 **The Rust identifiers.** `Cmd::FetchCordisPlugins`,
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

5.3 **The three vestigial plugin commands.** `/plugins`, `/cordis-plugins`,
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

**Commit:** `refactor(client)!: the _dsh/cordis extension family is now _crow/tui`

---

## Phase 6 — the test vocabulary

~400 hits. Mechanical, and the reason it is last-but-one: every earlier phase
rewrites some of these files anyway, so renaming first would just be churn.

6.1 **`dsh-*` fixture names** — `dsh-test` (156), `dsh-acp` (22), `dsh-tui`,
    `dsh-runtime`, `dsh-newest|past|alpha|old|new|cur|fb|blank|mid|start`,
    `agent-dsh-test` — become `crow-*` equivalents across
    `app__mode_tests.rs`, `ui__tests.rs`, `app__session_tabs_tests.rs`,
    `acp__tests.rs`, `sessions__tests.rs`, `app__resume_tests.rs`.
    *Verify:* the test count is unchanged by this item (a rename adds and
    removes nothing) and the suite is green.

6.2 **`martty-*`** temp dirs, env vars and test names (`MARTTY_SHELL_TEST`,
    `/opt/martty`, `work/acme/martty`, `martty-file-ref-*`,
    `martty-proto-wedge-*`, `martty-shell-*`, `martty-at-menu-ws-*`) → `crow-*`.
    *Verify:* `grep -rni martty tests` → 0; suite green.

6.3 **`deepseek-*` model ids and provider ids in canned payloads** → neutral
    crow-shaped ids, except where a test is specifically about the deepseek
    *palette* (4.2), which keeps its name on purpose.
    *Verify:* `grep -rni deepseek tests` returns only palette tests; suite green.

**Commit:** `test(client): the fixture vocabulary is crow's`

---

## Phase 7 — docs, assets, scripts, packaging

7.1 `assets/promo/build.py:89` — `github.com/openma-ai/deepseek-harness-tui` →
    the crow repo; sweep the rest of that script for brand text baked into
    promo images.
7.2 `docs/tui-palette.v0.schema.json` `$id`
    (`https://openma.ai/dsh-tui/tui-palette.v0.schema.json`) → crow-ai.dev, and
    the `$schema` reference in each of the 8 `docs/fixtures/*.v0.json`.
    *Verify:* the palette loader tests still parse every fixture (they read
    `$schema`-tagged files from `docs/fixtures/` at `$CARGO_MANIFEST_DIR`).
7.3 `scripts/collect-freeze-diag.sh` — pgreps `martty` binaries and writes
    `/tmp/martty-freeze-diag.*`; retarget at `crow`.
7.4 `README.md`, `AGENTS.md`, `docs/README.md` — the "what is still vestigial
    here" lists describe the pre-sprint state and will be wrong. Rewrite them
    to the post-sprint truth: what is parked and where the machinery lives,
    what the palette situation is, and that the client owns no model config.
    *Verify:* read top to bottom; every claim checked against the tree, not
    against memory.
7.5 Final sweep: `grep -rni "deepseek\|martty\|dsh\|openma\|liang\|cordis"`
    over the whole crate. The only surviving hits are the intentional ones —
    the deepseek palette in `theme.rs`, the parked `/liang` registry comment and
    its `pet.rs` machinery, `assets/pet/liang-*.png`, and `LICENSE:3`
    (deferred by the user). Anything else is a miss; fix it.

**Commit:** `docs(client): the rebrand, written down`

---

## Phase 8 — the whole gate, and the record

8.1 `cargo check --locked --tests -j 6` and `cargo test --locked --bin crow -j 6`
    from clean; the 3 pre-existing warnings still exactly 3.
8.2 `cargo build --release -j 6`, then drive the shipped binary the way
    `tests/startup_session_e2e.rs` does — a real PTY against
    `tests/fixtures/stub_acp_agent.py` — and `cargo run --release -- --demo`
    plus `--dump-frame` eyeballed.
8.3 The Python side is untouched by this sprint, but the repo is one workspace:
    `uv run pytest tests/unit -q` from the worktree root, to prove it.
8.4 `TODO.md` and `PLAN.md` fully checked, each with its evidence line; the
    deferred list intact with its reasons.
8.5 Report: what changed, what was verified, what is deferred, and the one
    visible difference a user will notice (the default palette is purple now,
    and the binary no longer asks anyone for a DeepSeek key).

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
