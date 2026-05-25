import asyncio
from pathlib import Path
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

CROW_UI_MCP_PATH = Path("/home/thomas/src/crow-ai/crow-cli/crow-ui-mcp/main.py")

async def test_with_env():
    """Test crow-ui-mcp with env vars passed via StdioTransport."""
    transport = StdioTransport(
        command="python",
        args=[str(CROW_UI_MCP_PATH)],
        env={"CROW_UI_PORT": "4723"},
    )
    client = Client(transport=transport)
    async with client:
        tools = await client.list_tools()
        print(f"Tools found: {len(tools)}")
        for t in tools:
            print(f"  - {t.name}: {t.description}")

async def test_without_env():
    """Test crow-ui-mcp without env vars."""
    transport = StdioTransport(
        command="python",
        args=[str(CROW_UI_MCP_PATH)],
    )
    client = Client(transport=transport)
    async with client:
        tools = await client.list_tools()
        print(f"Tools found: {len(tools)}")
        for t in tools:
            print(f"  - {t.name}: {t.description}")

async def test_with_empty_env():
    """Test crow-ui-mcp with empty env var (simulates unset ${VAR})."""
    transport = StdioTransport(
        command="python",
        args=[str(CROW_UI_MCP_PATH)],
        env={"CROW_UI_PORT": ""},
    )
    client = Client(transport=transport)
    async with client:
        tools = await client.list_tools()
        print(f"Tools found: {len(tools)}")
        for t in tools:
            print(f"  - {t.name}: {t.description}")

async def test_mcp_config_transport():
    """Test using MCPConfigTransport like crow-cli does."""
    from fastmcp.client.transports import MCPConfigTransport
    config = {
        "mcpServers": {
            "crow-ui-mcp": {
                "transport": "stdio",
                "command": "python",
                "args": [str(CROW_UI_MCP_PATH)],
                "env": {"CROW_UI_PORT": "4723"},
            }
        }
    }
    transport = MCPConfigTransport(config, name_as_prefix=False)
    client = Client(transport=transport)
    async with client:
        tools = await client.list_tools()
        print(f"Tools found: {len(tools)}")
        for t in tools:
            print(f"  - {t.name}: {t.description}")

if __name__ == "__main__":
    print("=== Test WITHOUT env ===")
    try:
        asyncio.run(test_without_env())
    except Exception as e:
        print(f"FAILED: {e}")

    print("\n=== Test WITH env (CROW_UI_PORT=4723) ===")
    try:
        asyncio.run(test_with_env())
    except Exception as e:
        print(f"FAILED: {e}")

    print("\n=== Test WITH empty env (CROW_UI_PORT='') ===")
    try:
        asyncio.run(test_with_empty_env())
    except Exception as e:
        print(f"FAILED: {e}")

    print("\n=== Test MCPConfigTransport with env ===")
    try:
        asyncio.run(test_mcp_config_transport())
    except Exception as e:
        print(f"FAILED: {e}")
