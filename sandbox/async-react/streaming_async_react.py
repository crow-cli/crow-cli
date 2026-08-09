import asyncio
import json
import os
import traceback

import httpx
from dotenv import load_dotenv
from fastmcp import Client
from openai import AsyncOpenAI

load_dotenv()


async def log_request(request):
    print(f"\n{'=' * 20} RAW REQUEST {'=' * 20}")
    print(f"{request.method} {request.url}")
    print(f"Headers: {dict(request.headers)}")
    # request.read() allows us to see the streamable body
    print(f"Body: {request.read().decode()}")
    print(f"{'=' * 53}\n")


# Pass the hooked client into your existing configure_provider logic
def configure_provider():
    http_client = httpx.AsyncClient(event_hooks={"request": [log_request]})
    return AsyncOpenAI(
        api_key=os.getenv("ZAI_API_KEY"),
        base_url=os.getenv("ZAI_BASE_URL"),
        http_client=http_client,
    )


def setup_mcp_client():
    return Client(
        {
            "mcpServers": {
                "crow-mcp": {
                    "transport": "stdio",
                    "command": "uvx",
                    "args": [
                        "crow-mcp",
                    ],
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


async def send_request(messages, model, tools, lm):
    try:
        response = await lm.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            stream=True,
        )
        return response
    except Exception as e:
        traceback.print_exc()
        raise ValueError(f"Error sending request: {e}")


def process_chunk(chunk, thinking, content, tool_calls):
    delta = chunk.choices[0].delta
    new_token = (None, None)

    if not delta.tool_calls:
        if not hasattr(delta, "reasoning_content"):
            verbal_chunk = delta.content
            if verbal_chunk:
                content.append(verbal_chunk)
                new_token = ("content", verbal_chunk)
        else:
            reasoning_chunk = delta.reasoning_content
            if reasoning_chunk:
                thinking.append(reasoning_chunk)
                new_token = ("thinking", reasoning_chunk)
    else:
        for call in delta.tool_calls:
            index = call.index

            # Initialize the dictionary for this index if it doesn't exist
            if index not in tool_calls:
                tool_calls[index] = {"id": "", "function_name": "", "arguments": []}

            # Update fields if they are present in this delta
            if call.id:
                tool_calls[index]["id"] = call.id
            if call.function and call.function.name:
                tool_calls[index]["function_name"] = call.function.name
                new_token = (
                    "tool_call",
                    (call.function.name, call.function.arguments or ""),
                )

            if call.function and call.function.arguments:
                arg_fragment = call.function.arguments
                tool_calls[index]["arguments"].append(arg_fragment)
                # Only yield args if we didn't just yield the initial tool_call token above
                if new_token[0] != "tool_call":
                    new_token = ("tool_args", arg_fragment)

    return thinking, content, tool_calls, new_token


async def process_response(response):
    thinking, content, tool_calls = [], [], {}
    async for chunk in response:
        # tool_call_id is removed entirely from the inputs and outputs
        thinking, content, tool_calls, new_token = process_chunk(
            chunk, thinking, content, tool_calls
        )
        msg_type, token = new_token
        if msg_type:
            yield msg_type, token

    # Yield final result as a special chunk
    yield "final", (thinking, content, process_tool_call_inputs(tool_calls))


def process_tool_call_inputs(tool_calls):
    tool_call_inputs = []
    # tool_calls is now a dict keyed by the integer index from the stream
    for index, tool_call in sorted(tool_calls.items()):
        tool_call_inputs.append(
            dict(
                id=tool_call["id"],
                type="function",
                function=dict(
                    name=tool_call["function_name"],
                    arguments="".join(tool_call["arguments"]),
                ),
            )
        )
    return tool_call_inputs


async def execute_tool_calls(mcp_client, tool_call_inputs, verbose=True):
    tool_results = []
    for tool_call in tool_call_inputs:
        print(tool_call["function"]["arguments"])
        result = await mcp_client.call_tool(
            tool_call["function"]["name"],
            json.loads(tool_call["function"]["arguments"]),
        )
        tool_results.append(
            dict(
                role="tool",
                tool_call_id=tool_call["id"],
                content=result.content[0].text,
            )
        )
        if verbose:
            print()
            print("TOOL RESULT:")
            print(f"{tool_call['function']['name']}: ")
            print(f"{result.content[0].text}")
    return tool_results


def add_response_to_messages(
    messages, thinking, content, tool_call_inputs, tool_results
):
    if len(content) > 0 and len(thinking) > 0:
        messages.append(
            dict(
                role="assistant",
                content="".join(content),
                reasoning_content="".join(thinking),
            )
        )
    elif len(thinking) > 0:
        messages.append(dict(role="assistant", reasoning_content="".join(thinking)))
    elif len(content) > 0:
        messages.append(dict(role="assistant", content="".join(content)))
    if len(tool_call_inputs) > 0:
        messages.append(dict(role="assistant", tool_calls=tool_call_inputs))
    if len(tool_results) > 0:
        print(tool_results)
        messages.extend(tool_results)
    return messages


async def react_loop(messages, mcp_client, lm, model, tools, max_turns=50000):
    for _ in range(max_turns):
        response = await send_request(messages, model, tools, lm)
        gen = process_response(response)
        thinking, content, tool_call_inputs = [], [], []
        async for msg_type, token in gen:
            if msg_type == "final":
                thinking, content, tool_call_inputs = token
            else:
                yield {"type": msg_type, "token": token}
        if not tool_call_inputs:
            messages = add_response_to_messages(messages, thinking, content, [], [])
            yield {"type": "final_history", "messages": messages}
            return  # This ends the generator
        tool_results = await execute_tool_calls(
            mcp_client, tool_call_inputs, verbose=False
        )
        messages = add_response_to_messages(
            messages, thinking, content, tool_call_inputs, tool_results
        )


async def main():
    mcp_client = setup_mcp_client()
    lm = configure_provider()
    messages = [
        dict(role="system", content="You are a helpful assistant named Crow."),
        dict(
            role="user",
            content="search for machine learning papers with your search tool",
        ),
    ]
    final_history = []
    async with mcp_client:
        tools = await get_tools(mcp_client)
        async for chunk in react_loop(
            messages, mcp_client, lm, "accounts/fireworks/models/minimax-m2p5", tools
        ):
            print(chunk)
            # if chunk["type"] == "content":
            #     print(chunk["token"], end="", flush=True)
            # elif chunk["type"] == "thinking":
            #     print(chunk["token"], end="", flush=True)
            # elif chunk["type"] == "tool_call":
            #     name, first_arg = chunk["token"]
            #     print(f"TOOL CHUNK: {chunk}")
            #     print(f"\n[Tool Call]: {name}({first_arg}", end="", flush=True)
            # elif chunk["type"] == "tool_args":
            #     print(chunk["token"], end="", flush=True)
            # elif chunk["type"] == "final_history":
            #     final_history = chunk["messages"]
    return final_history


if __name__ == "__main__":
    asyncio.run(main())
