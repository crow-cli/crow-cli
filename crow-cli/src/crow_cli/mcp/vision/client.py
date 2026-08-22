import asyncio

from fastmcp import Client

# Local Python script
client = Client("main.py")


async def main():
    async with client:
        # Basic server interaction
        await client.ping()

        # List available operations
        tools = await client.list_tools()
        resources = await client.list_resources()
        prompts = await client.list_prompts()

        # Execute operations
        result = await client.call_tool("capture_webcam", {})
        print(result)


asyncio.run(main())
