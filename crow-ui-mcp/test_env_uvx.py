import asyncio
from fastmcp import Client
from fastmcp.client.transports import MCPConfigTransport

async def test_uvx_with_env():
    """Test crow-ui-mcp via uvx with env vars."""
    config = {
        "mcpServers": {
            "crow-ui-mcp": {
                "transport": "stdio",
                "command": "uvx",
                "args": ["crow-ui-mcp"],
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

async def test_uvx_without_env():
    """Test crow-ui-mcp via uvx without env vars."""
    config = {
        "mcpServers": {
            "crow-ui-mcp": {
                "transport": "stdio",
                "command": "uvx",
                "args": ["crow-ui-mcp"],
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
    print("=== Test uvx WITHOUT env ===")
    try:
        asyncio.run(test_uvx_without_env())
    except Exception as e:
        print(f"FAILED: {e}")

    print("\n=== Test uvx WITH env ===")
    try:
        asyncio.run(test_uvx_with_env())
    except Exception as e:
        print(f"FAILED: {e}")
