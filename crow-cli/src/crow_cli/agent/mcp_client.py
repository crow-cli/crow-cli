"""
MCP client setup and tool extraction.

MCP servers are passed by the ACP client in new_session/load_session calls.
We convert ACP MCP server objects to FastMCP clients.
"""

from logging import Logger
from typing import Any

from acp.schema import HttpMcpServer, McpServerStdio, SseMcpServer
from fastmcp import Client as MCPClient
from fastmcp.client.transports import MCPConfigTransport

from crow_cli.agent.configure import Config


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
    builtin_config: dict[str, Any] | None,
    logger: Logger,
) -> MCPClient:
    """
    Create an MCP client from ACP client provided configurations or builtin config.

    Args:
        mcp_servers: List of MCP server configurations from ACP client (can be None or empty)
        cwd: Working directory (passed to MCP tools)
        builtin_config: FastMCP config dict with "mcpServers" key

    Returns:
        FastMCP Client instance (must be used with async with)
    """
    logger.info("create_mcp_client_from_acp called")
    logger.info("  mcp_servers param: %s", mcp_servers)
    logger.info("  builtin_config param: %s", builtin_config)

    # Start with fallback config as base
    config: dict[str, Any] = (
        dict(builtin_config) if builtin_config else {"mcpServers": {}}
    )
    logger.info("  base config after builtin: %s", config)

    # Convert any ACP mcp_servers and merge into config
    if mcp_servers:
        acp_config = acp_to_fastmcp_config(mcp_servers, logger=logger)
        logger.info("  acp_config converted: %s", acp_config)
        config["mcpServers"].update(acp_config["mcpServers"])
        logger.info("  config after merging acp: %s", config)

    # Add cwd to each server config
    for name, server_config in config["mcpServers"].items():
        server_config["cwd"] = cwd
        logger.info("  server '%s' env: %s", name, server_config.get("env"))

    logger.info("  final config (before transport): %s", config)
    if not config.get("mcpServers"):
        raise ValueError("No MCP servers defined in the config")

    logger.info(f"Creating MCP client with {len(config['mcpServers'])} server(s)")
    transport = MCPConfigTransport(config, name_as_prefix=False)
    return config, MCPClient(transport)


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


async def get_tools(mcp_client: MCPClient) -> list[dict[str, Any]]:
    """
    Extract tools from an MCP client.

    Strips the 'crow-mcp_' prefix from tool names to normalize them
    (e.g., 'crow-mcp_read' -> 'read'). This ensures consistent tool
    naming regardless of whether MCP servers are passed from a client
    or loaded from the fallback config.

    Args:
        mcp_client: Connected MCP client

    Returns:
        List of tool definitions in OpenAI format
    """
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
