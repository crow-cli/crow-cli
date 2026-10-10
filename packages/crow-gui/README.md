# crow-gui — the crow IDE build pipeline ("crowdium")

Builds crow's IDE from Microsoft's open-source VS Code using a **vendored copy
of VSCodium's build pipeline**, rebranded to crow. Two artifacts come out, and
both are first-class:

| artifact | what it is | entry point |
| --- | --- | --- |
| `vscodium/VSCode-linux-<arch>/` | the Electron desktop app | `bin/crow` |
| `vscodium/vscode-reh-web-linux-<arch>/` | the browser server (`reh-web`) | `bin/crow-server` |

`crow-cli install crow` is what puts these on a machine; this directory is what
produces them.

## Provenance

- Vendored from [VSCodium/vscodium](https://github.com/VSCodium/vscodium)
  (MIT) at `5b01560f8419b3cbbe4b1aa0ce07183ef8c45b0f`, tracked files only,
  minus `src/insider` (crow builds the stable channel only).
- That pin builds **VS Code 1.135.0**, commit
  `08d4889f9ec4a1685d257b9b95de036c8e1ce1e5` (`vscodium/upstream/stable.json`).
- crow's edits to the vendored scripts live in
  `crow-patches/vscodium-pipeline.patch` and are marked `# crow:` in the files
  themselves. `./vendor.sh <clone> --diff` shows them; `--make-patch`
  regenerates them after you edit `vscodium/` directly (it captures modified,
  added and deleted files, binaries included).

## Layout

```
crow.env                              crow's product identity (the only place it is defined)
build.sh                              build entry point — wraps the vendored pipeline
vendor.sh                             re-create vscodium/ from upstream + crow's patch
crow-patches/vscodium-pipeline.patch  crow's modifications to the vendored scripts
vscodium/                             the vendored pipeline (see its own README/docs)
  prepare_vscode.sh                   product.json rewrite + patch application + npm ci
  patches/                            43 patches + 2 action files applied to vscode/
  patches/user/                       <- crow's OWN vscode patches go here (applied last)
    00-cli-standalone-cargo-workspace.patch
    01-cli-crow-agent.patch
  src/stable/                         branding resources copied over vscode/ (icons, .desktop…)
  product.json                        deep-merged over vscode/product.json last (wins)
```

## Build

```bash
cd packages/crow-gui
./build.sh                 # desktop app + web server, linux x64
./build.sh --help
```

`build.sh` sources `crow.env`, exports the pipeline's contract
(`SHOULD_BUILD=yes CI_BUILD=no OS_NAME=linux VSCODE_ARCH=x64
VSCODE_QUALITY=stable SHOULD_BUILD_REH_WEB=yes`), then sources
`vscodium/get_repo.sh` (fetch the pinned VS Code) and `vscodium/build.sh`
(prepare → gulp → package → build the Rust CLI).

Flags: `--arch arm64`, `--os osx|windows` (untested), `--no-web`, `--reh`,
`--latest` (newest upstream instead of the pin), `--assets` (roll release
tarballs), `--prepare-only` (fetch + patch + `npm ci`, stop before gulp — the
fast way to check that every patch still applies), `--fresh` (delete
`vscodium/vscode/` and start the checkout over).

Re-running `./build.sh` **resumes**: `prepare_vscode.sh` patches `vscode/` in
place and cannot run twice, so a prepared tree is detected by the
`vscode/.crow-prepared` marker and the run goes straight to gulp. `--fresh` is
the escape hatch when the checkout itself is suspect.

The marker stores `RELEASE_VERSION`, and the resumed run takes the version from
it rather than recomputing — VSCodium derives it as
`<vscode version><day-of-year * 24 + hour>` (`get_repo.sh`), so it changes
every hour and a recomputed one would never match the tree that was prepared.

The resume path skips patch application, so a patch added under
`vscodium/patches/` only reaches an already-prepared tree by hand
(`cd vscodium/vscode && git apply ../patches/user/<name>.patch`) or via
`--fresh`.

The pinned commit is a ~340 MB fetch from GitHub. `build.sh` seeds it from a
local clone instead when one has the commit (`CROW_VSCODE_SRC=<path>` forces
it; by default a sibling `vscode/` checkout in the workspace is used).

Requirements: bash, git, jq, node + npm matching `vscode/.nvmrc`, python3,
libx11 + libxkbfile dev headers, and rustup + cargo for the CLI. (`libsecret`
is *not* needed at this pin — the Rust CLI's keyring uses the pure-Rust
secret-service backend, and openssl comes from `@vscode/openssl-prebuilt`.)
First run is long (npm ci + gulp minify); expect tens of GB of scratch inside
`vscodium/vscode/`.

## What crow changes in the vendored pipeline

`crow-patches/vscodium-pipeline.patch` touches six files:

- **`prepare_vscode.sh`** — the rebrand itself. Upstream VSCodium hardcodes
  `VSCodium`/`codium`/`vscodium.com` literals in the `product.json` `setpath`
  block and in the packaging-metadata `sed`s (only its *patches* are
  `!!APP_NAME!!`-substituted). Those are now driven by `APP_NAME`,
  `BINARY_NAME`, `GLOBAL_DIRNAME`, `ORG_NAME`, `TUNNEL_APP_NAME`, `SITE_URL`,
  `REPO_URL`, `LICENSE_URL`, `REPORT_ISSUE_URL`, `UPDATE_URL` and
  `DARWIN_BUNDLE_IDENTIFIER`. `utils.sh` is sourced before the product.json
  block so those exist. Also: fresh win32 AppIds/CLSIDs (VSCodium's would make
  a Windows crow installer collide with a VSCodium install), and
  `tunnelServerQualities` is set so the Rust CLI resolves `bin/crow-server`
  instead of falling back to `code-server-oss`.
- **`utils.sh`** — defaults for the new URL/identifier vars (VSCodium's own
  values, so the vendored script still behaves like upstream when `crow.env`
  is not sourced).
- **`get_repo.sh`** — `VSCODE_ORIGIN` overrides the vscode remote (local clone).
- **`build.sh`** — skips `prepare_vscode.sh` when `vscode/.crow-prepared`
  matches `RELEASE_VERSION`, so a build can be resumed after a gulp failure
  instead of re-fetching and re-patching from scratch.
- **`build_cli.sh`** — the CLI's update/download endpoints are overridable
  instead of pinned to VSCodium's feeds. (At this VS Code pin they are inert:
  `cli/build.rs` derives every `VSCODE_CLI_*` constant from `product.json`.)
  `mkdir openssl` became `mkdir -p`: the script re-runs on a resumed build and
  `set -e` made the existing directory fatal.
- **`patches/user/00-cli-standalone-cargo-workspace.patch`** (new) — gives
  `vscode/cli/Cargo.toml` and `vscode/build/win32/Cargo.toml` an empty
  `[workspace]` table. This pipeline lives *inside* the crow-cli repo, which has
  a cargo workspace at its root; without it `cargo build` in `cli/` dies with
  "current package believes it's in a workspace when it's not". A standalone
  VSCodium checkout gets that implicitly.
- **`patches/user/01-cli-crow-agent.patch`** (new) — `crow agent` starts the
  crow agent REPL. Upstream's Rust CLI already owns the word `agent` (Copilot
  agent-host management), so that moves to `agent-host` and a new
  `Commands::CrowAgent` execs `crow-cli run -i` with everything after
  `agent` passed through verbatim (`CROW_CLI` overrides the binary). The
  desktop CLI already forwards `agent` to the Rust binary — `agent` is in
  `NATIVE_CLI_COMMANDS` — so `bin/crow agent` works with no JavaScript
  changes beyond the `--help` description. Upstream's manager stays reachable
  as `bin/crow-tunnel agent-host …`.

Resulting `product.json` identity (stable channel):

```
nameShort / nameLong        Crow            applicationName        crow
dataFolderName              .crow           serverApplicationName  crow-server
serverDataFolderName        .crow-server    tunnelApplicationName  crow-tunnel
urlProtocol / linuxIconName crow            darwinBundleIdentifier dev.crow-ai.crow
quality                     stable          updateUrl/downloadUrl  absent (DISABLE_UPDATE=yes)
```

`dataFolderName` is a deliberate divergence: VSCodium stable leaves upstream's
`.vscode-oss`, so crow would otherwise share `~/.vscode-oss` with it. crow's
user data and extensions live in `~/.crow`.

## Not done yet

- **Icons are still VSCodium's.** `vscodium/src/stable/resources/**`,
  `vscodium/icons/**` and `vscodium/resources`-derived web PWA icons
  (`favicon.ico`, `code-192.png`, `code-512.png`) need crow art
  (`docs/crow-logo.svg` in this repo is the source). One more leak to fix in
  the same pass: `src/vs/code/browser/workbench/workbench.html` hardcodes
  `<meta name="apple-mobile-web-app-title" content="Code">`, which is what an
  iOS/Android home-screen install of `crow web` is named. A `patches/user/`
  patch with `content="!!APP_NAME!!"` gets substituted by `apply_patch`.
- **`vscode-acp` has no browser entry point**, so the crow ACP pane is blank in
  the web build until it grows one.
- The VS Code pin is 1.135.0; bumping it means re-running `vendor.sh` and
  fixing patch hunks.
- Windows/macOS packaging is untested; `--assets` skips deb/rpm/snap.

## Naming

`packages/crow-gui` (this directory) is the **IDE build pipeline**.
`crates/crow-gui` is the unrelated **ratatui-over-wgpu renderer** used by
`crow-web`. They share a name and nothing else.
