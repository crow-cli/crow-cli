# Using Crow SDK in Your REPL

## Quick Start

```python
# In your IPython REPL:
from crow.agent import create_mcp_client_from_acp, create_mcp_client_from_config
import asyncio

# Option 1: Use builtin MCP server (easiest, no setup)
client = await create_mcp_client_from_acp([])

# Option 2: Use config dict (your preferred format)
config = {
    "mcpServers": {
        "weather": {
            "url": "https://weather-api.example.com/mcp",
            "transport": "sse"
        },
        "assistant": {
            "command": "python",
            "args": ["./assistant_server.py"],
            "transport": "stdio"
        }
    }
}
client = create_mcp_client_from_config(config)

# Use it
async with client:
    # List tools
    tools = await client.list_tools()
    print(f"Found {len(tools)} tools")
    
    # Call a tool
    result = await client.call_tool("file_editor", {
        "command": "view",
        "path": "/home/thomas/src/projects/mcp-testing/README.md"
    })
    print(result.content[0].text)
```

## Using in REPL (no async with)

For easier REPL use, I recommend creating a helper:

```python
import asyncio
from crow.agent import create_mcp_client_from_acp

# Create a persistent client for REPL session
class REPLClient:
    def __init__(self):
        self._client = None
        self._cm = None
    
    async def start(self):
        self._client = await create_mcp_client_from_acp([])
        self._cm = self._client.__aenter__()
        await self._cm
        return self._client
    
    async def stop(self):
        if self._cm:
            await self._client.__aexit__(None, None, None)

# Use it
repl = REPLClient()
client = asyncio.run(repl.start())

# Now you can use client directly
tools = asyncio.run(client.list_tools())

# When done
asyncio.run(repl.stop())
```

## What's Available

### From crow.agent:
- `create_mcp_client_from_acp(mcp_servers)` - Takes ACP server list
- `create_mcp_client_from_config(config_dict)` - Takes FastMCP config dict
- `get_tools(client)` - Get tools in OpenAI format
- `Agent` - The main agent class
- `Session` - Session management
- `configure_llm()` - Configure LLM client

### From crow_mcp_server (builtin):
- `file_editor` - View, create, edit files
- `web_search` - Search the web via SearXNG
- `fetch` - Fetch and parse web pages

## Example Session

```python
thomas@coast-after-2:~/src/projects/mcp-testing$ uv --project . run ipython

In [1]: from crow.agent import create_mcp_client_from_acp
   ...: import asyncio

In [2]: client = asyncio.run(create_mcp_client_from_acp([]))

In [3]: async def list_tools():
   ...:     async with client:
   ...:         tools = await client.list_tools()
   ...:         return tools
   ...: 

In [4]: tools = asyncio.run(list_tools())

In [5]: print(f"Found {len(tools)} tools:")
   ...: for t in tools:
   ...:     print(f"  - {t.name}")
   ...: 
Found 3 tools:
  - file_editor
  - web_search
  - fetch

In [6]: async def read_readme():
   ...:     async with client:
   ...:         return await client.call_tool("file_editor", {
   ...:             "command": "view",
   ...:             "path": "/home/thomas/src/projects/mcp-testing/README.md"
   ...:         })
   ...: 

In [7]: result = asyncio.run(read_readme())

In [8]: print(result.content[0].text[:500])
```

## Next: Using with Agent

For full agent usage, you'd pass the MCP config to Agent:

```python
from crow.agent import Agent
from acp import run_agent

# Create agent
agent = Agent()

# Run via ACP
await run_agent(agent)
```

The agent will handle session management, MCP client lifecycle, etc.
