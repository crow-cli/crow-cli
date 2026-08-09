import asyncio
import os

from fastmcp import Client, FastMCP

config = {
    "mcpServers": {
        "local_server": {
            # Local stdio server
            "transport": "stdio",
            "command": "uv",
            "args": ["--project", os.getcwd(), "run", "fastmcp-test"],
            # "env": {"DEBUG": "true"},
            "cwd": os.getcwd(),
        }
    }
}
# Local Python script
client = Client(config)


async def main():
    async with client:
        # Basic server interaction
        await client.ping()

        # List available operations
        tools = await client.list_tools()
        resources = await client.list_resources()
        prompts = await client.list_prompts()

        # Execute operations
        # result = await client.call_tool("example_tool", {"param": "value"})
        # print(result)
        print(tools)


asyncio.run(main())
