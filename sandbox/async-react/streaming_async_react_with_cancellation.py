#!/usr/bin/env python3
"""
Sandbox async-react with cancellation support.

Key changes from original:
1. process_response() accepts state_accumulator parameter
2. process_response() yields "final" instead of returning
3. react_loop() checks cancel_event and persists on cancel
"""

import asyncio
import json
import os
import sys
import traceback

import httpx
from dotenv import load_dotenv
from fastmcp import Client
from openai import AsyncOpenAI

load_dotenv()

DELAY = 10.0


async def log_request(request):
    print(f"\n{'=' * 20} RAW REQUEST {'=' * 20}")
    print(f"{request.method} {request.url}")
    print(f"Headers: {dict(request.headers)}")
    print(f"Body: {request.read().decode()}")
    print(f"{'=' * 53}\n")


def configure_provider():
    http_client = httpx.AsyncClient(event_hooks={"request": [log_request]})
    return AsyncOpenAI(
        api_key=os.getenv("ZAI_API_KEY"),
        base_url=os.getenv("ZAI_BASE_URL"),
        http_client=http_client,
    )


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


async def process_response(response, state_accumulator: dict = None):
    """
    Process streaming response with state accumulator for cancellation.

    Args:
        response: Streaming response from LLM
        state_accumulator: Optional dict to expose partial state externally

    Yields:
        - (msg_type, token) for each streaming chunk
        - ("final", (thinking, content, tool_call_inputs, usage)) when done
    """
    thinking, content, tool_calls, tool_call_id = [], [], {}, None
    final_usage = None

    if state_accumulator is not None:
        state_accumulator.update(
            {
                "thinking": thinking,
                "content": content,
                "tool_calls": tool_calls,
                "tool_call_inputs": [],
            }
        )

    async for chunk in response:
        if hasattr(chunk, "usage") and chunk.usage:
            final_usage = {
                "prompt_tokens": chunk.usage.prompt_tokens,
                "completion_tokens": chunk.usage.completion_tokens,
                "total_tokens": chunk.usage.total_tokens,
            }

        thinking, content, tool_calls, tool_call_id, new_token = process_chunk(
            chunk, thinking, content, tool_calls, tool_call_id
        )

        if state_accumulator is not None:
            state_accumulator["thinking"] = thinking
            state_accumulator["content"] = content
            state_accumulator["tool_calls"] = tool_calls

        msg_type, token = new_token
        if msg_type:
            yield msg_type, token

    tool_call_inputs = process_tool_call_inputs(tool_calls)

    if state_accumulator is not None:
        state_accumulator["tool_call_inputs"] = tool_call_inputs

    yield "final", (thinking, content, tool_call_inputs, final_usage)


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
    messages,
    mcp_client,
    lm,
    model,
    tools,
    cancel_event: asyncio.Event = None,
    on_cancel: callable = None,
    max_turns=50000,
):
    """
    React loop with cancellation support.

    Args:
        cancel_event: asyncio.Event to signal cancellation
        on_cancel: callback(thinking, content, tool_call_inputs, tool_results)
    """
    for turn in range(max_turns):
        if cancel_event and cancel_event.is_set():
            print(f"\n[Cancelled at start of turn {turn}]")
            return

        response = await send_request(messages, model, tools, lm)

        state_accumulator = {"thinking": [], "content": [], "tool_call_inputs": []}

        gen = process_response(response, state_accumulator)
        thinking, content, tool_call_inputs, usage = [], [], [], None

        async for msg_type, token in gen:
            if msg_type == "final":
                thinking, content, tool_call_inputs, usage = token
            else:
                if cancel_event and cancel_event.is_set():
                    print(f"\n[Cancelled mid-stream]")
                    if on_cancel:
                        on_cancel(
                            state_accumulator["thinking"],
                            state_accumulator["content"],
                            state_accumulator["tool_call_inputs"],
                            [],
                        )
                    return

                yield {"type": msg_type, "token": token}

        if cancel_event and cancel_event.is_set():
            print(f"\n[Cancelled before tool execution]")
            if on_cancel:
                on_cancel(thinking, content, tool_call_inputs, [])
            return

        if not tool_call_inputs:
            messages = add_response_to_messages(messages, thinking, content, [], [])
            yield {"type": "final_history", "messages": messages}
            return

        tool_results = await execute_tool_calls(
            mcp_client, tool_call_inputs, verbose=False
        )

        if cancel_event and cancel_event.is_set():
            print(f"\n[Cancelled after tool execution]")
            if on_cancel:
                on_cancel(thinking, content, tool_call_inputs, tool_results)
            return

        messages = add_response_to_messages(
            messages, thinking, content, tool_call_inputs, tool_results
        )


async def test_cancellation():
    """Test cancellation mid-stream."""
    mcp_client = setup_mcp_client()
    lm = configure_provider()

    messages = [
        dict(role="system", content="You are a helpful assistant named Crow."),
        dict(
            role="user",
            content="Tell me a long story about a robot learning to paint.",
        ),
    ]

    cancel_event = asyncio.Event()

    partial_state = {"messages": []}

    def on_cancel(thinking, content, tool_call_inputs, tool_results):
        partial_state["messages"] = add_response_to_messages(
            messages.copy(), thinking, content, tool_call_inputs, tool_results
        )
        print(
            f"\n[Saved partial state: {len(content)} content chunks, {len(thinking)} thinking chunks]"
        )

    async def cancel_after_delay():
        await asyncio.sleep(DELAY)
        print("\n\n*** SENDING CANCEL ***\n")
        cancel_event.set()

    asyncio.create_task(cancel_after_delay())

    final_history = []
    async with mcp_client:
        tools = await get_tools(mcp_client)
        try:
            async for chunk in react_loop(
                messages,
                mcp_client,
                lm,
                "glm-5",
                tools,
                cancel_event=cancel_event,
                on_cancel=on_cancel,
            ):
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
        except Exception as e:
            print(f"\n[Error: {e}]")

    print("\n\n=== RESULTS ===")
    print(f"Completed: {len(final_history) > 0}")
    print(f"Partial state saved: {len(partial_state['messages']) > 0}")
    if partial_state["messages"]:
        print(f"Partial messages: {len(partial_state['messages'])}")
        last_msg = partial_state["messages"][-1]
        if "content" in last_msg:
            print(f"Last content length: {len(last_msg['content'])}")

    return final_history or partial_state["messages"]


async def main():
    """Normal execution without cancellation."""
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
        async for chunk in react_loop(messages, mcp_client, lm, "glm-5", tools):
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
    if len(sys.argv) > 1 and sys.argv[1] == "--test-cancel":
        print("Running cancellation test...")
        asyncio.run(test_cancellation())
    else:
        asyncio.run(main())
