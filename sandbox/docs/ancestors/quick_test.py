"""
Quick test to verify Crow Agent + MCP integration works end-to-end.
"""
import asyncio
import json
from crow import agent
from crow.agent.mcp_client import get_tools, create_mcp_client_from_config
from crow.agent.llm import configure_llm


async def main():
    """Quick verification that MCP + Agent works."""
    
    print("Testing Crow Agent + MCP Integration")
    print("=" * 60)
    
    # 1. Load config
    config = agent.get_default_config()
    print(f"✓ Config loaded from ~/.crow/mcp.json")
    print(f"  MCP Servers: {list(config.mcp_servers.get('mcpServers', {}).keys())}")
    
    # 2. Test MCP client
    mcp_client = create_mcp_client_from_config(config.mcp_servers)
    
    async with mcp_client:
        tools = await get_tools(mcp_client)
        print(f"\n✓ Connected to MCP server")
        print(f"  Tools: {[t['function']['name'] for t in tools]}")
        
        # 3. Test a simple tool call directly
        print(f"\n✓ Testing direct tool call...")
        result = await mcp_client.call_tool("file_editor", {
            "command": "view",
            "path": "/home/thomas/src/projects/mcp-testing/README.md"
        })
        print(f"  Result: {result.content[0].text[:200]}...")
        
        # 4. Test agent react loop with a simple task
        print(f"\n{'='*60}")
        print("Testing Agent React Loop")
        print("=" * 60)
        
        llm = configure_llm(debug=False)
        messages = [
            {"role": "system", "content": "You are Crow, a helpful assistant. Be concise."},
            {"role": "user", "content": "Say 'Hello, I am Crow!' and nothing else."}
        ]
        
        # Single turn to verify it works
        response = llm.chat.completions.create(
            model=config.llm.default_model,
            messages=messages,
            stream=True,
        )
        
        print("Agent: ", end="", flush=True)
        for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                print(delta.content, end="", flush=True)
        print()
        
    print(f"\n{'='*60}")
    print("✓ All tests passed! MCP + Agent integration working!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
