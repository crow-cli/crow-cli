import asyncio
import json
import os

from dotenv import load_dotenv
from fastmcp import Client, FastMCP
from openai import OpenAI

# In-memory server (ideal for testing)
server = FastMCP("TestServer")
client = Client(server)

# Load environment variables from .env file
load_dotenv()

# OpenAI API client
oai_client = OpenAI(
    api_key=os.getenv("ZAI_API_KEY"), base_url=os.getenv("ZAI_BASE_URL")
)

# Local Python script
client = Client("search.py")


async def main():
    async with client:
        # Basic server interaction
        await client.ping()

        # List available operations
        tools = await client.list_tools()
        resources = await client.list_resources()
        prompts = await client.list_prompts()
        tool = tools[0]
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            },
        }
        tool_calls_by_id = {}
        messages = [{"role": "user", "content": "search for machine learning papers"}]
        assistant_response = []
        response = oai_client.chat.completions.create(
            model="glm-4.7",
            messages=messages,
            tools=[openai_tool],
            stream=True,
        )

        for chunk in response:
            if not chunk.choices[0].delta.tool_calls:
                if not hasattr(chunk.choices[0].delta, "reasoning_content"):
                    # this is not a reasoning chunk
                    print(chunk.choices[0].delta.content, end="", flush=True)
                    assistant_response.append(chunk.choices[0].delta.content)
                else:
                    # this is a reasoning chunk
                    print(chunk.choices[0].delta.reasoning_content, end="", flush=True)
                    assistant_response.append(chunk.choices[0].delta.reasoning_content)

            else:
                # Handle tool calls
                print()
                print("TOOL CALL:")
                for call in chunk.choices[0].delta.tool_calls:
                    print(call.id)
                    print(call.function.name)
                    print(call.function.arguments)
                    print(type(call.function.arguments))
                    tool_calls_by_id[call.id] = dict(
                        function_name=call.function.name,
                        arguments=call.function.arguments,
                    )
        messages.append({"role": "assistant", "content": "".join(assistant_response)})
        # Execute tool calls
        tool_call_inputs = []
        tool_response_results = []
        for tool_call_id, tool_call in tool_calls_by_id.items():
            tool_call_inputs.append(
                dict(
                    id=tool_call_id,
                    type="function",
                    function=dict(
                        name=tool_call["function_name"],
                        arguments=tool_call["arguments"],
                    ),
                )
            )
            result = await client.call_tool(
                tool_call["function_name"], json.loads(tool_call["arguments"])
            )
            tool_response_results.append(
                dict(
                    role="tool",
                    tool_call_id=tool_call_id,
                    content=result.content[0].text,
                )
            )
        if len(tool_call_inputs) > 0:
            messages.append(dict(role="assistant", tool_calls=tool_call_inputs))
        if len(tool_response_results) > 0:
            messages.extend(tool_response_results)
        response = oai_client.chat.completions.create(
            model="glm-4.7",
            messages=messages,
            tools=[openai_tool],
            stream=False,
        )
        return messages, response


messages, result = asyncio.run(main())
