"""MCP ownership inversion: client-side converter + zero-tool agent path."""

import logging

from acp.schema import HttpMcpServer, McpServerStdio, SseMcpServer

from crow_cli.agent.mcp_client import (
    acp_to_fastmcp_config,
    create_mcp_client_from_acp,
    fastmcp_config_to_acp_servers,
    get_tools,
)


async def test_get_tools_none_client_returns_empty():
    assert await get_tools(None) == []


def test_create_mcp_client_no_servers_returns_none_client():
    config, client = create_mcp_client_from_acp(
        None, cwd="/tmp", logger=logging.getLogger("test")
    )
    assert client is None
    assert config == {"mcpServers": {}}

    config, client = create_mcp_client_from_acp(
        [], cwd="/tmp", logger=logging.getLogger("test")
    )
    assert client is None
    assert config == {"mcpServers": {}}


def test_fastmcp_config_to_acp_servers_stdio():
    servers = fastmcp_config_to_acp_servers(
        {
            "crow-mcp": {
                "transport": "stdio",
                "command": "crow-cli",
                "args": ["mcp"],
                "env": {"FOO": "bar"},
            }
        }
    )
    assert len(servers) == 1
    s = servers[0]
    assert isinstance(s, McpServerStdio)
    assert s.name == "crow-mcp"
    assert s.command == "crow-cli"
    assert s.args == ["mcp"]
    assert [(e.name, e.value) for e in s.env] == [("FOO", "bar")]


def test_fastmcp_config_to_acp_servers_http_and_sse():
    servers = fastmcp_config_to_acp_servers(
        {
            "h": {
                "transport": "http",
                "url": "http://localhost:8000/mcp",
                "headers": {"Authorization": "Bearer x"},
            },
            "s": {"transport": "sse", "url": "http://localhost:8001/sse"},
        }
    )
    by_name = {s.name: s for s in servers}
    assert isinstance(by_name["h"], HttpMcpServer)
    assert by_name["h"].url == "http://localhost:8000/mcp"
    assert [(h.name, h.value) for h in by_name["h"].headers] == [
        ("Authorization", "Bearer x")
    ]
    assert isinstance(by_name["s"], SseMcpServer)
    assert by_name["s"].url == "http://localhost:8001/sse"
    assert by_name["s"].headers == []


def test_fastmcp_config_to_acp_servers_empty():
    assert fastmcp_config_to_acp_servers(None) == []
    assert fastmcp_config_to_acp_servers({}) == []


def test_stdio_defaults_transport():
    # transport key omitted -> stdio (FastMCP default)
    servers = fastmcp_config_to_acp_servers(
        {"bare": {"command": "echo", "args": []}}
    )
    assert isinstance(servers[0], McpServerStdio)
    assert servers[0].env == []


def test_roundtrip_fastmcp_acp_fastmcp():
    original = {
        "crow-mcp": {
            "transport": "stdio",
            "command": "crow-cli",
            "args": ["mcp"],
            "env": {"A": "1"},
        },
        "remote": {
            "transport": "http",
            "url": "http://x/mcp",
            "headers": {"K": "V"},
        },
    }
    servers = fastmcp_config_to_acp_servers(original)
    back = acp_to_fastmcp_config(servers)
    assert back["mcpServers"] == original
