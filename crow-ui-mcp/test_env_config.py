import asyncio
from pathlib import Path
from fastmcp import Client
from fastmcp.client.transports import MCPConfigTransport

CROW_UI_MCP_PATH = Path(__file__).parent / "main.py"

async def test_config_with_env():
    """Test crow-ui-mcp via MCPConfigTransport with env vars."""
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

        # Call the prompt tool
        result = await client.call_tool(
            "prompt",
            {
                "message": "hello!",
                "session_id": "curly-masterful-ocelot-of-pleasure",
                "from_session_id": "honest-opalescent-frog-from-atlantis",
            },
        )
        print(f"Result: {result}")

async def test_config_without_env():
    """Test crow-ui-mcp via MCPConfigTransport WITHOUT env vars."""
    config = {
        "mcpServers": {
            "crow-ui-mcp": {
                "transport": "stdio",
                "command": "python",
                "args": [str(CROW_UI_MCP_PATH)],
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

async def test_config_with_unset_env():
    """Test crow-ui-mcp via MCPConfigTransport with empty env var."""
    config = {
        "mcpServers": {
            "crow-ui-mcp": {
                "transport": "stdio",
                "command": "python",
                "args": [str(CROW_UI_MCP_PATH)],
                "env": {"CROW_UI_PORT": ""},
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
        asyncio.run(test_config_without_env())
    except Exception as e:
        print(f"FAILED: {e}")

    print("\n=== Test WITH env (CROW_UI_PORT=4723) ===")
    try:
        asyncio.run(test_config_with_env())
    except Exception as e:
        print(f"FAILED: {e}")

    print("\n=== Test WITH empty env (CROW_UI_PORT='') ===")
    try:
        asyncio.run(test_config_with_unset_env())
    except Exception as e:
        print(f"FAILED: {e}")
