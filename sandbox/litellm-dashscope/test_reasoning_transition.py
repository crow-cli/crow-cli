#!/usr/bin/env python3
"""
Reproduce the reasoning_content="" token drop at the reasoning→content transition.

The hypothesis: When DashScope/qwen transitions from reasoning to content,
it emits a chunk with reasoning_content="" (empty string, not None).
Our process_chunk code does:

    reasoning_chunk = getattr(delta, "reasoning_content", None)
    if reasoning_chunk:       # "" is falsy → falls to else
        ...
    else:
        verbal_chunk = delta.content
        if verbal_chunk:       # if content is also "" or None → TOKEN DROPPED
            ...

This script streams a real response and logs EVERY chunk's delta fields to
see exactly what the transition looks like.

Run:
  cd sandbox/litellm-dashscope && uv --project . run python3 test_reasoning_transition.py
"""

import asyncio
import json
import sys
from pathlib import Path

# Add crow-cli to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "crow-cli" / "src"))

from crow_cli.agent.configure import Config, get_default_config_dir
from crow_cli.agent.react import process_chunk


def describe_delta(delta) -> dict:
    """Extract all relevant fields from a delta for debugging."""
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

    # Use openai client to hit litellm proxy
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    print("=" * 70)
    print("STREAMING CHRAW DUMP — reasoning_content → content transition")
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
        model="qwen3.6-plus",
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
    )

    # Simulate the exact state that process_chunk uses
    thinking = []
    content = []
    tool_calls = {}

    chunk_index = 0
    transition_found = False

    async for chunk in response:
        chunk_index += 1

        # Check for usage (final chunk)
        if hasattr(chunk, "usage") and chunk.usage is not None:
            print(f"\n[Chunk {chunk_index:04d}] USAGE: {chunk.usage}")
            continue

        if not chunk.choices or len(chunk.choices) == 0:
            print(f"\n[Chunk {chunk_index:04d}] NO CHOICES")
            continue

        delta = chunk.choices[0].delta
        delta_info = describe_delta(delta)

        # Check for the transition case
        rc = getattr(delta, "reasoning_content", None)
        dc = delta.content

        is_transition_case = False
        if rc is not None and rc == "" and not delta.tool_calls:
            is_transition_case = True
            if not transition_found:
                print("\n" + "!" * 70)
                print("  ⚠ TRANSITION CHUNK DETECTED: reasoning_content='' (empty string)")
                print("!" * 70)
                transition_found = True

        # Check if this chunk would be DROPPED by current process_chunk logic
        would_drop = False
        drop_reason = ""

        if not delta.tool_calls:
            if rc == "":
                # falls to else branch
                if not dc:
                    would_drop = True
                    drop_reason = "reasoning_content='' (falsy) + content is falsy → SILENT DROP"
            elif rc is not None:
                pass  # goes to thinking branch
            else:
                # rc is None
                if not dc:
                    would_drop = True
                    drop_reason = "reasoning_content=None + content is falsy → SILENT DROP"
        else:
            # tool_calls branch — reasoning_content and content are IGNORED
            if rc is not None or dc:
                would_drop = True
                drop_reason = f"tool_calls branch active — reasoning_content={repr(rc)} and/or content={repr(dc)} are IGNORED"

        # Run through actual process_chunk
        old_thinking_len = len(thinking)
        old_content_len = len(content)
        thinking, content, tool_calls, new_token = process_chunk(
            chunk, thinking, content, tool_calls
        )

        thinking_delta = len(thinking) - old_thinking_len
        content_delta = len(content) - old_content_len

        status = ""
        if would_drop:
            status = f"  ⚠️  DROPPED: {drop_reason}"
        elif new_token[0] == "thinking":
            status = f"  → thinking ({len(new_token[1])} chars)"
        elif new_token[0] == "content":
            status = f"  → content ({len(new_token[1])} chars)"
        elif new_token[0] == "tool_call":
            status = f"  → tool_call: {new_token[1][0]}"
        elif new_token[0] == "tool_args":
            status = f"  → tool_args ({len(new_token[1])} chars)"
        else:
            status = f"  (no yield)"

        print(f"[Chunk {chunk_index:04d}] delta={delta_info}")
        if is_transition_case:
            print(f"  *** REASONING→CONTENT TRANSITION ***")
        print(f"  thinking_accumulated={old_thinking_len}→{len(thinking)}  content_accumulated={old_content_len}→{len(content)}")
        if status:
            print(status)

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total chunks: {chunk_index}")
    print(f"Thinking tokens accumulated: {len(thinking)}")
    print(f"Content tokens accumulated: {len(content)}")
    print(f"Tool calls: {len(tool_calls)}")
    print()
    print(f"Full thinking: {''.join(thinking)[:200]}...")
    print()
    print(f"Full content: {''.join(content)[:200]}...")
    print()

    # ── Reproduce the exact bug with synthetic chunks ──
    print("=" * 70)
    print("SYNTHETIC BUG REPRODUCTION")
    print("=" * 70)
    print()

    # Simulate what DashScope sends at the transition
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

    # Scenario 1: Normal transition — reasoning_content="" + content=None
    # This is the DANGEROUS case if the next chunk also doesn't fire
    print("Scenario 1: reasoning_content='' + content=None (transition marker)")
    thinking1, content1, tc1 = [], [], {}
    chunk1 = FakeChunk(FakeDelta(content=None, reasoning_content=""))
    thinking1, content1, tc1, token1 = process_chunk(chunk1, thinking1, content1, tc1)
    print(f"  thinking={thinking1} content={content1} token={token1}")
    print(f"  → Chunk was {'DROPPED' if token1[0] is None else 'EMITTED'}")
    print()

    # Scenario 2: reasoning_content="" + content="Hello"
    # Should this work? Let's see
    print("Scenario 2: reasoning_content='' + content='Hello'")
    thinking2, content2, tc2 = [], [], {}
    chunk2 = FakeChunk(FakeDelta(content="Hello", reasoning_content=""))
    thinking2, content2, tc2, token2 = process_chunk(chunk2, thinking2, content2, tc2)
    print(f"  thinking={thinking2} content={content2} token={token2}")
    print(f"  → 'Hello' was {'DROPPED' if token2[0] is None else 'EMITTED'}")
    print()

    # Scenario 3: reasoning_content="" + content=""  (both empty strings)
    print("Scenario 3: reasoning_content='' + content='' (both empty strings)")
    thinking3, content3, tc3 = [], [], {}
    chunk3 = FakeChunk(FakeDelta(content="", reasoning_content=""))
    thinking3, content3, tc3, token3 = process_chunk(chunk3, thinking3, content3, tc3)
    print(f"  thinking={thinking3} content={content3} token={token3}")
    print(f"  → Chunk was {'DROPPED' if token3[0] is None else 'EMITTED'}")
    print()

    # Scenario 4: The REAL bug — tool_calls with reasoning_content=""
    # When the model emits tool_calls, the process_chunk goes to the tool_calls branch
    # and IGNORES reasoning_content and content entirely
    print("Scenario 4: tool_calls + reasoning_content='' (both present)")
    thinking4, content4, tc4 = [], [], {}
    delta4 = FakeDelta(
        content=None,
        reasoning_content="",
        tool_calls=[FakeToolCall(index=0, id="call_123", function=FakeFunction(name="search", arguments=None))]
    )
    chunk4 = FakeChunk(delta4)
    thinking4, content4, tc4, token4 = process_chunk(chunk4, thinking4, content4, tc4)
    print(f"  thinking={thinking4} content={content4} token={token4}")
    print(f"  reasoning_content='' was {'IGNORED (tool_calls branch)' if token4[0] != 'thinking' else 'EMITTED'}")
    print()

    # Scenario 5: Multi-chunk transition — what actually happens in practice
    print("Scenario 5: Multi-chunk sequence (realistic stream)")
    thinking5, content5, tc5 = [], [], {}
    all_tokens_5 = []

    # Chunk A: Last reasoning token
    chunkA = FakeChunk(FakeDelta(content=None, reasoning_content="So the answer is "))
    thinking5, content5, tc5, tokA = process_chunk(chunkA, thinking5, content5, tc5)
    all_tokens_5.append(("A", tokA))

    # Chunk B: Transition — reasoning_content="" + content=None
    chunkB = FakeChunk(FakeDelta(content=None, reasoning_content=""))
    thinking5, content5, tc5, tokB = process_chunk(chunkB, thinking5, content5, tc5)
    all_tokens_5.append(("B", tokB))

    # Chunk C: First content token
    chunkC = FakeChunk(FakeDelta(content="France", reasoning_content=None))
    thinking5, content5, tc5, tokC = process_chunk(chunkC, thinking5, content5, tc5)
    all_tokens_5.append(("C", tokC))

    # Chunk D: More content
    chunkD = FakeChunk(FakeDelta(content=" president", reasoning_content=None))
    thinking5, content5, tc5, tokD = process_chunk(chunkD, thinking5, content5, tc5)
    all_tokens_5.append(("D", tokD))

    for label, tok in all_tokens_5:
        print(f"  Chunk {label}: token={tok}")
    print(f"  Final thinking: {''.join(thinking5)}")
    print(f"  Final content: {''.join(content5)}")
    dropped_labels = [l for l, t in all_tokens_5 if t[0] is None]
    if dropped_labels:
        print(f"  ⚠ Dropped chunks: {dropped_labels}")
    else:
        print(f"  ✓ No dropped chunks")
    print()

    # ── The actual fix ──
    print("=" * 70)
    print("PROPOSED FIX")
    print("=" * 70)
    print()
    print("The fix: check `is not None` instead of truthiness for reasoning_content:")
    print()
    print("  BEFORE:")
    print("    reasoning_chunk = getattr(delta, 'reasoning_content', None)")
    print("    if reasoning_chunk:  # '' is falsy → falls to content branch")
    print()
    print("  AFTER:")
    print("    reasoning_chunk = getattr(delta, 'reasoning_content', None)")
    print("    if reasoning_chunk is not None:  # '' is explicitly handled")
    print("        thinking.append(reasoning_chunk)  # appends '' (harmless)")
    print("        new_token = ('thinking', reasoning_chunk)")
    print("    else:")
    print("        verbal_chunk = delta.content")
    print("        if verbal_chunk:")
    print("            content.append(verbal_chunk)")
    print("            new_token = ('content', verbal_chunk)")
    print()
    print("This ensures the reasoning→content boundary is explicit and")
    print("no chunks are silently dropped due to empty-string falsiness.")


if __name__ == "__main__":
    asyncio.run(main())
