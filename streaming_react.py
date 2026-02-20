import asyncio
import json
import os
import traceback

from dotenv import load_dotenv
from fastmcp import Client
from openai import OpenAI

load_dotenv()


def configure_provider():
    return OpenAI(api_key=os.getenv("ZAI_API_KEY"), base_url=os.getenv("ZAI_BASE_URL"))


def setup_mcp_client(mcp_path="/home/thomas/.crow/mcp.json"):
    with open(mcp_path, "r") as f:
        config = json.load(f)
    return Client(config)


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


def send_request(messages, model, tools, lm):
    """Send a request to the LLM provider"""
    try:
        response = lm.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            stream=True,
        )
        return response
    except Exception as e:
        traceback.print_exc()
        raise ValueError(f"Error sending request: {e}")


def process_chunk(chunk, thinking, content, tool_calls, tool_call_id, verbose=True):
    print(chunk)
    if not chunk.choices[0].delta.tool_calls:
        if not hasattr(chunk.choices[0].delta, "reasoning_content"):
            verbal_chunk = chunk.choices[0].delta.content
            if verbal_chunk is not None:
                content.append(verbal_chunk)
                if verbose:
                    print(verbal_chunk, end="", flush=True)
        else:
            reasoning_chunk = chunk.choices[0].delta.reasoning_content
            if reasoning_chunk is not None:
                thinking.append(reasoning_chunk)
                if verbose:
                    print(reasoning_chunk, end="", flush=True)

    else:
        for call in chunk.choices[0].delta.tool_calls:
            if call.id is not None and call.id != "":
                tool_call_id = call.id
                if call.id not in tool_calls:
                    tool_calls[call.id] = dict(
                        function_name=call.function.name,
                        arguments=[call.function.arguments],
                    )
                    if verbose:
                        print("TOOL CALL:")
                        print(call.function.name)
                        print(call.function.arguments, end="", flush=True)

            else:
                tool_calls[tool_call_id]["arguments"].append(call.function.arguments)
                if verbose:
                    print(call.function.arguments, end="", flush=True)
    return thinking, content, tool_calls, tool_call_id


def process_response(response, verbose=True):
    thinking = []
    content = []
    tool_calls = {}
    tool_call_id = None
    for chunk in response:
        thinking, content, tool_calls, tool_call_id = process_chunk(
            chunk,
            thinking,
            content,
            tool_calls,
            tool_call_id,
            verbose=verbose,
        )
    return thinking, content, process_tool_call_inputs(tool_calls)


def process_tool_call_inputs(tool_calls):
    tool_call_inputs = []
    for tool_call_id, tool_call in tool_calls.items():
        tool_call_inputs.append(
            dict(
                id=tool_call_id,
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
        print(tool_call)
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
        messages.extend(tool_results)
    return messages


async def react_loop(
    messages, mcp_client, lm, model, tools, max_turns=50000, verbose=False
):
    for _ in range(max_turns):
        response = send_request(messages, model, tools, lm)
        thinking, content, tool_calls = process_response(response, verbose=verbose)
        tool_results = await execute_tool_calls(mcp_client, tool_calls, verbose=verbose)
        messages = add_response_to_messages(
            messages, thinking, content, tool_calls, tool_results
        )
        if len(tool_calls) < 1:
            break
    return messages


async def main():
    mcp_client = setup_mcp_client()
    lm = configure_provider()
    message = [
        dict(role="system", content="You are a helpful assistant named Crow."),
        dict(
            role="user",
            content="search for machine learning papers with your search tool",
        ),
    ]
    async with mcp_client:
        tools = await get_tools(mcp_client)
        messages = await react_loop(message, mcp_client, lm, "glm-5", tools)
    return messages


if __name__ == "__main__":
    asyncio.run(main())
