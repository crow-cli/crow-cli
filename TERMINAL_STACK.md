# Terminal Stack — crow spaceship edition

The dev terminal stack on this box, documented 2026-08-29. Everything is
installed without sudo (user-local), and rio is built from source — which
is the whole point, see below.

## Rio terminal (built from source — `~/src/rio`, v0.5.26)

Installed at `~/.cargo/bin/rio`. Config: `~/.config/rio/config.toml`
(shades-of-dracula crow flavor — chrome accents are Dracula purple
`#BD93F9`, matching `src/crow_cli/tui/themes.py`; ANSI yellow stays
yellow for program output). Font: DejaVu Sans Mono 12px, deliberately
NOT a Nerd Font (won the bake-off against Lilex; tested against Zed).
All prompt/tool symbols in this stack are DejaVu-safe.

### What building from source buys

The default Linux build uses the native Vulkan backend. Two cargo
features are off by default and only reachable with a source build
(`frontends/rioterm/Cargo.toml`):

1. **`wgpu` — RetroArch shader filters.** The librashader filter chain
   (https://rioterm.com/docs/features/retroarch-shaders) only runs on
   the wgpu backend. Post-processing for the whole terminal: built-in
   `newpixiecrt`, or any `.slangp` from libretro/slang-shaders (CRT,
   bloom, scanlines — the spaceship-cockpit look).
2. **`audio` — real audio bell** via cpal (`handle_audio_bell` in
   `frontends/rioterm/src/application.rs`).

Also available in config regardless of build: `[renderer] strategy =
"Game"` (continuous game-loop rendering) vs the default event-based.

### Rebuild with shaders enabled

```bash
cd ~/src/rio
cargo install --path frontends/rioterm --features wgpu,audio --force
```

Then in `~/.config/rio/config.toml`:

```toml
[renderer]
backend = "Webgpu"
filters = ["newpixiecrt"]            # or a path to any .slangp
```

Note: wgpu-on-Linux translates through to Vulkan (slightly heavier than
the native backend); filters cost some GPU. If `filters` is set but the
backend is native Vulkan, rio accepts the config and silently skips the
chain — you must set `backend = "Webgpu"`.

Being upstream-from-source also means we can patch rio itself when the
zellji integration (below) needs something rio doesn't do yet.

## Shell stack (bash 5.2 — no shell switch, bash gets the upgrades)

All user-local; `~/.bashrc` is the spaceship (original at `~/.bashrc.bak`).

| Tool | What it does | Lives at |
|---|---|---|
| **starship** | prompt — git/lang/duration, Dracula palette | `~/.local/bin/starship`, config `~/.config/starship.toml` |
| **ble.sh** | readline replacement: syntax highlighting, autosuggestions, menu completion | `~/.local/share/ble-nightly/`, config `~/.blerc` |
| **eza** | ls with git status + tree | `~/.local/bin/eza` |
| **bat** | cat with syntax highlighting | `~/.local/bin/bat` |
| **zoxide** | `z foo` frecency directory jumps (`zi` interactive) | `~/.local/bin/zoxide` |
| **fzf** | Ctrl-R fuzzy history, Ctrl-T files, Alt-C dirs (fd-backed) | `~/.local/bin/fzf` + `~/.local/share/fzf/*.bash` |
| **delta** | git diff pager (wire via `git config --global core.pager delta` when wanted) | `~/.local/bin/delta` |
| **fd / rg** | already present via cargo | `~/.cargo/bin` |
| **hx** | helix editor, `$EDITOR` | system |

Update paths: starship re-runs its installer; ble.sh = re-download the
nightly tarball (`ble.sh/releases/download/nightly/ble-nightly.tar.xz`
→ extract to `~/.local/share`, no gawk/make needed for the prebuilt
tarball); the rest are GitHub-release binaries (x86_64).

### bashrc load order (matters)

1. interactive guard → 2. ble.sh `--attach=none` (first) → 3. history →
4. env (hx, LESS_TERMCAP, GCC_COLORS) → 5. toolchain PATH blocks
(cargo/fnm/bun/juliaup) → 6. aliases (eza/bat/git) → 7. fzf bindings →
8. bash-completion → 9. `starship init` + `zoxide init` → 10.
`ble-attach` (LAST — ble.sh takes over line editing).

## The zellji vision (why this is documented in crow-cli)

Goal: crow-cli grows into the glue of a full terminal IDE, replacing
the pile of bash scripts in https://github.com/josephschmitt/zide
(zellij layouts + `zide-pick` yazi wrapper + `zide-edit` editor
launcher) with Python.

- **zellij** = window/pane manager (the "IDE frame")
- **yazi** = filesystem pane
- **helix** (`hx`) = editor pane
- **crow-cli TUI** = the agent pane AND the orchestrator: spawns the
  layout, routes "open file" events from yazi into helix, drives the
  agent — i.e. `crow-cli ide` instead of `zide` + `zide-pick` +
  `zide-edit`.

Stepping stones: crow-cli already speaks ACP to its own agent and has
a TUI that drives it; the zide behaviors to absorb are (1) layout
launch with working-dir propagation, (2) filepicker → editor IPC
(zide uses zellij's pipe/message), (3) pane auto-resize for the picker.
Rio-from-source is the display layer: if the IDE glue needs something
from the terminal (keycodes, shader states, notifications), we patch
rio rather than work around it.
