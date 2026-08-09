#!/usr/bin/env python
"""
Test what usage information litellm returns in streaming responses WITH TOOLS.
"""

import asyncio
import json
import os

import httpx
from dotenv import load_dotenv
from fastmcp import Client
from openai import AsyncOpenAI

load_dotenv()


async def log_request(request):
    print(f"\n{'=' * 20} RAW REQUEST {'=' * 20}")
    print(f"{request.method} {request.url}")
    print(f"Headers: {dict(request.headers)}")
    print(f"Body: {request.read().decode()}")
    print(f"{'=' * 53}\n")


def configure_litellm():
    http_client = httpx.AsyncClient(event_hooks={"request": [log_request]})
    return AsyncOpenAI(
        api_key="EMPTY",  # litellm proxy
        base_url="http://localhost:4000/v1",
        http_client=http_client,
    )


def setup_mcp_client():
    return Client(
        {
            "mcpServers": {
                "crow-mcp": {
                    "transport": "stdio",
                    "command": "uvx",
                    "args": ["crow-mcp"],
                }
            }
        }
    )


async def get_tools(mcp_client):
    mcp_tools = await mcp_client.list_tools()
    tools = [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            },
        }
        for tool in mcp_tools
    ]
    return tools


async def test_streaming_usage_with_tools():
    lm = configure_litellm()
    mcp_client = setup_mcp_client()
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant with access to tools."},
        {"role": "user", "content": "List the files in the current directory using your tool."},
    ]
    
    print("Testing streaming response WITH TOOLS and usage tracking...\n")
    
    async with mcp_client:
        tools = await get_tools(mcp_client)
        
        print(f"Available tools: {[t['function']['name'] for t in tools]}\n")
        
        response = await lm.chat.completions.create(
            model="qwen3.5-plus",
            messages=messages,
            tools=tools,
            stream=True,
            stream_options={"include_usage": True},
        )
        
        chunk_count = 0
        usage_chunks = []
        content_chunks = []
        tool_call_chunks = []
        
        async for chunk in response:
            chunk_count += 1
            
            # Check for usage in every chunk
            if hasattr(chunk, "usage") and chunk.usage is not None:
                usage_info = {
                    "chunk_index": chunk_count,
                    "usage": {
                        "prompt_tokens": getattr(chunk.usage, "prompt_tokens", None),
                        "completion_tokens": getattr(chunk.usage, "completion_tokens", None),
                        "total_tokens": getattr(chunk.usage, "total_tokens", None),
                    }
                }
                usage_chunks.append(usage_info)
                print(f"Chunk {chunk_count}: 📊 USAGE - {usage_info['usage']}")
            
            # Check for content
            if chunk.choices and chunk.choices[0].delta.content:
                content_chunks.append(chunk.choices[0].delta.content)
                print(f"Chunk {chunk_count}: 💬 content='{chunk.choices[0].delta.content[:50]}...'")
            
            # Check for tool calls
            if chunk.choices and chunk.choices[0].delta.tool_calls:
                for tc in chunk.choices[0].delta.tool_calls:
                    tool_call_chunks.append({
                        "chunk_index": chunk_count,
                        "index": tc.index,
                        "name": tc.function.name if tc.function else None,
                        "args": tc.function.arguments if tc.function else None,
                    })
                    print(f"Chunk {chunk_count}: 🔧 TOOL CALL [{tc.index}] {tc.function.name if tc.function else '???'}")
        
        print(f"\n{'=' * 60}")
        print(f"SUMMARY:")
        print(f"  Total chunks: {chunk_count}")
        print(f"  Chunks with usage: {len(usage_chunks)}")
        print(f"  Content chunks: {len(content_chunks)}")
        print(f"  Tool call chunks: {len(tool_call_chunks)}")
        
        if usage_chunks:
            print(f"\n📊 Usage information:")
            for uc in usage_chunks:
                print(f"  Chunk {uc['chunk_index']}: {uc['usage']}")
            
            final_usage = usage_chunks[-1]["usage"]
            print(f"\n✅ Final usage from last chunk:")
            print(f"  Prompt tokens: {final_usage['prompt_tokens']}")
            print(f"  Completion tokens: {final_usage['completion_tokens']}")
            print(f"  Total tokens: {final_usage['total_tokens']}")
        else:
            print("\n⚠️  NO USAGE INFORMATION FOUND IN ANY CHUNK")
            print("  This means litellm/qwen3.5-plus doesn't return usage in streaming mode")
            print("  even with stream_options={'include_usage': True}")
        
        if tool_call_chunks:
            print(f"\n🔧 Tool calls detected:")
            for tc in tool_call_chunks:
                print(f"  Chunk {tc['chunk_index']}: [{tc['index']}] {tc['name']}")
        
        print(f"{'=' * 60}\n")


async def main():
    await test_streaming_usage_with_tools()


if __name__ == "__main__":
    asyncio.run(main())
