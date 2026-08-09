"""
Simple end-to-end example using Crow Agent with MCP tools.

This mimics streaming_async_react.py but uses the Crow Agent infrastructure.
No database, no sessions - just pure agent interaction.
"""
import asyncio
import json
from crow import agent
from crow.agent.mcp_client import get_tools, create_mcp_client_from_config
from crow.agent.llm import configure_llm


async def main():
    """Run a simple agent interaction with MCP tools."""
    
    print("=" * 60)
    print("Crow Agent - Simple Example (No DB)")
    print("=" * 60)
    
    # 1. Get default config (loads from ~/.crow/mcp.json)
    config = agent.get_default_config()
    print(f"\n✓ Config loaded from ~/.crow/mcp.json")
    print(f"  - Model: {config.llm.default_model}")
    print(f"  - MCP Servers: {list(config.mcp_servers.get('mcpServers', {}).keys())}")
    
    # 2. Create MCP client
    mcp_client = create_mcp_client_from_config(config.mcp_servers)
    
    # 3. Configure LLM
    llm = configure_llm(debug=False)
    
    async with mcp_client:
        # 4. Get tools
        tools = await get_tools(mcp_client)
        print(f"\n✓ Retrieved {len(tools)} tools from MCP server")
        
        # 5. Setup messages
        messages = [
            {"role": "system", "content": "You are a helpful assistant named Crow."},
            {"role": "user", "content": "Use the file_editor tool to view the README.md file and summarize what this project is about."}
        ]
        
        print(f"\n{'='*60}")
        print("Agent Response:")
        print("=" * 60)
        
        # 6. Run react loop (simplified from streaming_async_react.py)
        max_turns = 5
        for turn in range(max_turns):
            print(f"\n[Turn {turn + 1}]")
            
            # Send request to LLM
            response = llm.chat.completions.create(
                model=config.llm.default_model,
                messages=messages,
                tools=tools,
                stream=True,
            )
            
            # Process streaming response
            thinking, content, tool_calls, tool_call_id = [], [], {}, None
            
            for chunk in response:
                delta = chunk.choices[0].delta
                
                if not delta.tool_calls:
                    if not hasattr(delta, "reasoning_content"):
                        # Regular content
                        if delta.content:
                            content.append(delta.content)
                            print(delta.content, end="", flush=True)
                    else:
                        # Thinking/reasoning
                        if delta.reasoning_content:
                            thinking.append(delta.reasoning_content)
                            print(f"\n[Thinking]: {delta.reasoning_content}", end="", flush=True)
                else:
                    # Tool calls
                    for call in delta.tool_calls:
                        if call.id is not None:
                            tool_call_id = call.id
                            if call.id not in tool_calls:
                                tool_calls[call.id] = {
                                    "function_name": call.function.name,
                                    "arguments": [call.function.arguments],
                                }
                                print(f"\n[Tool Call]: {call.function.name}({call.function.arguments}", end="", flush=True)
                        else:
                            arg_fragment = call.function.arguments
                            tool_calls[tool_call_id]["arguments"].append(arg_fragment)
                            print(arg_fragment, end="", flush=True)
            
            print()  # New line after streaming
            
            # If no tool calls, we're done
            if not tool_calls:
                # Add assistant response to messages
                if content:
                    messages.append({"role": "assistant", "content": "".join(content)})
                break
            
            # Process tool calls
            tool_call_inputs = []
            for tid, tc in tool_calls.items():
                tool_call_inputs.append({
                    "id": tid,
                    "type": "function",
                    "function": {
                        "name": tc["function_name"],
                        "arguments": "".join(tc["arguments"]),
                    },
                })
            
            # Add assistant response with tool calls
            if content and thinking:
                messages.append({
                    "role": "assistant",
                    "content": "".join(content),
                    "reasoning_content": "".join(thinking),
                })
            elif thinking:
                messages.append({"role": "assistant", "reasoning_content": "".join(thinking)})
            elif content:
                messages.append({"role": "assistant", "content": "".join(content)})
            
            messages.append({"role": "assistant", "tool_calls": tool_call_inputs})
            
            # Execute tool calls
            print(f"\n[Executing {len(tool_call_inputs)} tool calls...]")
            tool_results = []
            for tool_call in tool_call_inputs:
                result = await mcp_client.call_tool(
                    tool_call["function"]["name"],
                    json.loads(tool_call["function"]["arguments"]),
                )
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": result.content[0].text,
                })
                print(f"  ✓ {tool_call['function']['name']}: {result.content[0].text[:100]}...")
            
            # Add tool results to messages
            messages.extend(tool_results)
        
        print(f"\n{'='*60}")
        print(f"✓ Agent completed after {turn + 1} turns!")
        print(f"  - Total messages: {len(messages)}")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
