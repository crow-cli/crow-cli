"""
MCP client setup and tool extraction.

MCP servers are passed by the ACP client in new_session/load_session calls.
We convert ACP MCP server objects to FastMCP clients.
"""

from logging import Logger
from typing import Any

from acp.schema import HttpMcpServer, McpServerStdio, SseMcpServer
from fastmcp import Client as MCPClient


def acp_to_fastmcp_config(
    mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio],
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
    fallback_config: dict[str, Any] | None,
    logger: Logger,
) -> MCPClient:
    """
    Create an MCP client from ACP MCP server configurations or fallback config.

    Args:
        mcp_servers: List of MCP server configurations from ACP client (can be None or empty)
        cwd: Working directory (passed to MCP tools)
        fallback_config: FastMCP config dict with "mcpServers" key

    Returns:
        FastMCP Client instance (must be used with async with)
    """
    # Start with fallback config as base
    config: dict[str, Any] = (
        dict(fallback_config) if fallback_config else {"mcpServers": {}}
    )

    # Convert any ACP mcp_servers and merge into config
    if mcp_servers:
        acp_config = acp_to_fastmcp_config(mcp_servers)
        config["mcpServers"].update(acp_config["mcpServers"])

    # Add cwd to each server config
    for server_config in config["mcpServers"].values():
        server_config["cwd"] = cwd

    logger.info("  final config: %s", config)
    if not config.get("mcpServers"):
        raise ValueError("No MCP servers defined in the config")

    logger.info(f"Creating MCP client with {len(config['mcpServers'])} server(s)")
    return MCPClient(config)


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
