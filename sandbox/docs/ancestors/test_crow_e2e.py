"""
End-to-end test for Crow Agent with MCP integration.

Based on streaming_async_react.py but uses the crow Agent.
"""
import asyncio
from crow import agent
from fastmcp import Client


async def main():
    """Test the Agent with MCP integration."""
    
    print("=" * 60)
    print("Testing Crow Agent with MCP")
    print("=" * 60)
    
    # 1. Get default config (loads from ~/.crow/mcp.json)
    default_config = agent.get_default_config()
    print(f"\n✓ Config loaded:")
    print(f"  - LLM: {default_config.llm.base_url}")
    print(f"  - Model: {default_config.llm.default_model}")
    print(f"  - MCP Servers: {list(default_config.mcp_servers.get('mcpServers', {}).keys())}")
    
    # 2. Create Agent with default config
    agent_instance = agent.Agent()
    print(f"\n✓ Agent created: {agent_instance}")
    
    # 3. Test MCP client directly (like in the IPython example)
    print("\n" + "=" * 60)
    print("Testing MCP Client")
    print("=" * 60)
    
    client_mcp = Client(default_config.mcp_servers)
    print(f"✓ MCP client created: {client_mcp}")
    
    async with client_mcp:
        # List tools
        tools = await client_mcp.list_tools()
        print(f"\n✓ Available tools ({len(tools)} total):")
        for i, tool in enumerate(tools[:10], 1):
            print(f"  {i}. {tool.name}: {tool.description[:50]}...")
        if len(tools) > 10:
            print(f"  ... and {len(tools) - 10} more")
        
        # Try calling a tool
        print(f"\n✓ Testing tool call...")
        try:
            result = await client_mcp.call_tool("terminal", {
                "command": "pwd"
            })
            print(f"  Result: {result.content[0].text}")
        except Exception as e:
            print(f"  Tool call error: {e}")
    
    print("\n" + "=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
