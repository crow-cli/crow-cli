# crow-mcp

<p>
  <a href="https://pypi.org/project/crow-mcp/"><img src="https://img.shields.io/pypi/v/crow-mcp" alt="PyPI version"></a>
  <a href="https://pypi.org/project/crow-mcp/"><img src="https://img.shields.io/pypi/pyversions/crow-mcp" alt="Python versions"></a>
  <a href="#license"><img src="https://img.shields.io/pypi/l/crow-mcp" alt="License"></a>
</p>

The built-in [MCP](https://modelcontextprotocol.io/) tool server for [crow-cli](../crow-cli/README.md). Provides filesystem, terminal, web, vision, and memory tools over stdio.

## Tools

| Tool | Module | What it does |
|------|--------|--------------|
| `read` | read | Read files with line numbers |
| `write` | write | Create or overwrite files |
| `edit` | editor | Precise string replacement with fuzzy matching |
| `terminal` | terminal | Shell commands in a persistent PTY session |
| `web_search` | web_search | Search the web via SearXNG (parallel queries) |
| `web_fetch` | web_fetch | Fetch a URL and extract content as markdown |
| `capture_webcam` | vision | Capture a frame from a webcam |
| `read_image_file` | vision | Read an image file for vision analysis |
| `list_sessions` | memory | List agent sessions by recent activity |
| `query_memory` | memory | Semantic search across all sessions |
| `query_session` | memory | Read or search within one session |

> ⚠️ Tool names are **not namespaced** — `read`, not `crow-mcp_read`. Watch for collisions when registering additional MCP servers.

## Usage

crow-mcp is started automatically by crow-cli as a child process. You don't normally run it directly.

To use it standalone:

```bash
# stdio
uv --project /path/to/crow-mcp run crow-mcp
# http in the background/separate service
uv --project /path/to/crow-mcp run crow-mcp --transport http --port 2770
```

Or register it in any MCP client config:

```json
// stdio
{
  "mcpServers": {
    "crow-mcp": {
      "transport": "stdio",
      "command": "uv",
      "args": ["--project", "/path/to/crow-mcp", "run", "crow-mcp"]
    }
  }
}
// http
{
  "mcpServers": {
    "crow-mcp": {
      "transport": "http",
      "url": "http://127.0.0.1:2770/mcp"
    }
  }
}
```

## Memory tools

The memory tools (`list_sessions`, `query_memory`, `query_session`) read the shared database through the `crow-memory` package with a read-only engine — BM25 keyword search via FTS5, no service involved. The db resolves from `CROW_DB_URI` (URI) → `CROW_MEMORY_DB` (path) → `db_uri:`/`memory_path:` in `~/.agents/crow/config.yaml` → the default `~/.agents/crow/crow.db`.

## Development

```bash
uv sync --project crow-mcp
uv run --project crow-mcp pytest crow-mcp/tests
```

## License

MIT
