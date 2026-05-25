import asyncio
from fastmcp import Client
from fastmcp.client.transports import MCPConfigTransport

async def test_crow_mcp_with_env():
    """Test crow-mcp via uvx with env vars."""
    config = {
        "mcpServers": {
            "crow-mcp": {
                "transport": "stdio",
                "command": "uvx",
                "args": ["crow-mcp"],
                "env": {"SOME_VAR": "some_value"},
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

async def test_crow_mcp_without_env():
    """Test crow-mcp via uvx without env vars."""
    config = {
        "mcpServers": {
            "crow-mcp": {
                "transport": "stdio",
                "command": "uvx",
                "args": ["crow-mcp"],
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
    print("=== Test crow-mcp uvx WITHOUT env ===")
    try:
        asyncio.run(test_crow_mcp_without_env())
    except Exception as e:
        print(f"FAILED: {e}")

    print("\n=== Test crow-mcp uvx WITH env ===")
    try:
        asyncio.run(test_crow_mcp_with_env())
    except Exception as e:
        print(f"FAILED: {e}")
