#!/usr/bin/env python3
"""
Find the correct fix for reasoning_content="" handling.

The problem space:
  - reasoning_content="" could be a transition marker (reasoning ended)
  - reasoning_content=None means "no reasoning field in this chunk"
  - content could appear simultaneously or in the next chunk

We need to figure out: does DashScope ever send reasoning_content="" AND
content="something" in the same chunk? If so, the naive "is not None" fix
will lose content.

Run:
  cd sandbox/litellm-dashscope && uv --project . run python3 test_fix_correctness.py
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "crow-cli" / "src"))

from crow_cli.agent.configure import Config, get_default_config_dir


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
    def __init__(self, content=None, reasoning_content=None, tool_calls=None):
        self.content = content
        self.reasoning_content = reasoning_content
        self.tool_calls = tool_calls


class FakeChoice:
    def __init__(self, delta):
        self.delta = delta


class FakeChunk:
    def __init__(self, delta):
        self.choices = [FakeChoice(delta)]
        self.usage = None


def process_chunk_original(chunk, thinking, content, tool_calls):
    """Current production code."""
    if not chunk.choices or len(chunk.choices) == 0:
        return thinking, content, tool_calls, (None, None)

    delta = chunk.choices[0].delta
    new_token = (None, None)

    if not delta.tool_calls:
        reasoning_chunk = getattr(delta, "reasoning_content", None)
        if reasoning_chunk:
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
                new_token = ("tool_call", (call.function.name, call.function.arguments or ""))
            if call.function and call.function.arguments:
                arg_fragment = call.function.arguments
                tool_calls[index]["arguments"].append(arg_fragment)
                if new_token[0] != "tool_call":
                    new_token = ("tool_args", arg_fragment)

    return thinking, content, tool_calls, new_token


def process_chunk_fix_a(chunk, thinking, content, tool_calls):
    """Fix A: 'is not None' — treats '' as explicit reasoning."""
    if not chunk.choices or len(chunk.choices) == 0:
        return thinking, content, tool_calls, (None, None)

    delta = chunk.choices[0].delta
    new_token = (None, None)

    if not delta.tool_calls:
        reasoning_chunk = getattr(delta, "reasoning_content", None)
        if reasoning_chunk is not None:  # <-- CHANGE
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
                new_token = ("tool_call", (call.function.name, call.function.arguments or ""))
            if call.function and call.function.arguments:
                arg_fragment = call.function.arguments
                tool_calls[index]["arguments"].append(arg_fragment)
                if new_token[0] != "tool_call":
                    new_token = ("tool_args", arg_fragment)

    return thinking, content, tool_calls, new_token


def process_chunk_fix_b(chunk, thinking, content, tool_calls):
    """Fix B: Check both — if reasoning_content is present (even ''), process it,
    then ALSO check content in the same chunk."""
    if not chunk.choices or len(chunk.choices) == 0:
        return thinking, content, tool_calls, (None, None)

    delta = chunk.choices[0].delta
    new_token = (None, None)

    if not delta.tool_calls:
        reasoning_chunk = getattr(delta, "reasoning_content", None)
        verbal_chunk = delta.content

        if reasoning_chunk is not None:
            thinking.append(reasoning_chunk)
            new_token = ("thinking", reasoning_chunk)

        # Also check content in the same chunk (handles rc='' + content='Hello')
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
                new_token = ("tool_call", (call.function.name, call.function.arguments or ""))
            if call.function and call.function.arguments:
                arg_fragment = call.function.arguments
                tool_calls[index]["arguments"].append(arg_fragment)
                if new_token[0] != "tool_call":
                    new_token = ("tool_args", arg_fragment)

    return thinking, content, tool_calls, new_token


def process_chunk_fix_c(chunk, thinking, content, tool_calls):
    """Fix C: '' is a no-op transition marker — skip it but fall through to content."""
    if not chunk.choices or len(chunk.choices) == 0:
        return thinking, content, tool_calls, (None, None)

    delta = chunk.choices[0].delta
    new_token = (None, None)

    if not delta.tool_calls:
        reasoning_chunk = getattr(delta, "reasoning_content", None)
        verbal_chunk = delta.content

        if reasoning_chunk:
            # Normal reasoning token
            thinking.append(reasoning_chunk)
            new_token = ("thinking", reasoning_chunk)
        elif reasoning_chunk is not None:
            # reasoning_chunk == "" — transition marker, skip but check content
            if verbal_chunk:
                content.append(verbal_chunk)
                new_token = ("content", verbal_chunk)
        else:
            # reasoning_chunk is None
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
                new_token = ("tool_call", (call.function.name, call.function.arguments or ""))
            if call.function and call.function.arguments:
                arg_fragment = call.function.arguments
                tool_calls[index]["arguments"].append(arg_fragment)
                if new_token[0] != "tool_call":
                    new_token = ("tool_args", arg_fragment)

    return thinking, content, tool_calls, new_token


def run_sequence(chunks, process_fn):
    """Run a sequence of chunks through a process_chunk variant."""
    thinking = []
    content = []
    tool_calls = {}
    tokens = []

    for chunk in chunks:
        thinking, content, tool_calls, new_token = process_fn(chunk, thinking, content, tool_calls)
        tokens.append(new_token)

    return {
        "thinking": "".join(thinking),
        "content": "".join(content),
        "tool_calls": len(tool_calls),
        "tokens": tokens,
    }


def main():
    print("=" * 70)
    print("FIX CORRECTNESS TEST")
    print("=" * 70)
    print()

    # Define test sequences that mimic real API behavior
    sequences = {
        "Normal reasoning→content (no empty marker)": [
            FakeChunk(FakeDelta(reasoning_content="Hmm, ")),
            FakeChunk(FakeDelta(reasoning_content="let me think.")),
            FakeChunk(FakeDelta(reasoning_content=None, content="The answer is")),
            FakeChunk(FakeDelta(reasoning_content=None, content=" 42.")),
        ],
        "Empty-string transition marker (rc='' then content)": [
            FakeChunk(FakeDelta(reasoning_content="Thinking...")),
            FakeChunk(FakeDelta(reasoning_content="", content=None)),  # transition
            FakeChunk(FakeDelta(reasoning_content=None, content="Hello world")),
        ],
        "Simultaneous rc='' + content (potential DashScope behavior)": [
            FakeChunk(FakeDelta(reasoning_content="Almost done")),
            FakeChunk(FakeDelta(reasoning_content="", content="Done!")),  # both present
        ],
        "Reasoning→tool_calls": [
            FakeChunk(FakeDelta(reasoning_content="I should search")),
            FakeChunk(FakeDelta(
                reasoning_content=None,
                content=None,
                tool_calls=[FakeToolCall(index=0, id="call_1", function=FakeFunction(name="search"))]
            )),
            FakeChunk(FakeDelta(
                tool_calls=[FakeToolCall(index=0, function=FakeFunction(arguments='{"q":"hi"}'))]
            )),
        ],
        "rc='' with tool_calls (edge case)": [
            FakeChunk(FakeDelta(reasoning_content="Need to search")),
            FakeChunk(FakeDelta(
                reasoning_content="",
                tool_calls=[FakeToolCall(index=0, id="call_1", function=FakeFunction(name="search"))]
            )),
        ],
    }

    variants = {
        "Original": process_chunk_original,
        "Fix A (is not None)": process_chunk_fix_a,
        "Fix B (both fields)": process_chunk_fix_b,
        "Fix C (skip '', check content)": process_chunk_fix_c,
    }

    for seq_name, chunks in sequences.items():
        print(f"Sequence: {seq_name}")
        print("-" * 70)

        results = {}
        for name, fn in variants.items():
            results[name] = run_sequence(chunks, fn)

        # Check if all variants produce the same result
        thinking_vals = {name: r["thinking"] for name, r in results.items()}
        content_vals = {name: r["content"] for name, r in results.items()}

        thinking_unique = len(set(thinking_vals.values())) == 1
        content_unique = len(set(content_vals.values())) == 1

        for name, r in results.items():
            marker = ""
            if not thinking_unique or not content_unique:
                # Highlight differences
                if r["thinking"] != list(results.values())[0]["thinking"]:
                    marker += " ✗thinking"
                if r["content"] != list(results.values())[0]["content"]:
                    marker += " ✗content"

            print(f"  {name:<30} thinking={r['thinking']!r:<30} content={r['content']!r:<20}{marker}")

        if not thinking_unique or not content_unique:
            print("  ⚠️  VARIANTS DISAGREE")
        else:
            print("  ✓ All variants agree")
        print()

    # ── Deep analysis: what is the CORRECT behavior? ──
    print("=" * 70)
    print("CORRECTNESS ANALYSIS")
    print("=" * 70)
    print()

    print("The critical question: What does DashScope/qwen actually emit?")
    print()
    print("From our real API tests:")
    print("  1. Simple prompt: reasoning→content went from rc=text → rc=None+content=text")
    print("     No rc='' transition marker was observed.")
    print("  2. Tool-calling prompt: reasoning→tools went from rc=text → rc=None+tc=[...]")
    print("     No rc='' transition marker was observed.")
    print()
    print("So the rc='' case may NOT occur with qwen3.6-plus through LiteLLM.")
    print("But the user reports it happening — maybe with a different model or config.")
    print()

    print("What SHOULD happen for each case:")
    print()
    print("  Case 1: rc='text' + content=None")
    print("    → thinking += 'text'  (obvious)")
    print()
    print("  Case 2: rc=None + content='text'")
    print("    → content += 'text'  (obvious)")
    print()
    print("  Case 3: rc='' + content=None")
    print("    → This is a TRANSITION MARKER. Should either:")
    print("      a) Do nothing (skip it, next chunk has content)")
    print("      b) Append '' to thinking (harmless but noisy)")
    print("    Original: does nothing (correct if next chunk has content)")
    print("    Fix A: appends '' to thinking (harmless)")
    print()
    print("  Case 4: rc='' + content='text'  ← THE DANGEROUS CASE")
    print("    → If rc='' means 'reasoning ended AND here's first content':")
    print("      content += 'text'  (we MUST not lose this)")
    print("    Original: content += 'text'  ✓ (rc='' is falsy, falls to content branch)")
    print("    Fix A: thinking += '' ✗ (loses content!)")
    print("    Fix B: thinking += '' AND content += 'text' ✓ (captures both)")
    print("    Fix C: content += 'text'  ✓ (skips '', falls to content)")
    print()
    print("  Case 5: rc='' + tool_calls=[...]")
    print("    → Goes to tool_calls branch regardless. rc='' is ignored.")
    print("    This is fine because tool_calls branch doesn't check rc/content.")
    print()
    print("VERDICT:")
    print("  - Fix A is WRONG: it loses content when rc='' + content='text'")
    print("  - Fix C is the safest: treats rc='' as transition marker,")
    print("    skips it, and falls through to check content")
    print("  - Fix B is also correct but adds '' to thinking (noisy)")
    print("  - Original is correct for Case 4 but wrong for Case 3 if")
    print("    rc='' appears without a following content chunk")
    print()

    # ── Multi-chunk integrity test ──
    print("=" * 70)
    print("MULTI-CHUNK INTEGRITY — simulating real stream with rc='' marker")
    print("=" * 70)
    print()

    # Simulate what the user claims happens: rc='' appears but content is lost
    # This would occur if the transition chunk is rc='' with content=None,
    # AND the next chunk is also rc=None with content=None (gap before content starts)
    gap_sequence = [
        FakeChunk(FakeDelta(reasoning_content="Final thought")),
        FakeChunk(FakeDelta(reasoning_content="", content=None)),  # transition
        FakeChunk(FakeDelta(reasoning_content=None, content=None)),  # gap
        FakeChunk(FakeDelta(reasoning_content=None, content="Hello")),
    ]

    print("Sequence: reasoning → rc='' → gap (rc=None, content=None) → content='Hello'")
    print()

    for name, fn in variants.items():
        result = run_sequence(gap_sequence, fn)
        print(f"  {name:<30} thinking={result['thinking']!r:<25} content={result['content']!r}")

    print()
    print("All variants correctly capture 'Hello' — the gap chunk is harmless")
    print("because rc=None + content=None is correctly dropped by all variants.")
    print()

    # ── The REAL bug scenario ──
    print("=" * 70)
    print("THE REAL BUG: where does the user see token loss?")
    print("=" * 70)
    print()
    print("If the user sees token loss at the reasoning→content boundary,")
    print("it's NOT because of rc='' being falsy (we proved that above).")
    print()
    print("Possible actual causes:")
    print("  1. LiteLLM proxy strips or transforms rc/content fields")
    print("  2. The chunk with rc=None + content='first_token' is dropped elsewhere")
    print("  3. The model emits rc='' + content='' (both empty) as a transition,")
    print("     and the NEXT chunk's content is lost due to buffering")
    print("  4. Something in the session persistence layer drops tokens")
    print()
    print("Recommendation: add chunk-level logging in production to see")
    print("exactly what deltas arrive at the reasoning→content boundary.")


if __name__ == "__main__":
    main()
