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

## Scope capture (unordered)

- [ ] **The client stops owning provider/model/credentials.** `MODEL_PRESETS`
      (five hardcoded deepseek ids) is the seed for `/model` when no agent
      catalog has arrived — it goes, and the picker seeds from `last_models`
      plus the effective current model only. `RuntimeConfig.provider`/`.model`
      stop being `String`s with deepseek defaults. `--provider`, `--base-url`,
      `--api-key`, `--max-tokens` leave the flag surface; `--model` stays (an
      explicit "run THIS", applied on bind via the same wire path ctrl+p uses)
      and `CROW_MODEL` stays, `DSH_MODEL` goes.
- [ ] **`legacy_dsh()` and everything it feeds, deleted.** `~/.dsh/.credentials.yaml`,
      `~/.dsh/settings.yaml` (`agent-default-model`), the two hand-rolled yaml
      scrapers, `LegacyDsh`, `has_credentials()`, `credential_source()`.
- [ ] **`child_env()` stops injecting `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL`**
      and stops exporting `CROW_CORDIS_CONFIG` (nothing has ever read it —
      verified: zero consumers in crow-cli's `src/`, `tests/`, `docs/`).
      The harness `env` from `settings.json` still applies.
- [ ] **The credential UI becomes ACP-only.** `ui.rs:4248-4262` (the
      `⚠ DEEPSEEK_API_KEY not set` line, EN + zh) and `info.rs:113-119`
      (`api key present · --api-key flag`) collapse into the branch that
      already exists and already tells the truth: credentials are the agent's,
      and ACP `authenticate` is the only sign-in story.
- [ ] **No martty/dsh homes.** `crow_home_from` keeps `CROW_HOME` →
      `~/.agents/crow` and loses `MARTTY_HOME` + `DSH_HOME`;
      `legacy_settings_paths*` (`~/.martty/settings.json`,
      `~/.dsh-tui/sessions/dsh-tui-settings.json`) deleted with its callers;
      `sessions.rs` discovers only the configured root, not `~/.crow-term`,
      `~/.martty`, `~/.dsh`, `~/.dsh-tui`; `DSH_TUI_KEYDEBUG` alias deleted
      (`CROW_KEYDEBUG` only).
- [ ] **The tests that PIN those shims get rewritten, not deleted.**
      `sessions_from_the_martty_and_dsh_homes_remain_discoverable`,
      `legacy_settings_come_from_the_martty_home_then_dsh_tui`,
      `a pre-rebrand MARTTY_HOME keeps its data` currently assert the behaviour
      we are removing. Each becomes the opposite assertion — legacy homes are
      NOT discovered — so the contract stays pinned.
- [ ] **`/liang` out of `SLASH_COMMANDS`** (commented, with a note pointing at
      `pet.rs` + `assets/pet/*.png`), handler and pet machinery untouched.
      `locale__tests.rs` iterates the catalog for the zh-desc gate and for
      name-sort, so both stay green; `run_slash("liang", …)` still works, which
      is what `app__mode_tests.rs:298` and `pet__tests.rs` drive.
- [ ] **The deepseek *logo* is not a theme.** The `ui_preset == "deepseek"`
      banner branch, `src/deepseek_logo.rs`, `assets/martty-lockup.svg` and
      `scripts/render-martty-lockup.swift` go; `logo.rs` (the crow-cli lockup)
      is the only banner. `ui_preset` keeps its `default`.
- [ ] **The deepseek palette stays a palette.** `theme.rs`'s `DEEPSEEK_50…900`
      ramp survives as a *named* pack; the builtin `default` pack stops wearing
      DeepSeek blue as its brand and wears crow's purple instead
      (`docs/styles/purple.css`, `docs/img/crow-icon-purple.svg` are the house
      brand). `--theme <dark|light>` help text stops saying "DeepSeek Web UI
      palette".
- [ ] **`DeepSeekStyleSheet`** in `markdown.rs` (5 sites) renamed to something
      that says what it is, not who it was copied from.
- [ ] **`demo.rs`**: the DeepSeek whale prose (2 passages), and the
      `"provider": "deepseek-official", "model": "deepseek-v4-flash"` in three
      canned JSON payloads, become crow-shaped. `--demo` and `--dump-frame`
      must still render.
- [ ] **The `_dsh/cordis` extension family renamed, machinery kept.**
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
- [ ] **`AGENT_MODES` demo seeds**: the `cordis` "Creator mode" entry and the
      "Shipped creator id is `cordis`" comment.
- [ ] **The vestigial plugin slash commands** `/plugins`, `/cordis-plugins`,
      `/ui` — they aim at a plugin host that does not exist. Rename away from
      cordis at minimum; whether they stay registered is a decision to record,
      not to guess at silently.
- [ ] **Test fixture vocabulary**: ~400 hits — `dsh-test` (156), `dsh-acp` (22),
      `dsh-tui`, `dsh-runtime`, `martty-*` temp dirs and env names,
      `deepseek-*` model ids in canned payloads. Renamed to crow-shaped names
      with every assertion's meaning preserved.
- [ ] **Docs, assets, scripts, packaging**: `assets/promo/build.py:89`
      (`github.com/openma-ai/deepseek-harness-tui`), `docs/tui-palette.v0.schema.json`
      `$id` (`https://openma.ai/dsh-tui/…`) and the `$schema` refs in the 8
      fixtures, `scripts/collect-freeze-diag.sh` (pgreps `martty`),
      `crates/crow-client/README.md` + `AGENTS.md` + `docs/README.md` prose
      (the "what is still vestigial here" list describes the old state).
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
