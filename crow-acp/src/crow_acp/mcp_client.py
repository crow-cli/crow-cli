"""
MCP client setup and tool extraction.

MCP servers are passed by the ACP client in new_session/load_session calls.
We convert ACP MCP server objects to FastMCP clients.
"""

import logging
from typing import Any

from acp.schema import HttpMcpServer, McpServerStdio, SseMcpServer
from fastmcp import Client as MCPClient

logger = logging.getLogger(__name__)


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

    Example:
        >>> from acp.schema import McpServerStdio, EnvVariable
        >>> servers = [
        ...     McpServerStdio(
        ...         name="crow-builtin",
        ...         command="uv",
        ...         args=["--project", ".", "run", "server.py"],
        ...         env=[EnvVariable(name="DEBUG", value="true")]
        ...     )
        ... ]
        >>> config = acp_to_fastmcp_config(servers)
        >>> config["mcpServers"]["crow-builtin"]["command"]
        'uv'
        >>> config["mcpServers"]["crow-builtin"]["env"]["DEBUG"]
        'true'
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

            logger.debug(
                f"Converted stdio MCP server '{server.name}': "
                f"command={server.command}, args={server.args}"
            )

        elif isinstance(server, HttpMcpServer):
            # Convert List[HttpHeader] to dict[str, str]
            headers_dict = {h.name: h.value for h in server.headers}

            config["mcpServers"][server.name] = {
                "transport": "http",
                "url": server.url,
                "headers": headers_dict,
            }

            logger.debug(f"Converted HTTP MCP server '{server.name}': url={server.url}")

        elif isinstance(server, SseMcpServer):
            # Convert List[HttpHeader] to dict[str, str]
            headers_dict = {h.name: h.value for h in server.headers}

            config["mcpServers"][server.name] = {
                "transport": "sse",
                "url": server.url,
                "headers": headers_dict,
            }

            logger.debug(f"Converted SSE MCP server '{server.name}': url={server.url}")

        else:
            logger.warning(f"Unknown MCP server type: {type(server)}, skipping")

    logger.info(f"Converted {len(config['mcpServers'])} MCP servers to FastMCP config")
    return config


async def create_mcp_client_from_acp(
    mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio],
    cwd: str,
    fallback_config: dict[str, Any] | None = None,
) -> MCPClient:
    """
    Create an MCP client from ACP MCP server configurations.

    Args:
        mcp_servers: List of MCP server configurations from ACP client
        fallback_config: FastMCP config dict to use if mcp_servers is empty

    Returns:
        FastMCP Client instance

    Example:
        >>> from acp.schema import McpServerStdio
        >>> servers = [
        ...     McpServerStdio(
        ...         name="crow-builtin",
        ...         command="uv",
        ...         args=["--project", ".", "run", "server.py"],
        ...         env=[]
        ...     )
        ... ]
        >>> client = await create_mcp_client_from_acp(servers)
        >>> async with client:
        ...     tools = await client.list_tools()
    """
    if not mcp_servers:
        if fallback_config is None:
            raise ValueError(
                "No MCP servers provided and no fallback config available. "
                "MCP servers must be provided either via ACP protocol or fallback_config."
            )
        logger.info("No MCP servers provided, using fallback config")
    # So fallback_config exists.
    # We don't know if mcp_servers is an empty list
    logger.info(f"mcp_servers: {mcp_servers}")
    logger.info(f"fallback_config: {fallback_config}")

    # Let's try to use the fallback_config
    config = acp_to_fastmcp_config(mcp_servers)
    logger.info(f"config: {config}")
    config["mcpServers"].update(**fallback_config["mcpServers"])
    for server_name, server_config in config["mcpServers"].items():
        server_config.update(dict(cwd=cwd))
    # Convert ACP format to FastMCP config dict
    #
    # for mcp_server_name, mcp_config in config["mcpServers"].items():
    #     mcp_config[]

    logger.info(f"Creating FastMCP client from {len(mcp_servers)} ACP servers")

    # Create FastMCP client from config
    return MCPClient(config)


def create_mcp_client_from_config(config: dict[str, Any]) -> MCPClient:
    """
    Create an MCP client from a config dict (FastMCP format).

    This is a convenience function for using MCP directly in Python scripts.

    Args:
        config: MCP configuration dict in FastMCP format

    Returns:
        FastMCP Client instance (must be used with async with)

    Example:
        >>> config = {
        ...     "mcpServers": {
        ...         "crow-builtin": {
        ...             "command": "uv",
        ...             "args": ["--project", "crow-mcp-server", "run", "."],
        ...         }
        ...     }
        ... }
        >>> client = create_mcp_client_from_config(config)
        >>> async with client:
        ...     tools = await client.list_tools()
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

    logger.info(f"Retrieved {len(tools)} tools from MCP server")
    return tools


# Legacy function for backwards compatibility
def setup_mcp_client(mcp_path: str = "search.py") -> MCPClient:
    """
    Setup MCP client (legacy compatibility).

    DEPRECATED: Use create_mcp_client_from_acp instead.
    """
    logger.warning("setup_mcp_client is deprecated, use create_mcp_client_from_acp")
    return MCPClient(mcp_path)
