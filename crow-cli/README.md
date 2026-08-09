# crow-cli

<p>
  <a href="https://pypi.org/project/crow-cli/"><img src="https://img.shields.io/pypi/v/crow-cli" alt="PyPI version"></a>
  <a href="https://pypi.org/project/crow-cli/"><img src="https://img.shields.io/pypi/pyversions/crow-cli" alt="Python versions"></a>
  <a href="#license"><img src="https://img.shields.io/pypi/l/crow-cli" alt="License"></a>
</p>

[Documentation](https://crow-ai.dev)

`crow-cli` is an [Agent Client Protocol (ACP)](https://agentclientprotocol.com/) coding agent that runs in your terminal and inside ACP-compatible editors. It reads and edits code, runs shell commands, searches the web, and remembers your work across sessions.

Most agent toolkits treat persistence as an afterthought. crow-cli treats it as the point: every session lives in a dedicated memory service ([crow-memory](#crow-memory--persistence--memory-api)) built on [LanceDB](https://lancedb.github.io/lancedb/) with ColBERT and ColPali embeddings, so agents recall past conversations semantically and can delegate work to one another. Sessions get memorable coolname ids (like `taupe-squirrel-of-splendid-potency`) you can resume or read from any other agent.

## Requirements

- Python 3.14+, managed with [uv](https://docs.astral.sh/uv/)
- Docker, for the crow-memory and SearXNG services
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
uv tool install crow-cli --python 3.14      # or run without installing: uvx crow-cli --help
```

Initialize your configuration and start the backing services:

```bash
crow-cli init                          # scaffolds ~/.agents/crow (config.yaml, .env, docker-compose)
cd ~/.agents/crow && docker compose up -d     # starts crow-memory + SearXNG
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

crow-cli is a monorepo. The pieces:

### crow-cli — the agent

The ACP-native agent: a streaming ReAct loop with tool calling, cancellation, conversation compaction, and multimodal input. Provider and model configuration lives in `~/.agents/crow/config.yaml`.

### crow-memory — persistence + memory API

A standalone service — a LanceDB store with ColBERT (text) and ColPali (image) multivector embeddings — that the agent talks to over HTTP. It backs both session persistence and a semantic memory API, exposed to agents as three tools:

- `list_sessions()` — sessions ordered by recent activity (who's working on what)
- `query_memory(query)` — find which session discussed something, across all sessions
- `query_session(session_id)` — read or search within one session (spans all of that session's agents)

This is what makes multi-agent delegation work: launch a worker, then read its thoughts from any other agent. Today crow-memory runs as a Docker container the agent connects to; longer-term it moves toward an always-on daemon, in line with the ACP v2 direction.

### crow-mcp — the tool server

The built-in [MCP](https://modelcontextprotocol.io/) server providing the agent's tools:

| Tool | What it does |
|------|--------------|
| `read` / `write` / `edit` | File access — `edit` does precise, fuzzy-matched string replacement |
| `terminal` | Run shell commands in the workspace |
| `web_search` / `web_fetch` | Search the web (via SearXNG) and fetch pages as markdown |
| `capture_webcam` / `read_image_file` | Vision input |
| `list_sessions` / `query_memory` / `query_session` | Memory (see above) |

**Extensible by design:** register any MCP server in `~/.agents/crow/config.yaml` and its tools appear alongside these automatically.

> ⚠️ **Tool names are not namespaced.** crow-mcp registers its tools as `read`, `edit`, `terminal`, … — not `crow-mcp_read`. When you add your own MCP servers, watch for name collisions.

### SearXNG — web search

crow-cli ships a maintained SearXNG configuration (stored as JSON so the agent can drive it over MCP) so web search works out of the box, without hand-editing SearXNG settings.

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
uv sync --project crow-cli
```

Run the unit tests — fast and hermetic, no services required (tests that touch sessions use an in-memory fake of the memory service):

```bash
uv run --project crow-cli pytest crow-cli/tests/unit
```

The persistence layer itself is tested in `crow-memory`. Integration and end-to-end tiers are opt-in:

```bash
uv run --project crow-cli pytest crow-cli/tests --run-integration   # spawn the agent
uv run --project crow-cli pytest crow-cli/tests --run-e2e           # live LLM calls (costs $)
```

## Project layout

```
crow-cli/               the agent — ACP server, ReAct loop, CLI
crow-mcp/               built-in MCP tool server
crow-memory/            persistence + memory service (LanceDB, ColBERT/ColPali)
crow-task-mcp/          task-list MCP server for delegation (being reworked)
crow-orchestrator-mcp/  orchestration MCP server for delegation (being reworked)
```

## License

MIT
