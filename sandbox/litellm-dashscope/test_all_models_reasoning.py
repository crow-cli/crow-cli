#!/usr/bin/env python3
"""
Test reasoning_content="" across ALL available models to find which ones
emit empty-string transition markers.

Run:
  cd sandbox/litellm-dashscope && uv --project . run python3 test_all_models_reasoning.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "crow-cli" / "src"))

from crow_cli.agent.configure import Config, get_default_config_dir
from crow_cli.agent.react import process_chunk


async def test_model(client, model_name):
    """Test a single model for reasoning_content behavior."""
    messages = [
        {"role": "system", "content": "Think step by step, then answer."},
        {"role": "user", "content": "Who invented the telephone?"},
    ]

    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            max_tokens=200,  # Keep it short
        )
    except Exception as e:
        return {"error": str(e)}

    thinking = []
    content = []
    tool_calls = {}
    rc_empty_count = 0
    rc_empty_samples = []
    transition_rc = None  # rc value at the transition chunk
    transition_dc = None  # content value at the transition chunk
    first_content_chunk = None
    last_reasoning_chunk = None
    total_chunks = 0

    async for chunk in response:
        if hasattr(chunk, "usage") and chunk.usage is not None:
            continue
        if not chunk.choices or len(chunk.choices) == 0:
            continue

        total_chunks += 1
        delta = chunk.choices[0].delta
        rc = getattr(delta, "reasoning_content", None)
        dc = delta.content
        has_tc = bool(delta.tool_calls)

        # Track empty string rc
        if isinstance(rc, str) and rc == "":
            rc_empty_count += 1
            if len(rc_empty_samples) < 3:
                rc_empty_samples.append(f"chunk #{total_chunks}: dc={dc!r} tool_calls={has_tc}")

        # Track transitions
        if first_content_chunk is None and dc and not has_tc:
            first_content_chunk = total_chunks
            transition_rc = rc
            transition_dc = dc

        if not has_tc:
            if isinstance(rc, str) and rc:
                last_reasoning_chunk = rc[-50:] if len(rc) > 50 else rc

        old_t = len(thinking)
        old_c = len(content)
        thinking, content, tool_calls, _ = process_chunk(chunk, thinking, content, tool_calls)

    return {
        "total_chunks": total_chunks,
        "thinking_len": len("".join(thinking)),
        "content_len": len("".join(content)),
        "tool_calls": len(tool_calls),
        "rc_empty_count": rc_empty_count,
        "rc_empty_samples": rc_empty_samples,
        "transition_rc_type": type(transition_rc).__name__,
        "transition_rc": repr(transition_rc),
        "transition_dc": repr(transition_dc),
        "first_content_chunk": first_content_chunk,
        "last_reasoning": repr(last_reasoning_chunk),
    }


async def main():
    from openai import AsyncOpenAI
    from crow_cli.agent.configure import Config, get_default_config_dir

    # Test through LiteLLM proxy
    config_dir = get_default_config_dir()
    config = Config.load(config_dir=config_dir)

    litellm = config.llm.providers["litellm"]
    client_litellm = AsyncOpenAI(api_key=litellm.api_key, base_url=litellm.base_url)

    # Test through llamacpp
    llamacpp = config.llm.providers["llamacpp"]
    client_llamacpp = AsyncOpenAI(api_key=llamacpp.api_key, base_url=llamacpp.base_url)

    # Models to test
    models_litellm = ["qwen3.6-plus", "kimi-k2.5", "glm-5"]
    models_llamacpp = ["unsloth/Qwen3.6-35B-A3B-GGUF:Q8_0"]

    print("=" * 70)
    print("REASONING_CONTENT EMPTY-STRING SCAN — ALL MODELS")
    print("=" * 70)
    print()

    # Test LiteLLM models
    for model in models_litellm:
        print(f"\n--- LiteLLM: {model} ---")
        result = await test_model(client_litellm, model)

        if "error" in result:
            print(f"  ERROR: {result['error']}")
            continue

        print(f"  Chunks: {result['total_chunks']}")
        print(f"  Thinking: {result['thinking_len']} chars, Content: {result['content_len']} chars")
        print(f"  rc='' count: {result['rc_empty_count']}")
        if result['rc_empty_samples']:
            for s in result['rc_empty_samples']:
                print(f"    {s}")
        print(f"  Transition chunk (first content): #{result['first_content_chunk']}")
        print(f"    rc type at transition: {result['transition_rc_type']}")
        print(f"    rc value at transition: {result['transition_rc']}")
        print(f"    content value at transition: {result['transition_dc']}")
        print(f"    Last reasoning: ...{result['last_reasoning']}")

    # Test llamacpp models
    for model in models_llamacpp:
        print(f"\n--- llamacpp: {model} ---")
        result = await test_model(client_llamacpp, model)

        if "error" in result:
            print(f"  ERROR: {result['error']}")
            continue

        print(f"  Chunks: {result['total_chunks']}")
        print(f"  Thinking: {result['thinking_len']} chars, Content: {result['content_len']} chars")
        print(f"  rc='' count: {result['rc_empty_count']}")
        if result['rc_empty_samples']:
            for s in result['rc_empty_samples']:
                print(f"    {s}")
        print(f"  Transition chunk (first content): #{result['first_content_chunk']}")
        print(f"    rc type at transition: {result['transition_rc_type']}")
        print(f"    rc value at transition: {result['transition_rc']}")
        print(f"    content value at transition: {result['transition_dc']}")
        print(f"    Last reasoning: ...{result['last_reasoning']}")

    print()
    print("=" * 70)
    print("CONCLUSION")
    print("=" * 70)
    print()
    print("If ANY model shows rc='' count > 0, that model emits empty-string")
    print("transition markers and the process_chunk code needs to handle them.")
    print()
    print("If rc value at transition is None, the current code is safe.")
    print("If rc value at transition is '' (empty string), the current code")
    print("drops that chunk (but may not lose data if next chunk has content).")


if __name__ == "__main__":
    asyncio.run(main())
