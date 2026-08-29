"""MCP servers to hand to agents at session/new and session/load.

Toad ships no tools of its own; agents like crow-cli come up toolless
unless the client supplies MCP servers. This reads the mcpServers dict
straight out of crow-cli's config (~/.agents/crow/config.yaml) and
converts it to ACP wire format — pure passthrough, toad never connects
to these servers itself.

Config shape::

    mcpServers:
      crow-mcp:
        transport: http
        url: "http://localhost:2769/mcp"
      playwright:
        transport: stdio
        command: npx
        args: ["-y", "@playwright/mcp"]
        env: {FOO: bar}
"""

from pathlib import Path

import yaml

from crow_cli.tui.acp import protocol

CROW_CONFIG = Path("~/.agents/crow/config.yaml").expanduser()


def _to_wire(name: str, server: dict) -> protocol.McpServer:
    transport = server.get("transport")
    if transport in ("http", "sse") or "url" in server:
        return {
            "name": name,
            "type": transport if transport in ("http", "sse") else "http",
            "url": server["url"],
            "headers": [
                {"name": k, "value": v} for k, v in server.get("headers", {}).items()
            ],
        }
    env = server.get("env", {})
    return {
        "name": name,
        "command": server["command"],
        "args": server.get("args", []),
        "env": [{"name": k, "value": str(v)} for k, v in env.items()],
    }


def load_mcp_servers() -> list[protocol.McpServer]:
    """Return crow-cli's mcpServers in ACP wire format (empty if absent)."""
    if not CROW_CONFIG.exists():
        return []
    config = yaml.safe_load(CROW_CONFIG.read_text("utf-8")) or {}
    servers = config.get("mcpServers") or {}
    return [_to_wire(name, server) for name, server in servers.items()]
