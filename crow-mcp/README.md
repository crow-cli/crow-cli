<p align="center">
    <img src="https://github.com/odellus/crow/raw/v0.1.0/assets/crow-logo-crop.png" description="crow logo"width=500/>
</p>


# `crow-mcp`

## Configuration

```python
import os

from fastmcp import Client

CROW_MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
print("=" * 60)
print(f"CROW_MCP_DIR: {CROW_MCP_DIR}")
print("=" * 60)
config = {
    "mcpServers": {
        "crow_mcp": {
            "transport": "stdio",
            "command": "uv",
            "args": ["--project", CROW_MCP_DIR, "run", "crow-mcp"],
            "cwd": CROW_MCP_DIR,
        }
    }
}

async def test():
    client = Client(config)

    print("Connecting to MCP server...")
    async with client:
        print("✅ Connected\n")

        # Test 1: Basic command
        print("=" * 60)
        print("TEST 1: Basic command")
        print("=" * 60)
        result = await client.call_tool(
            "terminal", {"command": "echo 'Hello terminal!'"}
        )
        print(result.content[0].text)

        # Test 2: Directory persistence
        print("\n" + "=" * 60)
        print("TEST 2: CD persistence")
        print("=" * 60)
        result1 = await client.call_tool("terminal", {"command": "pwd"})
        print(f"Before: {result1.content[0].text}")

        result2 = await client.call_tool("terminal", {"command": "cd /tmp"})
        print(f"CD: {result2.content[0].text}")

        result3 = await client.call_tool("terminal", {"command": "pwd"})
        print(f"After: {result3.content[0].text}")

```


hey
