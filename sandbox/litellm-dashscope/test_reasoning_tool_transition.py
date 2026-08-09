#!/usr/bin/env python3
"""
Test reasoning_content="" transition with tool calls.

Some models emit reasoning_content="" as an explicit transition marker when
switching from thinking to tool calling. This script tests whether that
happens with qwen3.6-plus through LiteLLM.

Run:
  cd sandbox/litellm-dashscope && uv --project . run python3 test_reasoning_tool_transition.py
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "crow-cli" / "src"))

from crow_cli.agent.configure import Config, get_default_config_dir
from crow_cli.agent.react import process_chunk


def describe_delta(delta) -> dict:
    d = {}
    for attr in ("content", "reasoning_content", "role", "tool_calls"):
        val = getattr(delta, attr, "<MISSING>")
        if val == "<MISSING>":
            continue
        if attr == "tool_calls" and val:
            d[attr] = [
                {
                    "index": tc.index,
                    "id": tc.id,
                    "function": {
                        "name": tc.function.name if tc.function else None,
                        "arguments": tc.function.arguments if tc.function else None,
                    },
                }
                for tc in val
            ]
        else:
            d[attr] = repr(val)
    return d


async def main():
    config_dir = get_default_config_dir()
    config = Config.load(config_dir=config_dir)

    api_key = config.llm.providers["litellm"].api_key
    base_url = config.llm.providers["litellm"].base_url

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    tools = [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web for information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "queries": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of search queries",
                        }
                    },
                    "required": ["queries"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file from disk",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                    },
                    "required": ["path"],
                },
            },
        },
    ]

    print("=" * 70)
    print("TOOL-CALLING STREAM — reasoning_content → tool_calls transition")
    print("=" * 70)
    print()

    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant. Use tools when helpful. Think step by step.",
        },
        {
            "role": "user",
            "content": "Search for the latest news about quantum computing breakthroughs in 2026.",
        },
    ]

    response = await client.chat.completions.create(
        model="qwen3.6-plus",
        messages=messages,
        tools=tools,
        stream=True,
        stream_options={"include_usage": True},
    )

    thinking = []
    content = []
    tool_calls = {}

    chunk_index = 0
    transition_chunks = []  # Track reasoning_content == "" chunks
    empty_chunks = []  # Track chunks where both rc and content are falsy

    async for chunk in response:
        chunk_index += 1

        if hasattr(chunk, "usage") and chunk.usage is not None:
            print(f"\n[Chunk {chunk_index:04d}] USAGE: {chunk.usage}")
            continue

        if not chunk.choices or len(chunk.choices) == 0:
            print(f"\n[Chunk {chunk_index:04d}] NO CHOICES")
            continue

        delta = chunk.choices[0].delta
        delta_info = describe_delta(delta)

        rc = getattr(delta, "reasoning_content", None)
        dc = delta.content
        has_tool_calls = bool(delta.tool_calls)

        # Track special cases
        if rc == "" and rc is not None:
            transition_chunks.append({
                "index": chunk_index,
                "reasoning_content": repr(rc),
                "content": repr(dc),
                "tool_calls": has_tool_calls,
            })

        if not rc and not dc and not has_tool_calls:
            empty_chunks.append(chunk_index)

        # Run through process_chunk
        old_thinking_len = len(thinking)
        old_content_len = len(content)
        old_tc_count = len(tool_calls)
        thinking, content, tool_calls, new_token = process_chunk(
            chunk, thinking, content, tool_calls
        )

        tc_delta = len(tool_calls) - old_tc_count

        status = ""
        if new_token[0] == "thinking":
            status = f"  → thinking (+{len(new_token[1])} chars)"
        elif new_token[0] == "content":
            status = f"  → content (+{len(new_token[1])} chars)"
        elif new_token[0] == "tool_call":
            status = f"  → tool_call: {new_token[1][0]}"
        elif new_token[0] == "tool_args":
            status = f"  → tool_args (+{len(new_token[1])} chars)"
        else:
            status = f"  (no yield)"

        # Highlight the reasoning → tool_calls transition
        marker = ""
        if rc is not None and rc == "" and has_tool_calls:
            marker = "  ⚠️  REASONING→TOOL TRANSITION: reasoning_content='' + tool_calls"
        elif rc is not None and rc == "" and not has_tool_calls:
            marker = "  ⚠️  EMPTY REASONING: reasoning_content='' with no tool_calls"
        elif not has_tool_calls and old_tc_count == 0 and dc and rc is None and old_thinking_len > 0:
            marker = "  ⚡ REASONING→CONTENT TRANSITION"
        elif has_tool_calls and old_tc_count == 0:
            marker = "  ⚡ REASONING→TOOL_CALLS TRANSITION (first tool delta)"

        print(f"[Chunk {chunk_index:04d}] delta={delta_info}{marker}{status}")

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total chunks: {chunk_index}")
    print(f"Thinking tokens: {len(thinking)}")
    print(f"Content tokens: {len(content)}")
    print(f"Tool calls: {len(tool_calls)}")
    print()
    print(f"Thinking: {''.join(thinking)[:200]}...")
    print()
    print(f"Content: {''.join(content)[:200] if content else '(empty)'}")
    print()

    if transition_chunks:
        print(f"⚠️  Found {len(transition_chunks)} chunk(s) with reasoning_content='':")
        for tc in transition_chunks:
            print(f"    Chunk {tc['index']}: rc={tc['reasoning_content']} content={tc['content']} tools={tc['tool_calls']}")
    else:
        print("✓ No reasoning_content='' chunks found in this stream")
    print()

    if empty_chunks:
        print(f"Empty (all falsy) chunks: {empty_chunks}")
    print()

    # ── Token counting analysis ──
    print("=" * 70)
    print("TOKEN COUNTING ANALYSIS")
    print("=" * 70)
    thinking_text = "".join(thinking)
    content_text = "".join(content)
    tool_arg_text = "".join(
        "".join(tc["arguments"])
        for tc in sorted(tool_calls.values(), key=lambda x: x.get("id", ""))
    )
    print(f"Thinking chars: {len(thinking_text)}")
    print(f"Content chars: {len(content_text)}")
    print(f"Tool argument chars: {len(tool_arg_text)}")
    print()

    # Now let's also test what happens if we FIX the code
    print("=" * 70)
    print("FIXED process_chunk — comparison")
    print("=" * 70)
    print()

    def process_chunk_fixed(chunk, thinking, content, tool_calls):
        """Fixed version that handles reasoning_content='' explicitly."""
        if not chunk.choices or len(chunk.choices) == 0:
            return thinking, content, tool_calls, (None, None)

        delta = chunk.choices[0].delta
        new_token = (None, None)

        if not delta.tool_calls:
            reasoning_chunk = getattr(delta, "reasoning_content", None)
            if reasoning_chunk is not None:  # <-- FIX: is not None instead of truthiness
                thinking.append(reasoning_chunk)
                new_token = ("thinking", reasoning_chunk)
            else:
                verbal_chunk = delta.content
                if verbal_chunk:
                    content.append(verbal_chunk)
                    new_token = ("content", verbal_chunk)
        else:
            for call in delta.tool_calls:
                index = call.index
                if index not in tool_calls:
                    tool_calls[index] = {"id": "", "function_name": "", "arguments": []}
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
                    if new_token[0] != "tool_call":
                        new_token = ("tool_args", arg_fragment)

        return thinking, content, tool_calls, new_token

    # Re-stream to compare
    response2 = await client.chat.completions.create(
        model="qwen3.6-plus",
        messages=messages,
        tools=tools,
        stream=True,
        stream_options={"include_usage": True},
    )

    thinking_f = []
    content_f = []
    tool_calls_f = {}
    fixed_emitted = 0
    original_emitted = 0

    # We already have the original run's data, so just compare synthetic cases
    print("Synthetic comparison (original vs fixed):")
    print()

    class FakeFunction:
        def __init__(self, name=None, arguments=None):
            self.name = name
            self.arguments = arguments

    class FakeToolCall:
        def __init__(self, index=0, id=None, function=None):
            self.index = index
            self.id = id
            self.function = function

    class FakeDelta:
        def __init__(self, content=None, reasoning_content=None, role=None, tool_calls=None):
            self.content = content
            self.reasoning_content = reasoning_content
            self.role = role
            self.tool_calls = tool_calls

    class FakeChoice:
        def __init__(self, delta):
            self.delta = delta

    class FakeChunk:
        def __init__(self, delta):
            self.choices = [FakeChoice(delta)]
            self.usage = None

    test_cases = [
        ("reasoning_content='' + content=None", FakeDelta(content=None, reasoning_content="")),
        ("reasoning_content='' + content='Hello'", FakeDelta(content="Hello", reasoning_content="")),
        ("reasoning_content='' + content=''", FakeDelta(content="", reasoning_content="")),
        ("reasoning_content=None + content='Hi'", FakeDelta(content="Hi", reasoning_content=None)),
        ("reasoning_content='think' + content=None", FakeDelta(content=None, reasoning_content="think")),
        ("reasoning_content=None + content=None", FakeDelta(content=None, reasoning_content=None)),
    ]

    print(f"{'Test Case':<45} | {'Original':<20} | {'Fixed':<20}")
    print("-" * 90)

    for name, delta in test_cases:
        chunk = FakeChunk(delta)

        t_o, c_o, tc_o = [], [], {}
        _, _, _, tok_o = process_chunk(chunk, t_o, c_o, tc_o)

        t_f, c_f, tc_f = [], [], {}
        _, _, _, tok_f = process_chunk_fixed(chunk, t_f, c_f, tc_f)

        orig_result = f"thinking={t_o} content={c_o}"
        fixed_result = f"thinking={t_f} content={c_f}"

        diff = " ✓" if (t_o == t_f and c_o == c_f) else " ✗ DIFFERS"
        print(f"{name:<45} | {orig_result:<20} | {fixed_result:<20}{diff}")

    print()
    print("Key: ✗ DIFFERS means the fix changes behavior for this case")


if __name__ == "__main__":
    asyncio.run(main())
