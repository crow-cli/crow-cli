<p align="center">
    <img src="https://github.com/crow-cli/crow-cli/blob/main/docs/img/crow-logo-crop.png?raw=true" alt="crow logo" width=500/>
</p>

# 🐦‍⬛ Crow

<p>
  <a href="https://pypi.org/project/crow-cli/"><img src="https://img.shields.io/pypi/v/crow-cli" alt="PyPI version"></a>
  <a href="https://pypi.org/project/crow-cli/"><img src="https://img.shields.io/pypi/pyversions/crow-cli" alt="Python versions"></a>
  <a href="#license"><img src="https://img.shields.io/pypi/l/crow-cli" alt="License"></a>
</p>

Monorepo for the Crow coding agent.

Crow is an [ACP](https://agentclientprotocol.com/)-native coding agent that runs in your
terminal and inside ACP-compatible editors. It reads and edits code, runs shell commands,
and searches the web — and it **remembers**: every session is written to a shared memory
service you can query across sessions.

## Packages

| Package | What it is |
|---------|-----------|
| [`crow-cli`](./crow-cli/README.md) | The agent — CLI, ACP server, tool executors, sqlite memory |
| [`crow-mcp`](./crow-mcp/README.md) | MCP toolserver (filesystem, terminal, web search, memory tools) |

## Getting started

Setup and usage live in the [`crow-cli` README](./crow-cli/README.md). In short:

```bash
git clone https://github.com/crow-cli/crow-cli
cd crow-cli/crow-cli
uv sync
uv run crow-cli init

# start the memory service
docker compose up -d

# run the agent
uv run crow-cli run "explain this project"
```

## License

MIT. See [LICENSE.md](./LICENSE.md).


