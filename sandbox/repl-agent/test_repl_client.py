"""Smoke test: ReplClient -> repl-agent main.py, verify conversation state."""

import asyncio

from client import ReplClient

AGENT_CMD = "uv"
AGENT_ARGS = (
    "--project",
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent",
    "run",
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/main.py",
)


async def test():
    c = ReplClient(AGENT_CMD, *AGENT_ARGS)
    d = ReplClient(AGENT_CMD, *AGENT_ARGS)

    await c.send("what is agent client protocol?")
    await c.send("do you think it's any good?")
    await c.send(
        "summarize the conversation and the steps you have taken, call no tools. this is an interagent summary/compaction event."
    )

    print("\n=== Conversation State ===")
    conversation = c.conversation.get(c._session_id, [])
    last_message = conversation[-1]["content"]
    print(last_message)
    await d.send(last_message)
    await c.close()
    await d.close()


asyncio.run(test())
