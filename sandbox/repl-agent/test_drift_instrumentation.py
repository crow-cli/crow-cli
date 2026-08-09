"""
Test the react.py instrumentation for token drift detection.

Runs a multi-turn tool-calling conversation through ReplClient,
then checks the agent logs for PAYLOAD and SESSION STATE entries.
"""

import asyncio
import json
import os
from pathlib import Path

from client import ReplClient

AGENT_CMD = "uv"
AGENT_ARGS = (
    "--project",
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent",
    "run",
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/main.py",
)

CROW_LOGS = Path(
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/.crow/logs"
)


def tail_log(session_id: str, lines=50):
    """Tail the crow-cli log for a session."""
    log_dir = Path("/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/.crow/logs")
    log_files = sorted(log_dir.glob("crow-cli-*.log"), key=lambda p: p.stat().st_mtime)
    if not log_files:
        print("  No crow-cli log files found")
        return

    log_file = log_files[-1]
    content = log_file.read_text()
    payload_lines = [l for l in content.split("\n") if "PAYLOAD" in l]
    session_lines = [l for l in content.split("\n") if "SESSION STATE" in l]
    norm_lines = [l for l in content.split("\n") if "normalize_blocks changed" in l]

    print(f"\n{'=' * 60}")
    print(f"INSTRUMENTATION LOGS (from {log_file.name})")
    print(f"{'=' * 60}")

    if payload_lines:
        print(f"\n--- PAYLOAD lines ({len(payload_lines)}) ---")
        for l in payload_lines[-10:]:
            print(f"  {l.strip()}")
    else:
        print("\n  ⚠ No PAYLOAD log lines found — instrumentation NOT firing")

    if session_lines:
        print(f"\n--- SESSION STATE lines ({len(session_lines)}) ---")
        for l in session_lines[-10:]:
            print(f"  {l.strip()}")
    else:
        print("\n  ⚠ No SESSION STATE log lines found — instrumentation NOT firing")

    if norm_lines:
        print(f"\n--- normalize_blocks changes ({len(norm_lines)}) ---")
        for l in norm_lines:
            print(f"  {l.strip()}")

    # Check payload dump files
    payload_files = sorted(
        CROW_LOGS.glob("payload-*.json"), key=lambda p: p.stat().st_mtime
    )
    if payload_files:
        print(f"\n--- Payload dump files ({len(payload_files)}) ---")
        for pf in payload_files[-5:]:
            data = json.loads(pf.read_text())
            total_chars = sum(
                len(str(m.get("content", "")))
                + len(str(m.get("reasoning_content", "")))
                for m in data
            )
            tool_args = sum(
                len(tc["function"]["arguments"])
                for m in data
                for tc in m.get("tool_calls", [])
            )
            print(
                f"  {pf.name}: msgs={len(data)} chars={total_chars} tool_args={tool_args}B"
            )


async def test():
    c = ReplClient(AGENT_CMD, *AGENT_ARGS)

    # Turn 1: Force a search tool call
    await c.send("search for machine learning papers from 2025")

    # Turn 2: Force another search
    await c.send("now search for transformer architecture improvements")

    # Turn 3: Force a web_fetch
    await c.send("fetch the first result URL you found")

    # Turn 4: Force more tools
    await c.send("search for reinforcement learning papers and fetch the top result")

    # Show conversation state (client-side simplified view)
    session_id = c._session_id
    conversation = c.conversation.get(session_id, [])
    print(f"\n{'=' * 60}")
    print(f"CLIENT CONVERSATION STATE (session={session_id})")
    print(f"{'=' * 60}")
    print(f"Client tracked {len(conversation)} messages")
    for i, msg in enumerate(conversation):
        role = msg.get("role", "?")
        content_preview = ""
        if "content" in msg and msg["content"]:
            content_preview = f" content={len(msg['content'])}B"
        if "reasoning_content" in msg and msg["reasoning_content"]:
            content_preview += f" reasoning={len(msg['reasoning_content'])}B"
        # Note: client doesn't track tool_calls!
        print(f"  [{i:02d}] {role}{content_preview}")

    print("\n  ⚠ NOTE: ReplClient does NOT track tool_calls or tool results")
    print("  Client conversation is a SIMPLIFIED view — the full state")
    print("  lives in the agent's Session (persisted in DB)")

    # Check instrumentation
    tail_log(session_id)

    await c.close()


if __name__ == "__main__":
    asyncio.run(test())
