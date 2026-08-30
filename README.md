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

`crow-cli` is an [Agent Client Protocol (ACP)](https://agentclientprotocol.com/) coding agent that runs in your terminal and inside ACP-compatible editors. It reads and edits code, runs shell commands, searches the web, and remembers your work across sessions.

Persistence is the point: every session lives in a local sqlite database (`~/.agents/crow/crow.db`) with FTS5 full-text search, so agents recall past conversations and can delegate work to one another. Images are stored as files next to the database and hydrated only when sent to the LLM. Sessions get memorable coolname ids (like `taupe-squirrel-of-splendid-potency`) you can resume or read from any other agent.

## Requirements

- Python 3.14+, managed with [uv](https://docs.astral.sh/uv/)
- Docker, for the SearXNG service
- An API key for an OpenAI-compatible LLM provider (OpenRouter, OpenAI, your own endpoint, …)

| Platform | Notes |
|----------|-------|
| Linux    | glibc 2.35+ (Ubuntu 22.04+, Debian 12+, or equivalent) |
| macOS    | 13+ (Ventura), Intel and Apple Silicon |
| Windows  | 10+ (64-bit); WSL2 recommended |

## Setup

Install the CLI:

```bash
git clone https://github.com/crow-cli/crow-cli.git
cd crow-cli
uv tool install . --python 3.14      # or run without installing: uvx --from . crow-cli --help
```

Initialize your configuration and start the backing services:

```bash
crow-cli init                          # scaffolds ~/.agents/crow (config.yaml, .env, docker-compose)
cd ~/.agents/crow && docker compose up -d     # starts SearXNG
```

`crow-cli init` walks you through provider and model selection and writes your secrets to `~/.agents/crow/.env`, referenced from the config as `${VAR}`.

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

# Run as an ACP agent server (for editors)
crow-cli acp
```

Inspect stored sessions with `crow-cli inspect` (add `--session <id> --messages` to see a session's messages).

## Using crow-cli in your editor

crow-cli speaks ACP, so it works with any ACP-compatible client. For [Zed](https://zed.dev/), add to `~/.config/zed/settings.json`:

```json
{
  "agent_servers": {
    "crow-cli": {
      "type": "custom",
      "command": "crow-cli",
      "args": ["acp"]
    }
  }
}
```

The agent detects client capabilities (terminals, file read/write) and uses the native ACP versions when available, falling back to MCP tools otherwise.

## What's in the box

### The agent

An ACP-native agent: a streaming ReAct loop with tool calling, cancellation, conversation compaction, and multimodal input. Provider and model configuration lives in `~/.agents/crow/config.yaml`.

### Persistence — SQL memory (sqlite or PostgreSQL)
We use SQL for storing agent state.

### Built-in MCP tool server

The bundled [MCP](https://modelcontextprotocol.io/) server (`crow-cli mcp`) providing the agent's tools:

| Tool | What it does |
|------|--------------|
| `read` / `write` / `edit` | File access — `edit` does precise, fuzzy-matched string replacement |
| `terminal` | Run shell commands in the workspace |
| `web_search` / `web_fetch` | Search the web (via SearXNG) and fetch pages as markdown |
| `capture_webcam` / `read_image_file` | Vision input |
| `list_sessions` / `query_memory` / `query_session` | Memory (see above) |

**Extensible by design:** register any MCP server in `~/.agents/crow/config.yaml` and its tools appear alongside these automatically.

> ⚠️ **Tool names are not namespaced.** The built-in server registers its tools as `read`, `edit`, `terminal`, … — not `crow_read`. When you add your own MCP servers, watch for name collisions.

### SearXNG — web search

crow-cli ships a maintained SearXNG configuration (stored as python so the agent works with PyInstaller — sorry) so web search works out of the box, without hand-editing SearXNG settings.

### Skills

Agents load reusable skills from `~/.agents/skills/` — each a directory with a `SKILL.md` describing when and how to use it. Skill distribution is still being worked out; today skills are local directories.

## Configuration

`~/.agents/crow/config.yaml` holds providers, models, and MCP servers; secrets live in `~/.agents/crow/.env` and are interpolated with `${VAR}`.

```yaml
providers:
  openrouter:
    api_key: ${OPENROUTER_API_KEY}
    base_url: https://openrouter.ai/api/v1
models:
  my-model:
    provider: openrouter
    model: anthropic/claude-sonnet-4
```

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

The persistence layer itself lives in `src/crow_cli/memory` and is tested in `tests/memory/test_store.py`. To run a single tier, point pytest at its directory:

```bash
uv run pytest tests/unit          # fast, hermetic
uv run pytest tests/integration   # real sqlite, agent spawn
uv run pytest tests/e2e           # live LLM calls (costs $)
```

## Project layout

```
src/crow_cli/           the agent — ACP server, ReAct loop, CLI
src/crow_cli/config/    config loading, defaults, overrides (shared by every layer)
src/crow_cli/mcp/       built-in MCP tool server (`crow-cli mcp`)
src/crow_cli/memory/    shared SQL persistence (sqlite default, PostgreSQL supported)
```

## License

crow-cli is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0-or-later). See [LICENSE.md](./LICENSE.md).

The interactive TUI in `src/crow_cli/tui/` is derived from
[Toad](https://github.com/batrachianai/toad) by Will McGugan and is likewise
AGPL-3.0 (see `src/crow_cli/tui/NOTICE`).
