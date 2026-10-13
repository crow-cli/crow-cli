<p align="center">
    <img src="https://github.com/crow-cli/crow-cli/blob/main/docs/img/crow-logo-crop.png?raw=true" alt="crow logo" width=500/>
</p>

# 🐦‍⬛ Crow

<p>
  <a href="https://pypi.org/project/crow-cli/"><img src="https://img.shields.io/pypi/v/crow-cli" alt="PyPI version"></a>
  <a href="https://pypi.org/project/crow-cli/"><img src="https://img.shields.io/pypi/pyversions/crow-cli" alt="Python versions"></a>
  <a href="#license"><img src="https://img.shields.io/pypi/l/crow-cli" alt="License"></a>
</p>

[Documentation](https://crow-ai.dev)

`crow-cli` is an [Agent Client Protocol (ACP)](https://agentclientprotocol.com/) coding agent: a streaming ReAct loop that reads and edits code, runs shells, searches the web and sees images — plus a set of first-party clients (terminal, TUI, IDE, browser) that all drive the same agent over the same wire.

Two ideas hold the whole thing together.

**Persistence is the point.** Every session lives in a SQL database (`~/.agents/crow/crow.db` — sqlite by default, PostgreSQL when you want one store shared across machines) with full-text search over every message. Agents recall past conversations, read each other's sessions and delegate work to one another through that store; there is no bespoke agent-to-agent protocol, just a shared database and a read query. Images are content-addressed files beside the database, hydrated to base64 only when they are actually sent to the LLM. Sessions get memorable coolname ids (`taupe-squirrel-of-splendid-potency`) you can resume, fork, or read from any other agent.

**The client owns the tools.** The agent has *no* builtin tool supply. Whatever MCP servers the client hands it at `session/new` are exactly the tools that session gets — see [Tools](#tools-the-client-owns-the-supply). crow's own clients pass crow's own MCP server, which is why a fresh install works; a third-party client passes its own.

## Requirements

The agent:

- Python 3.13+, managed with [uv](https://docs.astral.sh/uv/)
- Docker, for the SearXNG service that backs web search
- An API key for an OpenAI-compatible LLM provider (OpenRouter, OpenAI, your own endpoint, …)

The clients, if you want to build them:

- Rust (`rustup` + `cargo`) for the `crow-agent` TUI
- node matching `packages/crow-gui/vscodium/.nvmrc` (24.x), `npm`, `bun`, `jq`, `curl`, `unzip`, the libx11/libxkbfile/libsecret headers, and `fakeroot` + `dpkg-dev` for the `.deb` — all of it for the IDE build, which is a from-source VS Code

| Platform | Notes |
|----------|-------|
| Linux    | glibc 2.35+ (Ubuntu 22.04+, Debian 12+, or equivalent); the IDE build and installer are Linux-only today |
| macOS    | 13+ (Ventura), Intel and Apple Silicon |
| Windows  | 10+ (64-bit); WSL2 recommended |

## Setup

```bash
uv tool install crow-cli --python 3.13     # from PyPI
```

…or from a clone, which you want anyway if you mean to build the IDE or the Rust clients — both build from the tree they sit in:

```bash
git clone https://github.com/crow-cli/crow-cli.git
cd crow-cli
uv tool install . --python 3.13      # or run without installing: uvx --from . crow-cli --help
```

Then configure it and start the backing services:

```bash
crow-cli init                                 # wizard: provider, model, secrets, services
cd ~/.agents/crow && docker compose up -d     # starts SearXNG (written by init, not started by it)
```

`crow-cli init` walks you through provider and model selection and writes:

| Path | What it is |
|------|------------|
| `~/.agents/crow/config.yaml` | providers, models, `mcpServers`, `agent_servers`, `db_uri` |
| `~/.agents/crow/.env` | secrets, referenced from the config as `${VAR}` (chmod 600) |
| `~/.agents/crow/compose.yaml` + `searxng/settings.yml` | the services init offers: SearXNG, PostgreSQL, RustFS |
| `~/.agents/crow/prompts/` | `system_prompt.jinja2` and `execute_prompt.jinja2` — edit them, they are yours |
| `~/.agents/crow/src/` | checkouts init clones and `uv sync`s: `crow-cli` and `crow-cli.github.io` (the website). `--no-source` skips them |
| `~/.agents/skills/crow-cli` | the crow-cli skill, installed globally on purpose: it is the BIOS, so an agent can repair a broken spawn |

**Nothing runs from that checkout implicitly.** What init does with it is write one `agent_servers` entry into `config.yaml` — ordinary config, which you can read, edit or delete:

```yaml
agent_servers:
  crow-cli:
    type: custom
    command: uv
    args: ["--project", "/home/you/.agents/crow/src/crow-cli", "run", "crow-cli", "acp"]
```

A bare `crow-cli run` drives the top entry, so on a fresh init that is the checkout; delete the entry and crow drives its own agent — always the code that is actually running, never a directory it chose for you. (An implicit "re-exec into `~/.agents/crow/src`" override used to exist and is gone: it fought worktrees and project checkouts.) `crow-cli agents` prints what will run.

## Quick start

```bash
# One-shot prompt — prints the response and exits
crow-cli run "explain what this repo does"

# Continue an existing session by id
crow-cli run -s <session-id> "now add tests"

# Send a long, pre-written prompt from a file or stdin
crow-cli run -f delegation.md -s <session-id>
cat prompt.md | crow-cli run -

# Interactive REPL
crow-cli run -i

# Machine-readable: one JSONL event per line (session, thinking, message, tool_call, usage, result, error)
crow-cli run -j "refactor the parser" > run.jsonl

# Run as an ACP agent server (for editors and other clients)
crow-cli acp          # ACP v1, stdio — spawned by a client
crow-cli acp2         # ACP v2, stdio — spawned by a client
crow-cli acp2 --http  # …or one server for every dialling client: ws://127.0.0.1:2771/acp
```

`--http` is the one you leave running in a terminal of its own: a single instance serves the IDE, the browser client and anything else that dials it. See [Clients](#clients) for who starts what.

Which agent runs is config, not code: `crow-cli agents` lists the `agent_servers` entries, `-a NAME` drives one, and a bare `run` drives the top entry (crow's own v2 agent when nothing is configured).

The rest of the CLI is observability into the same store:

| Command | What it does |
|---------|--------------|
| `crow-cli inspect` | session state and messages (`--session <id> --messages`) |
| `crow-cli list-sessions` | every session, most-recently-active first — who's working now |
| `crow-cli query-memory` | BM25 search across all sessions |
| `crow-cli query-session` | read or search one session across all its agents |
| `crow-cli models` / `agents` | what config.yaml offers |
| `crow-cli mcp` / `mcp2` | serve crow's tools to any MCP client |
| `crow-cli timers` | the worker that fires scheduled wakes |
| `crow-cli install crow` | build the IDE `.deb`, `dpkg -i` it, install the agent TUI — from a clone, since that is where the build lives |

## Clients

One agent, several front doors. Every one of them is an ACP client; they differ in where the pixels come from — and in who starts the agent.

Two shapes, and only two:

- **Diallers** — the IDE's chat panel and the browser client. They spawn nothing. In another terminal, run a single instance of the agent and leave it running:

  ```bash
  crow-cli acp2 --http        # one server for every client on this machine: ws://127.0.0.1:2771/acp
  ```

- **Spawners** — `crow-cli run` and `crow-agent`. They start their own agent over stdio (the top `agent_servers` entry, or `--agent`), so they need no server.

| Client | What it is | The agent | Run it |
|--------|-----------|-----------|--------|
| `crow-cli run` | the reference client: one-shot, REPL, JSONL, session forks | spawns its own over stdio | `crow-cli run "…"` |
| `crow-agent` | Rust ratatui TUI (`crates/crow-client`) | spawns its own over stdio — `--agent`, default `crow-cli acp2` | `crow-agent` |
| crow IDE | VS Code built from source by `packages/crow-gui`, with the crow chat extension bundled as a built-in — desktop app and browser server | dials `crowAcp.endpoint`, default `ws://127.0.0.1:2771/acp` | `crow` |
| any ACP client | Zed and friends, over stdio or WebSocket | the client spawns the command you give it | `crow-cli acp` / `acp2` |

**The args, exactly.** `acp --http` serves protocol v1 on **2769**; `acp2 --http` serves v2 on **2771**; `--host` (default `127.0.0.1`) and `--port` move either. One v2 instance is enough for every dialler — the IDE panel's `crowAcp.endpoint` defaults to `ws://127.0.0.1:2771/acp`. A client that only speaks v1 needs `crow-cli acp --http` instead, on 2769.

### `crow-agent` — the terminal client

A ratatui ACP client in `crates/crow-client`. It spawns the agent itself (`--agent`, default `crow-cli acp2`) so there is nothing to start first, and it is a real terminal citizen: markdown rendering, syntax-highlighted diffs, drag-to-select copy, tool calls that expand in place, `!` for a shell line and `/` for commands.

```bash
cargo build --release --bin crow-agent
crow-agent                              # in the current workspace
crow-agent -w ~/src/project --session-id <id>   # resume a durable session
crow-agent --model <name>               # ask the agent for a model (default: $CROW_MODEL)
crow-agent --demo                       # scripted turns, no agent needed
```

### crow — the IDE

`packages/crow-gui` builds crow's IDE ("crowdium") from Microsoft's open-source VS Code using a **vendored copy of VSCodium's build pipeline**, rebranded, with crow's patches in `packages/crow-gui/vscodium/patches/user/`. Two artifacts come out and both are first-class:

| Artifact | What it is | Entry point |
|----------|-----------|-------------|
| `vscodium/VSCode-linux-<arch>/` | the Electron desktop app | `bin/crow` |
| `vscodium/vscode-reh-web-linux-<arch>/` | the browser server (`reh-web`) | `bin/crow-server` |

The chat panel is `packages/vscode-acp` (`crow-acp`), built with bun and copied into every packaged tree as a **built-in** extension alongside the Jupyter + Python stack pinned in `packages/crow-gui/bundled-exts.json` — so notebooks get a kernel picker with no marketplace install.

```bash
uv run crow-cli install crow   # from the clone: builds the .deb, installs it with dpkg, builds the TUI
```

The IDE is a dialler — it does not start the agent. In another terminal, run a single instance and leave it running:

```bash
crow-cli acp2 --http           # ws://127.0.0.1:2771/acp, which is what crowAcp.endpoint already points at
```

Then open whichever front door you want:

```bash
crow                           # the desktop IDE
crow serve-web                 # the same IDE in a browser, through the IDE's own CLI, which prints a tokenised URL
crow agent                     # the crow-agent TUI — the one front door that spawns its own agent
```

The chat panel is a webview that dials the agent directly and spawns nothing: `crowAcp.endpoint` (default `ws://127.0.0.1:2771/acp`, i.e. `acp2 --http`), `crowAcp.protocol` (`1`, `2` or `auto`), `crowAcp.cwd`, and `crowAcp.mcpConfig` — the tool supply it hands over at `session/new`, by default `crow-cli mcp2`. Nothing listening at that endpoint, nothing to chat with.

`serve-web` starts the `reh-web` server that ships **beside** the IDE (`/usr/share/crow/web`, or `$CROW_WEB_DIR`): crow publishes no release tarballs, so there is nothing to download and no update check to fail.

The install **is** the `.deb`, and that is not pedantry: `dpkg -i` is the only route that gets a root-owned `4755 chrome-sandbox`, which Chromium requires — without it the desktop app can die silently on kernels that restrict unprivileged user namespaces (Ubuntu 24.04+). So `install crow` runs the pipeline with `--deb` (it wants `fakeroot` + `dpkg-dev`, and says so *before* a 40-minute build rather than after) and then installs it:

```bash
cd packages/crow-gui && ./build.sh --deb     # what `install crow` runs; ~40 min the first time
sudo dpkg -i vscodium/assets/crow_*.deb      # …and what it runs next
```

A deb that is already built is installed without rebuilding (`--rebuild` forces the pipeline). `--no-deb` is the rootless fallback: it copies the trees to `~/.local/share/crow/{ide,web}` and writes a user-level `.desktop` entry — a build you can run, not an install, with no setuid sandbox. The deb route deletes that user-level entry instead of letting it shadow the package's.

### Any other ACP client

For [Zed](https://zed.dev/), declare the agent *and* its tool supply — Zed forwards `context_servers` to external agents over ACP, and an agent handed nothing runs with zero tools:

```json
{
  "agent_servers": {
    "crow-cli": { "command": "crow-cli", "args": ["acp"] }
  },
  "context_servers": {
    "crow-mcp": { "command": "crow-cli", "args": ["mcp"], "env": {} }
  }
}
```

## Tools: the client owns the supply

This is the part that surprises people, so it is worth stating plainly: **the agent has no builtin MCP servers.** `mcpServers` in `~/.agents/crow/config.yaml` is consumed by the *client* — `crow-cli run` converts it to ACP `mcpServers` and passes it at `session/new`/`load_session`. Empty or absent means the session runs with zero tools. `crow-cli init` writes the entry below, which is the only reason a fresh install has tools at all:

```yaml
mcpServers:
  crow-mcp:
    transport: stdio
    command: crow-cli
    args: [mcp]
```

An `agent_servers` entry may carry its own `mcpServers`, which *replaces* the global supply for that agent only — that is how a v2 agent gets `crow-mcp2` without changing what the v1 sessions on the same box are handed.

One binary serves two tool surfaces:

### `crow-cli mcp` — the flat tool set (ACP v1)

| Tool | What it does |
|------|--------------|
| `read` / `write` / `edit` | File access — `edit` does precise, fuzzy-matched string replacement |
| `terminal` | Run shell commands in the workspace |
| `execute` | The persistent IPython kernel (below) |
| `web_search` / `web_fetch` | Search the web (via SearXNG) and fetch pages as markdown |
| `capture_webcam` / `read_image_file` | Vision input |
| `list_sessions` / `query_memory` / `query_session` | Memory |
| `task` | Launch, re-prompt and cancel subagents |

`--include-tools` narrows it to an allowlist (spawn the server several times to get several servers out of one codebase), `--transport http` serves it as a streamable HTTP service, and `--list-tools` prints the names.

### `crow-cli mcp2` — `execute`, and only `execute` (ACP v2)

The v2 surface is one tool: a **persistent IPython kernel** that survives the whole session. Variables, imports, open handles and cwd carry from one cell to the next, so work is written as successive cells rather than as one-shot shell invocations — and crow's capabilities are ambient inside it, bound by a prelude as lazy facades:

| Subtool | What it does |
|---------|--------------|
| `fs` / `write` / `edit` | File access — read/stat/list, write, and precise edits that return a diff |
| `web` | `search`, `fetch`, `run` (headless browser), `close` |
| `memory` | Read-only SQL over the whole session store |
| `rlm` | Delegate a subtask to another model, blocking |
| `vision` | Bring an image into the conversation |
| `sg` | ast-grep: structural search and rewrite |
| `task` / `task_read` / `task_send` / `task_cancel` | Subagents and their mailboxes (v2 kernels) |
| `goal_start` / `goal_done` / `goal_blocked` / `goal_reset` | The continuation loop that keeps a long sprint running (v2 kernels) |
| `reload` | Re-bind the tool facades in place, without losing kernel state |

`help(tool)` works out of the box on every one of them.

> ⚠️ **Tool names are not namespaced.** `crow-cli mcp` registers `read`, `edit`, `terminal`, … — not `crow_read`. When you add your own MCP servers, watch for collisions.

### Persistence — SQL memory

sqlite by default (single machine, zero setup); point `db_uri` at PostgreSQL for memory shared across machines, so agents on any box see the same sessions, messages and task mailboxes. Search is a real index on both backends — an FTS5 virtual table with bm25 ranking on sqlite. The layer lives in `src/crow_cli/memory` and is tested in `tests/memory/test_store.py`.

### SearXNG — web search

crow-cli ships a maintained SearXNG configuration (stored as Python, so it survives a PyInstaller freeze — sorry) so search works out of the box without hand-editing SearXNG settings. `crow-cli init` writes `compose.yaml` and `searxng/settings.yml`; `docker compose up -d` in `~/.agents/crow` starts it.

### Skills

Agents load reusable skills from `~/.agents/skills/` — each a directory with a `SKILL.md` saying when and how to use it, scanned at session creation and injected into the system prompt. Skill distribution is still being worked out; today skills are local directories.

## Configuration

`~/.agents/crow/config.yaml` holds providers, models, MCP servers and the agent registry; secrets live in `~/.agents/crow/.env` and are interpolated with `${VAR}`.

```yaml
providers:
  openrouter:
    api_key: ${OPENROUTER_API_KEY}
    base_url: https://openrouter.ai/api/v1
models:
  my-model:
    provider: openrouter
    model: anthropic/claude-sonnet-4
agent_servers:
  crow-execute:
    protocol: acp2
    command: uv
    args: ["--project", "~/.agents/crow/src/crow-cli", "run", "crow-cli", "acp2"]
    mcpServers:
      crow-mcp2:
        transport: stdio
        command: crow-cli
        args: [mcp2]
```

The first model is the default; the top `agent_servers` entry is the agent a bare `crow-cli run` drives. Every entry is a command honored exactly as written — crow never substitutes its own agent for a configured one. `protocol` is optional: leave it out and the client asks the agent at `initialize`, then drives whatever it answers, so an entry cannot disagree with its own agent.

## Development

```bash
git clone https://github.com/crow-cli/crow-cli.git
cd crow-cli
uv sync
```

Run the test suite — every tier runs unconditionally (unit + integration + e2e live LLM):

```bash
uv run pytest tests
```

To run a single tier, point pytest at its directory:

```bash
uv run pytest tests/unit          # fast, hermetic
uv run pytest tests/integration   # real sqlite, agent spawn
uv run pytest tests/e2e           # live LLM calls (costs $)
```

The Rust client builds with cargo (`cargo build --release --bin crow-agent`; `crates/crow-client` is the workspace's only member), the chat webview and the extension with bun (`bun install` at the root, then `bun run ext:build`), and the IDE with `packages/crow-gui/build.sh` (`--help` lists its flags; `--prepare-only` stops after fetch + patch + `npm ci`).

## Project layout

```
src/crow_cli/             the agent — ACP v1 + v2 servers, ReAct loop, CLI
src/crow_cli/agent/       the v1 agent: session, tools, MCP client, memory
src/crow_cli/agent2/      the v2 agent: the execute-kernel driver
src/crow_cli/client/      the v1 client (`crow-cli run`)
src/crow_cli/client2/     the v2 client
src/crow_cli/mcp/         the flat MCP tool server (`crow-cli mcp`)
src/crow_cli/mcp2/        the execute-only MCP server (`crow-cli mcp2`)
src/crow_cli/tools/       the in-kernel subtools the prelude binds
src/crow_cli/config/      config loading, defaults, overrides (shared by every layer)
src/crow_cli/memory/      shared SQL persistence (sqlite default, PostgreSQL supported)

crates/crow-client/       crow-agent — the ratatui ACP client TUI

packages/chat/            the chat webview source (@crow/chat) — the extension's UI
packages/aui/             vendored assistant-ui, as built dist
packages/vscode-acp/      crow-acp — the chat extension bundled into the IDE
packages/crow-gui/        the IDE build pipeline (vendored VSCodium + crow's patches)
```

## License

MIT — see [LICENSE.md](./LICENSE.md).
