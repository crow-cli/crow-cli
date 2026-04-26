"""Smoke test: ReplClient -> repl-agent main.py, verify conversation state."""

import asyncio

from client import ReplClient

AGENT_CMD = "uv"
AGENT_ARGS = (
    "--project",
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent",
    "run",
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/scratch_db.py",
)


async def test():
    c = ReplClient(AGENT_CMD, *AGENT_ARGS)
    d = ReplClient(AGENT_CMD, *AGENT_ARGS)
    e = ReplClient(AGENT_CMD, *AGENT_ARGS)

    compact_prompt = (
        "Summarize the conversation in RESTful markdown format and the "
        "steps you have taken, This is an interagent summary/compaction "
        "event. Respond directly. Call no tools"
    )
    c_prompt = (
        "investigate agent client protocol on internet and give your "
        "assessment of its current and future potential. "
    )
    await c.send(c_prompt)
    await c.send(compact_prompt)

    print("\n=== Conversation State ===")
    conversation = c.conversation.get(c._session_id, [])
    last_message = conversation[-1]["content"]
    d_prompt = (
        "You have been given a summary of the previous actions "
        "of another agent. Please evaluate the actions of that agent "
        "for correctness against the original request.\n"
        f"original request:\n{c_prompt}\n"
        "Here is the summary of the actions it took \n"
        f"agent summary:\n{last_message}\n"
    )
    print(last_message)
    await d.send(d_prompt)
    await d.send(compact_prompt)
    d_conversation = d.conversation.get(d._session_id, [])
    d_last_message = d_conversation[-1]["content"]

    e_prompt = (
        "You have been given a summary of the previous actions "
        "of another agent. Please evaluate the actions of that agent "
        "for correctness against the original request.\n"
        f"original request:\n{d_prompt}\n"
        "Here is the summary of the actions it took \n"
        f"agent summary:\n{d_last_message}\n"
        "ACTUAL TASK:\n"
        "But I don't really care about that. "
        "I want you to look at run_repl_client.py, which "
        "is the file that has invoked all three of the previous agents. "
        "Express appropriate shock and awe"
    )
    await e.send(e_prompt)
    await e.send(compact_prompt)
    e_conversation = e.conversation.get(e._session_id, [])
    e_last_message = e_conversation[-1]["content"]
    print(e_last_message)
    await c.close()
    await d.close()
    await e.close()


asyncio.run(test())
