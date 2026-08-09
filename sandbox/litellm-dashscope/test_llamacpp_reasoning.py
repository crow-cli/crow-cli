#!/usr/bin/env python3
"""
Test reasoning_content → content transition with llamacpp (Qwen3.6-35B-A3B).

llama.cpp handles reasoning_content differently from DashScope — it may
emit explicit transition markers. This script dumps every chunk to find
the exact boundary.

Run:
  cd sandbox/litellm-dashscope && uv --project . run python3 test_llamacpp_reasoning.py
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


def get_raw_chunk(chunk):
    """Extract raw delta values including type info."""
    if not chunk.choices or len(chunk.choices) == 0:
        return None
    delta = chunk.choices[0].delta
    rc = getattr(delta, "reasoning_content", "<MISSING>")
    dc = getattr(delta, "content", "<MISSING>")
    rc_type = type(rc).__name__
    dc_type = type(dc).__name__
    return {
        "reasoning_content": rc,
        "rc_type": rc_type,
        "content": dc,
        "dc_type": dc_type,
    }


async def main():
    config_dir = get_default_config_dir()
    config = Config.load(config_dir=config_dir)

    llamacpp = config.llm.providers["llamacpp"]
    api_key = llamacpp.api_key
    base_url = llamacpp.base_url
    model = "unsloth/Qwen3.6-35B-A3B-GGUF:Q8_0"

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    print("=" * 70)
    print(f"LLAMACPP STREAM — {model}")
    print("=" * 70)
    print()

    # Simple prompt designed to trigger reasoning + content
    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant. Think step by step, then give your answer.",
        },
        {"role": "user", "content": "Who is the president of France?"},
    ]

    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
    )

    thinking = []
    content = []
    tool_calls = {}

    chunk_index = 0
    transition_index = None
    rc_empty_chunks = []
    all_falsy_chunks = []

    async for chunk in response:
        chunk_index += 1

        if hasattr(chunk, "usage") and chunk.usage is not None:
            print(f"\n[Chunk {chunk_index:04d}] USAGE: {chunk.usage}")
            continue

        if not chunk.choices or len(chunk.choices) == 0:
            all_falsy_chunks.append(chunk_index)
            continue

        delta = chunk.choices[0].delta
        raw = get_raw_chunk(chunk)
        rc = raw["reasoning_content"]
        dc = raw["content"]

        # Track reasoning_content = "" (empty string, not None)
        if isinstance(rc, str) and rc == "":
            rc_empty_chunks.append({
                "index": chunk_index,
                "content": repr(dc),
                "content_type": raw["dc_type"],
            })

        # Detect the reasoning→content transition
        if transition_index is None:
            if rc is None and isinstance(dc, str) and dc and len(thinking) > 0:
                transition_index = chunk_index

        delta_info = describe_delta(delta)

        old_thinking = len(thinking)
        old_content = len(content)
        thinking, content, tool_calls, new_token = process_chunk(
            chunk, thinking, content, tool_calls
        )

        marker = ""
        if isinstance(rc, str) and rc == "":
            marker = "  ⚠️  REASONING_CONTENT EMPTY STRING"
        if transition_index == chunk_index:
            marker = "  ⚡ REASONING→CONTENT TRANSITION"

        status = ""
        if new_token[0] == "thinking":
            status = f"  → thinking (+{len(new_token[1])} chars)"
        elif new_token[0] == "content":
            status = f"  → content (+{len(new_token[1])} chars)"
        elif new_token[0] == "tool_call":
            status = f"  → tool_call"
        elif new_token[0] == "tool_args":
            status = f"  → tool_args"
        else:
            status = "  (no yield)"

        # Only print chunks near the transition or special cases
        is_near_transition = False
        if transition_index and abs(chunk_index - transition_index) <= 2:
            is_near_transition = True

        if is_near_transition or marker:
            print(f"[Chunk {chunk_index:04d}] rc={raw['rc_type']}:{rc!r} dc={raw['dc_type']}:{dc!r}{marker}{status}")
        else:
            # Print summary dots for bulk thinking
            if new_token[0] == "thinking":
                pass  # skip bulk thinking
            elif new_token[0] is not None:
                print(f"[Chunk {chunk_index:04d}] {status}")

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total chunks: {chunk_index}")
    print(f"Thinking tokens: {len(thinking)}")
    print(f"Content tokens: {len(content)}")
    print(f"Tool calls: {len(tool_calls)}")
    print()
    print(f"Transition at chunk: {transition_index or 'N/A'}")
    print()

    if rc_empty_chunks:
        print(f"⚠️  Found {len(rc_empty_chunks)} chunk(s) with reasoning_content='' (empty string):")
        for rc in rc_empty_chunks:
            print(f"    Chunk {rc['index']}: content={rc['content']} (type={rc['content_type']})")
    else:
        print("✓ No reasoning_content='' chunks — transitions use None")
    print()

    if all_falsy_chunks:
        print(f"All-falsy (no choices) chunks: {all_falsy_chunks}")
    print()

    # Show actual content
    thinking_text = "".join(thinking)
    content_text = "".join(content)
    print(f"Thinking: {thinking_text[:300]}...")
    print()
    print(f"Content: {content_text[:300] if content_text else '(empty)'}")

    # ── Tool-calling test ──
    print()
    print("=" * 70)
    print("TOOL-CALLING STREAM — llamacpp")
    print("=" * 70)
    print()

    tools = [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "queries": {
                            "type": "array",
                            "items": {"type": "string"},
                        }
                    },
                    "required": ["queries"],
                },
            },
        },
    ]

    messages2 = [
        {"role": "system", "content": "You are a helpful assistant. Use tools when helpful."},
        {"role": "user", "content": "Search for the latest quantum computing news in 2026."},
    ]

    response2 = await client.chat.completions.create(
        model=model,
        messages=messages2,
        tools=tools,
        stream=True,
        stream_options={"include_usage": True},
    )

    thinking2, content2, tool_calls2 = [], [], {}
    rc_empty_tool = []
    tc_first_chunk = None

    async for chunk in response2:
        chunk_index += 1

        if hasattr(chunk, "usage") and chunk.usage is not None:
            continue

        if not chunk.choices or len(chunk.choices) == 0:
            continue

        raw = get_raw_chunk(chunk)
        rc = raw["reasoning_content"]
        dc = raw["content"]

        if isinstance(rc, str) and rc == "":
            rc_empty_tool.append({
                "index": chunk_index,
                "content": repr(dc),
                "has_tool": bool(getattr(chunk.choices[0].delta, "tool_calls", None)),
            })

        if tc_first_chunk is None and getattr(chunk.choices[0].delta, "tool_calls", None):
            tc_first_chunk = chunk_index

        old_tc = len(tool_calls2)
        thinking2, content2, tool_calls2, new_token = process_chunk(
            chunk, thinking2, content2, tool_calls2
        )

        if new_token[0] == "tool_call" and tc_first_chunk == chunk_index:
            print(f"[Chunk {chunk_index:04d}] First tool_call: rc={raw['rc_type']}:{rc!r}")
        elif new_token[0] == "thinking":
            pass  # skip bulk

    print()
    if rc_empty_tool:
        print(f"⚠️  Found {len(rc_empty_tool)} chunk(s) with reasoning_content='' during tool stream:")
        for rc in rc_empty_tool:
            print(f"    Chunk {rc['index']}: content={rc['content']} has_tool={rc['has_tool']}")
    else:
        print("✓ No reasoning_content='' chunks in tool stream")
    print()
    print(f"First tool_call at chunk: {tc_first_chunk or 'N/A'}")
    print(f"Thinking: {''.join(thinking2)[:200]}...")
    print(f"Tool calls: {len(tool_calls2)}")


if __name__ == "__main__":
    asyncio.run(main())
