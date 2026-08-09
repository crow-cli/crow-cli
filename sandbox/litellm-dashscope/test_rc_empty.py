#!/usr/bin/env python3
"""
DEFINITIVE: reasoning_content="" analysis across all providers.

RESULTS (verified with real API calls):
========================================
Model                          | rc='' count | Transition rc type | Safe?
-------------------------------|-------------|-------------------|-------
qwen3.6-plus (DashScope)       | 0           | None              | YES
kimi-k2.5 (DashScope)          | 0           | None              | YES
glm-5 (DashScope)              | 0           | None              | YES
Qwen3.6-35B-A3B (llamacpp)     | 0           | None              | YES
(though llamacpp may put ALL output in reasoning_content)

CONCLUSION:
===========
No model we tested emits reasoning_content="". The transition is always
rc=text → rc=None + content=text. The current process_chunk code handles
this correctly.

HOWEVER, the user reports seeing reasoning_content="" causing token loss.
If this happens, it would be because:
  1. A model NOT in our test set emits rc=""
  2. LiteLLM transforms the response differently for some routing config
  3. A future model update changes behavior

SAFEST FIX (if rc="" ever appears):
=====================================
  In process_chunk, replace:
      if reasoning_chunk:
  with:
      if reasoning_chunk is not None and reasoning_chunk != "":

  This treats rc="" as a transition marker (skip it) but still checks
  content in the same chunk. This is Fix C from test_fix_correctness.py.

RUN THIS SCRIPT to verify with any model:
  cd sandbox/litellm-dashscope && uv --project . run python3 test_rc_empty.py [model] [provider]

Or just accept the finding: no rc="" in current models, but add a
defensive check anyway since it costs nothing.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "crow-cli" / "src"))

from crow_cli.agent.configure import Config, get_default_config_dir


async def main():
    if len(sys.argv) < 3:
        print("Usage: test_rc_empty.py <model> <provider>")
        print("  provider: litellm | llamacpp")
        print()
        print("Example: test_rc_empty.py qwen3.6-plus litellm")
        sys.exit(1)

    model = sys.argv[1]
    provider_name = sys.argv[2]

    config_dir = get_default_config_dir()
    config = Config.load(config_dir=config_dir)
    provider = config.llm.providers[provider_name]

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=provider.api_key, base_url=provider.base_url)

    messages = [
        {"role": "system", "content": "Think step by step, then answer concisely."},
        {"role": "user", "content": "Who is the president of France?"},
    ]

    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
    )

    print(f"Model: {model} (provider: {provider_name})")
    print(f"Base URL: {provider.base_url}")
    print()

    from crow_cli.agent.react import process_chunk
    thinking = []
    content = []
    tool_calls = {}
    rc_empty_seen = False
    transition_info = None

    async for chunk in response:
        if hasattr(chunk, "usage") and chunk.usage is not None:
            continue
        if not chunk.choices or len(chunk.choices) == 0:
            continue

        delta = chunk.choices[0].delta
        rc = getattr(delta, "reasoning_content", None)
        dc = delta.content

        # Detect rc = ""
        if isinstance(rc, str) and rc == "":
            rc_empty_seen = True
            print(f"⚠️  reasoning_content='' detected! dc={dc!r} tool_calls={bool(delta.tool_calls)}")

        # Detect transition
        if transition_info is None and dc and not delta.tool_calls and len(thinking) > 0:
            transition_info = {"rc": rc, "rc_type": type(rc).__name__, "dc": dc}

        thinking, content, tool_calls, _ = process_chunk(chunk, thinking, content, tool_calls)

    print()
    print(f"thinking chars: {len(''.join(thinking))}")
    print(f"content chars: {len(''.join(content))}")
    print(f"tool_calls: {len(tool_calls)}")
    print()

    if rc_empty_seen:
        print("⚠️  MODEL EMITS reasoning_content='' — FIX NEEDED")
        print()
        print("Apply this patch to process_chunk in react.py:")
        print()
        print("    reasoning_chunk = getattr(delta, 'reasoning_content', None)")
        print("    if reasoning_chunk is not None and reasoning_chunk != '':")
        print("        thinking.append(reasoning_chunk)")
        print("        new_token = ('thinking', reasoning_chunk)")
        print("    else:")
        print("        verbal_chunk = delta.content")
        print("        if verbal_chunk:")
        print("            content.append(verbal_chunk)")
        print("            new_token = ('content', verbal_chunk)")
    else:
        print("✓ MODEL does NOT emit reasoning_content=''")
        if transition_info:
            print(f"  Transition: rc type={transition_info['rc_type']}, rc={transition_info['rc']!r}, dc={transition_info['dc']!r}")


if __name__ == "__main__":
    asyncio.run(main())
