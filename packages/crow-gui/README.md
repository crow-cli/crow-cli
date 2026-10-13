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
bundle-exts.sh                        sync ./bundled-exts.json into the packaged trees
bundled-exts.json                     the Jupyter + Python stack crow ships as built-ins
vendor.sh                             re-create vscodium/ from upstream + crow's patch
art/                                  crow brand art (the crow disc + vector)
make_icons.py                         regenerate every shipped icon from art/
crow-patches/vscodium-pipeline.patch  crow's modifications to the vendored scripts
vscodium/                             the vendored pipeline (see its own README/docs)
  prepare_vscode.sh                   product.json rewrite + patch application + npm ci
  patches/                            43 patches + 2 action files applied to vscode/
  patches/user/                       <- crow's OWN vscode patches go here (applied last)
    00-cli-standalone-cargo-workspace.patch
    01-cli-crow-agent.patch
    02-web-workbench-title.patch
    03-deb-host-shlibdeps.patch
    04-deb-chrome-sandbox-setuid.patch
    05-getting-started-tagline.patch
    06-no-default-chat-agent.patch
    07-self-hosted-webview.patch
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
tarballs), `--deb` (build `vscodium/assets/crow_<version>_amd64.deb`),
`--prepare-only` (fetch + patch + `npm ci`, stop before gulp — the fast way to
check that every patch still applies), `--fresh` (delete `vscodium/vscode/` and
start the checkout over).

Re-running `./build.sh` **resumes**: `prepare_vscode.sh` patches `vscode/` in
place and cannot run twice, so a prepared tree is detected by the
`vscode/.crow-prepared` marker and the run goes straight to gulp. `--fresh` is
the escape hatch when the checkout itself is suspect.

The marker stores `RELEASE_VERSION`, and the resumed run takes the version from
it rather than recomputing — VSCodium derives it as
`<vscode version><day-of-year * 24 + hour>` (`get_repo.sh`), so it changes
every hour and a recomputed one would never match the tree that was prepared.

`crow --version` prints a second hash that is *not* the git commit: VSCodium's
`version.sh` sets `BUILD_SOURCEVERSION` to `sha1sum` of `RELEASE_VERSION`, and
gulp writes that into `product.json` as `commit`. It therefore changes whenever
the hour changes, and `crow tunnel --version` reporting "(commit unknown)" is
upstream behaviour (`VSCODE_CLI_COMMIT` is an `option_env!` nothing sets).

The resume path skips patch application, so a patch added under
`vscodium/patches/` only reaches an already-prepared tree by hand
(`cd vscodium/vscode && git apply ../patches/user/<name>.patch`) or via
`--fresh`.

The pinned commit is a ~340 MB fetch from GitHub. `build.sh` seeds it from a
local clone instead when one has the commit (`CROW_VSCODE_SRC=<path>` forces
it; by default a sibling `vscode/` checkout in the workspace is used).

### The .deb

```bash
./build.sh --deb         # → vscodium/assets/crow_<version>_amd64.deb
sudo dpkg -i vscodium/assets/crow_*.deb
```

On Linux the .deb is the install that actually works. Chromium only accepts a
setuid sandbox helper that is **root-owned mode 4755**; a build unpacked into
`~/.local/share/crow/ide` has `chrome-sandbox` owned by the user, Electron
FATALs in `setuid_sandbox_host.cc`, and because `cli.js` detaches the main
process with stdio ignored the app exits 0 and nothing appears. The userns
fallback is closed too on Ubuntu 24.04+ (`kernel.apparmor_restrict_unprivileged_userns=1`).
`dpkg-deb` runs under `fakeroot`, so the archive carries root:root ownership
and `build-deb` chmods the helper 4755 (`patches/user/04`). `--deb` needs
`fakeroot` and `dpkg-dev` (`dpkg-shlibdeps` computes `Depends` —
`patches/user/03`).

`crow-cli install crow`'s shim prefers `/usr/share/crow` over
`~/.local/share/crow/ide` when the package is installed, so `crow` keeps
meaning the working one.

### Bundled extensions

Built-in extensions are scanned from a tree's extension dir at startup
(`VSCode-linux-<arch>/resources/app/extensions/`, `extensions/` in the reh-web
and reh trees), so anything copied there ships with `install crow` and with the
deb — no marketplace install, no first-run network. `build.sh` fills them in
after gulp and before `--deb`:

- **crow-acp** — crow's own chat extension, built from `packages/vscode-acp`
  (bun + vite) and copied in as `crow-acp`. Needs `bun`.
- **the Jupyter + Python stack** — `./bundle-exts.sh` reads
  `./bundled-exts.json` (pinned versions of `ms-toolsai.jupyter`,
  `ms-python.python`, `ms-python.debugpy` and the rest of their extension
  packs), downloads each vsix from Open VSX into `.build/exts/` (cached, so only
  a version bump needs the network), unpacks the vsix's `extension/` payload and
  syncs it into every packaged tree. This is what gives a notebook its kernel
  picker and the status bar its interpreter picker, in the desktop app and in
  `crow serve-web` alike. `ms-python.vscode-pylance` stays out: Microsoft-licensed and
  not on Open VSX. `./bundle-exts.sh [os] [arch]` re-syncs without a rebuild.
  Needs `curl` + `unzip`.

Requirements: bash, git, jq, curl, unzip, node + npm matching `vscode/.nvmrc`, python3,
libx11 + libxkbfile dev headers, and rustup + cargo for the CLI. (`libsecret`
is *not* needed at this pin — the Rust CLI's keyring uses the pure-Rust
secret-service backend, and openssl comes from `@vscode/openssl-prebuilt`.)
First run is long (npm ci + gulp minify); expect tens of GB of scratch inside
`vscodium/vscode/`.

## What crow changes in the vendored pipeline

`crow-patches/vscodium-pipeline.patch` carries crow's changes to the vendored
pipeline — the scripts below, the icons under `src/stable/resources/`, and the
user patches that reach `vscode/` itself:

- **`prepare_vscode.sh`** — the rebrand itself. Upstream VSCodium hardcodes
  `VSCodium`/`codium`/`vscodium.com` literals in the `product.json` `setpath`
  block and in the packaging-metadata `sed`s (only its *patches* are
  `!!APP_NAME!!`-substituted). Those are now driven by `APP_NAME`,
  `BINARY_NAME`, `GLOBAL_DIRNAME`, `ORG_NAME`, `TUNNEL_APP_NAME`, `SITE_URL`,
  `REPO_URL`, `LICENSE_URL`, `REPORT_ISSUE_URL`, `UPDATE_URL` and
  `DARWIN_BUNDLE_IDENTIFIER`. `utils.sh` is sourced before the product.json
  block so those exist. It also strips the Microsoft help/telemetry endpoints
  VSCodium leaves in `product.json`: `documentationUrl`, `releaseNotesUrl` and
  `requestFeatureUrl` point at crow, while `tipsAndTricksUrl`,
  `introductoryVideosUrl`, `twitterUrl`, the three `keyboardShortcutsUrl*` PDF
  links, `checksumFailMoreInfoUrl`, `voiceWsUrl` and `defaultChatAgent` (the
  Copilot chat onboarding) are deleted — the Help menu hides an entry whose URL
  is absent. Also: fresh win32 AppIds/CLSIDs (VSCodium's would make
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
  crow agent TUI: the `crow-agent` binary this repo builds from
  `crates/crow-client` (`crow-cli install crow` builds and installs it to
  `~/.local/bin`). Upstream's Rust CLI already owns the word `agent` (Copilot
  agent-host management), so that moves to `agent-host` and a new
  `Commands::CrowAgent` execs `crow-agent` with everything after `agent`
  passed through verbatim (`CROW_AGENT_BIN` overrides the binary). The
  desktop CLI already forwards `agent` to the Rust binary — `agent` is in
  `NATIVE_CLI_COMMANDS` — so `bin/crow agent` works with no JavaScript
  changes beyond the `--help` description. Upstream's manager stays reachable
  as `bin/crow-tunnel agent-host …`.
- **`patches/user/02-web-workbench-title.patch`** (new) — the web workbench's
  `apple-mobile-web-app-title` meta tag says `Code`; see *Icons* below.
- **`patches/user/03-deb-host-shlibdeps.patch`** (new) — `build-deb` computes
  `Depends` with the host's `dpkg-shlibdeps` instead of downloading chromium's
  vendored copy of the script. That copy (fetched at the `cgmanifest.json`
  chromium pin, and even at chromium `main`) predates dpkg 1.23's
  `Dpkg::Shlibs` and dies with `Can't use an undefined value as a HASH
  reference at Dpkg/Shlibs/SymbolFile.pm`, so no .deb could be built on a
  modern host. The host tool needs `dpkg-dev` and drops chromium's
  `--ignore-weak-undefined` flag, which upstream's `dpkg-shlibdeps` does not
  have.
- **`patches/user/04-deb-chrome-sandbox-setuid.patch`** (new) — `build-deb`
  chmods `chrome-sandbox` 4755 before `fakeroot dpkg-deb`, mirroring the rpm
  spec's `%attr(4755, root, root)`. See *The .deb* above.
- **`patches/user/05-getting-started-tagline.patch`** (new) — the Welcome
  page's subtitle is VS Code's hardcoded "Editing evolved"; crow's is
  "Code editing. Redefined." (the tagline the deb/appdata descriptions use).
- **`patches/user/06-no-default-chat-agent.patch`** (new) — VS Code 1.135's
  `DefaultAccountService` and the extension gallery dereference
  `productService.defaultChatAgent` without a guard, so a product.json *without*
  it — crow deletes it in the branding sweep, and VSCodium-style products never
  had it — crashes the workbench during startup with `Cannot read properties of
  undefined (reading 'chatExtensionId')`: a blank page in `crow serve-web`, a dead
  window on the desktop. The patch makes the five unguarded reads tolerate an
  absent agent; every other read site already uses `?.` or a truthiness check.
- **`patches/user/07-self-hosted-webview.patch`** (new) — upstream serves the
  webview bootstrap page from `{{uuid}}.vscode-cdn.net` (an https Microsoft CDN
  origin baked into the compiled workbench product blob), so on a self-hosted
  plain-http server every webview fetch — notebook output renderers included —
  dies as mixed content (`net::ERR_FAILED`, "error loading dynamically imported
  module"). Port of code-server's `webview.diff`: the web client server hands the
  workbench a same-origin `webviewEndpoint`, the browser environment service
  resolves it against `window.location`, and the webview pre page skips the
  uuid-subdomain `parentOriginHash` check when parent and webview share a host
  (inline-script CSP sha256 in the meta tag refreshed to match). This is what
  makes Jupyter cell outputs render in `crow serve-web`.

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

## Icons

`art/` holds the brand art: `crow-logo.png` (the white crow on the `#6553ff`
disc, transparent corners) and `crow-logo.svg` (the same glyph as a transparent
vector).
`make_icons.py` derives every icon the Linux build and the web server consume
and writes them into `vscodium/src/stable/resources/`:

| output | used by |
| --- | --- |
| `linux/code.png` (1024²) | the app's window/taskbar icon, deb/rpm/snap packaging, `crow.desktop` |
| `linux/code.svg` | shipped alongside; the vector on its own background disc |
| `linux/rpm/code.xpm` | the rpm spec's icon |
| `server/code-192.png`, `server/code-512.png` | the web workbench's PWA manifest + apple-touch-icon |
| `server/favicon.ico` (16–256) | the browser tab |

VSCodium's own generator (`icons/build_icons.sh`) is left alone: it needs
rsvg-convert/imagemagick/icns tools and downloads VSCodium art from the
network, and crow only builds Linux. Edit the art, run
`uv --project <crow-cli> run python make_icons.py`, commit art/ and the
generated files, then rebuild — the icons are copied into the checkout by
`prepare_vscode.sh`, so an already-prepared tree needs `--fresh` (or a manual
copy) to pick them up.

The last hardcoded brand string in the web UI —
`workbench.html`'s `<meta name="apple-mobile-web-app-title" content="Code">`,
the name an iOS/Android home-screen install of `crow serve-web` gets — is replaced by
`patches/user/02-web-workbench-title.patch` with `content="!!APP_NAME!!"`,
which `apply_patch` substitutes from `crow.env` at apply time.

## Not done yet

- **Darwin/Windows icons are still VSCodium's** (`resources/darwin/*.icns`,
  `resources/win32/*.ico`). crow builds Linux only; regenerating them needs
  the icns/ico toolchain VSCodium's `icons/build_icons.sh` uses.
- **`vscode-acp` has no browser entry point**, so the crow ACP pane is blank in
  the web build until it grows one.
- The VS Code pin is 1.135.0; bumping it means re-running `vendor.sh` and
  fixing patch hunks.
- Windows/macOS packaging is untested. The deb builds (`--deb`); rpm and snap
  do not — `--assets` still skips all three.

## Naming

`packages/crow-gui` (this directory) is the **IDE build pipeline**, and the only
`crow-gui` left. A `crates/crow-gui` (ratatui-over-wgpu renderer) and a
`crates/crow-web` (the browser client's state server) used to share the name;
both are deleted. `/usr/bin/crow-web` from the .deb is neither — that is the
IDE's own `reh-web` server, the one `crow serve-web` starts.
