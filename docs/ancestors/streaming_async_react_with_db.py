import asyncio
import json
import os
import traceback

import httpx
from dotenv import load_dotenv
from fastmcp import Client
from openai import OpenAI

from database import create_database, get_session, save_event

load_dotenv()


def log_request(request):
    print(f"\n{'=' * 20} RAW REQUEST {'=' * 20}")
    print(f"{request.method} {request.url}")
    print(f"Headers: {dict(request.headers)}")
    # request.read() allows us to see the streamable body
    print(f"Body: {request.read().decode()}")
    print(f"{'=' * 53}\n")


# Pass the hooked client into your existing configure_provider logic
def configure_provider():
    http_client = httpx.Client(event_hooks={"request": [log_request]})
    return OpenAI(
        api_key=os.getenv("ZAI_API_KEY"),
        base_url=os.getenv("ZAI_BASE_URL"),
        http_client=http_client,
    )


def setup_mcp_client(mcp_path="search.py"):
    return Client(mcp_path)


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


def process_chunk(chunk, thinking, content, tool_calls, tool_call_id):
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
            if call.id is not None:
                tool_call_id = call.id
                if call.id not in tool_calls:
                    tool_calls[call.id] = dict(
                        function_name=call.function.name,
                        arguments=[call.function.arguments],
                    )
                    new_token = (
                        "tool_call",
                        (call.function.name, call.function.arguments),
                    )
            else:
                arg_fragment = call.function.arguments
                tool_calls[tool_call_id]["arguments"].append(arg_fragment)
                new_token = ("tool_args", arg_fragment)
    return thinking, content, tool_calls, tool_call_id, new_token


def process_response(response):
    thinking, content, tool_calls, tool_call_id = [], [], {}, None
    final_usage = None
    for chunk in response:
        # Capture usage from the chunk (if present)
        if hasattr(chunk, 'usage') and chunk.usage:
            final_usage = {
                'prompt_tokens': chunk.usage.prompt_tokens,
                'completion_tokens': chunk.usage.completion_tokens,
                'total_tokens': chunk.usage.total_tokens,
            }
        thinking, content, tool_calls, tool_call_id, new_token = process_chunk(
            chunk, thinking, content, tool_calls, tool_call_id
        )
        msg_type, token = new_token
        if msg_type:
            yield msg_type, token
    return thinking, content, process_tool_call_inputs(tool_calls), final_usage


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
    messages, thinking, content, tool_call_inputs, tool_results, session_id=None, conv_index=0
):
    # Save assistant response with token counts
    if (len(content) > 0 or len(thinking) > 0) and session_id:
        save_event(
            session=get_session(),
            session_id=session_id,
            conv_index=conv_index,
            role="assistant",
            content="".join(content) if content else None,
            reasoning_content="".join(thinking) if thinking else None,
        )
        conv_index += 1
    
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
        # Save tool calls
        if session_id:
            for tool_call in tool_call_inputs:
                save_event(
                    session=get_session(),
                    session_id=session_id,
                    conv_index=conv_index,
                    role="assistant",
                    tool_call_id=tool_call["id"],
                    tool_call_name=tool_call["function"]["name"],
                    tool_arguments=json.loads(tool_call["function"]["arguments"]),
                )
                conv_index += 1
    if len(tool_results) > 0:
        messages.extend(tool_results)
        # Save tool results
        if session_id:
            for tool_result in tool_results:
                save_event(
                    session=get_session(),
                    session_id=session_id,
                    conv_index=conv_index,
                    role="tool",
                    tool_call_id=tool_result["tool_call_id"],
                    content=tool_result["content"],
                )
                conv_index += 1
    return messages, conv_index


async def react_loop(messages, mcp_client, lm, model, tools, session_id=None, max_turns=50000):
    conv_index = 0
    for _ in range(max_turns):
        response = send_request(messages, model, tools, lm)
        gen = process_response(response)
        while True:
            try:
                msg_type, token = next(gen)
                yield {"type": msg_type, "token": token}
            except StopIteration as e:
                thinking, content, tool_call_inputs, usage = e.value
                break
        if not tool_call_inputs:
            messages, conv_index = add_response_to_messages(messages, thinking, content, [], [], session_id, conv_index)
            yield {"type": "final_history", "messages": messages}
            return  # This ends the generator
        tool_results = await execute_tool_calls(
            mcp_client, tool_call_inputs, verbose=False
        )
        messages, conv_index = add_response_to_messages(
            messages, thinking, content, tool_call_inputs, tool_results, session_id, conv_index
        )


async def main():
    mcp_client = setup_mcp_client()
    lm = configure_provider()
    
    # Create database
    create_database()
    
    # Session ID - you'd generate this from system_prompt + tools hash
    session_id = "example-session-123"
    
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
        async for chunk in react_loop(messages, mcp_client, lm, "glm-4.7", tools, session_id):
            if chunk["type"] == "content":
                print(chunk["token"], end="", flush=True)
            elif chunk["type"] == "thinking":
                print(f"\n[Thinking]: {chunk['token']}", end="", flush=True)
            elif chunk["type"] == "tool_call":
                name, first_arg = chunk["token"]
                print(f"\n[Tool Call]: {name}({first_arg}", end="", flush=True)
            elif chunk["type"] == "tool_args":
                print(chunk["token"], end="", flush=True)
            elif chunk["type"] == "final_history":
                final_history = chunk["messages"]
    return final_history


if __name__ == "__main__":
    asyncio.run(main())
