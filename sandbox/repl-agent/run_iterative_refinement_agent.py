"""Smoke test: spawn an agent with the iterative-refinement MCP server attached,
ask it to create a calculator module, and print what the agent got back.

Usage:
    cd /home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent
    uv --project . run run_iterative_refinement_agent.py
"""

import asyncio
from rich.console import Console
from rich.panel import Panel

from client import ReplClient, stdio_mcp

AGENT_CMD = "uv"
AGENT_ARGS = (
    "--project",
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent",
    "run",
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/scratch_db.py",
)

REFINEMENT_MCP = stdio_mcp(
    "iterative-refinement",
    AGENT_CMD,
    "--project",
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent",
    "run",
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/iterative_refinement_mcp.py",
)

CWD = "/tmp/calculator"

TASK_PROMPT = (
    f"You are in {CWD}. Use the iterative-refinement_refine tool to "
    f"create a Python calculator module there with these criteria:\n"
    f"- All four operations (add, subtract, multiply, divide) as functions\n"
    f"- Division by zero raises ValueError with a clear message\n"
    f"- Functions are type-hinted and have docstrings\n"
    f"- A __main__ block provides a simple CLI demo\n"
    f"Use max_iterations of 2."
)


def get_last_assistant(client: ReplClient) -> str:
    """Return the last assistant message content, or '(none)'."""
    conversation = client.conversation.get(client.session_id, [])
    for msg in reversed(conversation):
        if msg["role"] == "assistant" and msg.get("content"):
            return msg["content"]
    return "(none)"


async def main():
    console = Console()

    client = ReplClient(
        AGENT_CMD,
        *AGENT_ARGS,
        mcp_servers=[REFINEMENT_MCP],
        cwd=CWD,
    )

    await client.send(TASK_PROMPT)

    response = get_last_assistant(client)
    console.print()
    console.print(
        Panel(
            response,
            title="[green]Agent Response[/green]",
            border_style="green",
        )
    )

    # Also show conversation length for debugging
    count = len(client.conversation.get(client.session_id, []))
    console.print(f"\n[dim]Conversation messages: {count}[/dim]")
    for msg in client.conversation.get(client.session_id, []):
        preview = msg["content"][:80] + "..." if len(msg["content"]) > 80 else msg["content"]
        console.print(f"[dim]  {msg['role']}: {preview}[/dim]")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
