"""
MCP client setup and tool extraction.

MCP servers are passed by the ACP client in new_session/load_session calls —
the CLIENT owns tool supply; the agent has no builtin fallback. We convert
ACP MCP server objects to FastMCP clients (and back, for the client side).
"""

from logging import Logger
from typing import Any

from acp.schema import (
    EnvVariable,
    HttpHeader,
    HttpMcpServer,
    McpServerStdio,
    SseMcpServer,
)
from fastmcp import Client as MCPClient
from fastmcp.client.transports import MCPConfigTransport


def acp_to_fastmcp_config(
    mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio],
    logger: Logger | None = None,
) -> dict[str, Any]:
    """
    Convert ACP mcp_servers to FastMCP configuration dict.

    ACP protocol uses structured types with List[EnvVariable] and List[HttpHeader].
    FastMCP expects dict[str, str] for environment variables and headers.

    Args:
        mcp_servers: List of MCP server configurations from ACP client

    Returns:
        FastMCP configuration dict with "mcpServers" key
    """
    config: dict[str, Any] = {"mcpServers": {}}

    for server in mcp_servers:
        if isinstance(server, McpServerStdio):
            # Convert List[EnvVariable] to dict[str, str]
            env_dict = {e.name: e.value for e in server.env}
            if logger:
                logger.info("  acp_to_fastmcp_config: server '%s' env_dict=%s", server.name, env_dict)

            config["mcpServers"][server.name] = {
                "transport": "stdio",
                "command": server.command,
                "args": server.args,
                "env": env_dict,
            }

        elif isinstance(server, HttpMcpServer):
            # Convert List[HttpHeader] to dict[str, str]
            headers_dict = {h.name: h.value for h in server.headers}

            config["mcpServers"][server.name] = {
                "transport": "http",
                "url": server.url,
                "headers": headers_dict,
            }

        elif isinstance(server, SseMcpServer):
            # Convert List[HttpHeader] to dict[str, str]
            headers_dict = {h.name: h.value for h in server.headers}

            config["mcpServers"][server.name] = {
                "transport": "sse",
                "url": server.url,
                "headers": headers_dict,
            }
    return config


def create_mcp_client_from_acp(
    mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None,
    cwd: str,
    logger: Logger,
) -> tuple[dict[str, Any], MCPClient | None]:
    """
    Create an MCP client from the servers the ACP client passed in.

    The agent has NO builtin fallback — tool supply is owned by the client
    (new_session/load_session mcpServers). An empty/missing list means the
    session runs with zero tools.

    Args:
        mcp_servers: MCP server configurations from the ACP client
        cwd: Working directory (passed to MCP tools)

    Returns:
        (config dict, MCPClient | None) — client is None for zero servers.
    """
    logger.info("create_mcp_client_from_acp: mcp_servers from client: %s", mcp_servers)

    config: dict[str, Any] = {"mcpServers": {}}
    if mcp_servers:
        config = acp_to_fastmcp_config(mcp_servers, logger=logger)

    for server_config in config["mcpServers"].values():
        server_config["cwd"] = cwd

    if not config.get("mcpServers"):
        logger.info("create_mcp_client_from_acp: no MCP servers -> zero tools")
        return config, None

    logger.info("Creating MCP client with %d server(s)", len(config["mcpServers"]))
    transport = MCPConfigTransport(config, name_as_prefix=False)
    return config, MCPClient(transport)


def fastmcp_config_to_acp_servers(
    mcp_servers: dict[str, Any] | None,
) -> list[McpServerStdio | HttpMcpServer | SseMcpServer]:
    """
    Convert a FastMCP-format mcpServers dict (config.yaml shape) into ACP MCP
    server objects. Inverse of acp_to_fastmcp_config — used by the client to
    hand its MCP configuration to the agent over ACP.
    """
    servers: list[McpServerStdio | HttpMcpServer | SseMcpServer] = []
    for name, cfg in (mcp_servers or {}).items():
        transport = cfg.get("transport", "stdio")
        if transport == "stdio":
            servers.append(
                McpServerStdio(
                    name=name,
                    command=cfg["command"],
                    args=list(cfg.get("args") or []),
                    env=[
                        EnvVariable(name=k, value=str(v))
                        for k, v in (cfg.get("env") or {}).items()
                    ],
                )
            )
        elif transport in ("http", "sse"):
            headers = [
                HttpHeader(name=k, value=str(v))
                for k, v in (cfg.get("headers") or {}).items()
            ]
            cls = HttpMcpServer if transport == "http" else SseMcpServer
            servers.append(cls(name=name, url=cfg["url"], headers=headers, type=transport))
    return servers


def create_mcp_client_from_config(config: dict[str, Any]) -> MCPClient:
    """
    Create an MCP client from a config dict (FastMCP format).

    This is a convenience function for using MCP directly in Python scripts.

    Args:
        config: MCP configuration dict in FastMCP format

    Returns:
        FastMCP Client instance (must be used with async with)
    """
    return MCPClient(config)


async def get_tools(mcp_client: MCPClient | None) -> list[dict[str, Any]]:
    """
    Extract tools from an MCP client.

    Args:
        mcp_client: Connected MCP client (None -> zero tools)

    Returns:
        List of tool definitions in OpenAI format
    """
    if mcp_client is None:
        return []
    tools_result = await mcp_client.list_tools()
    tools = []
    for t in tools_result:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": t.inputSchema,
                },
            }
        )

    return tools


# Legacy function for backwards compatibility
def setup_mcp_client(mcp_path: str = "search.py") -> MCPClient:
    """
    Setup MCP client (legacy compatibility).

    DEPRECATED: Use create_mcp_client_from_acp instead.
    """
    return MCPClient(mcp_path)
