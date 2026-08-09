"""
Tool usage audit test: Launch an ACP agent, send it a codebase exploration task,
and report which commands it actually used (rg vs find vs ls vs tree vs read-on-dir).
"""

import asyncio
import re

import typer

from client import ReplClient

app = typer.Typer()

AGENT_CMD = "uv"
AGENT_ARGS = (
    "--project",
    "/home/thomas/src/crow-ai/crow-cli/crow-cli",
    "run",
    "crow-cli",
    "acp",
)
# AGENT_ARGS = (
#     "--project",
#     "/Users/thomas/src/crow-ai/crow-cli/crow-cli",
#     "run",
#     "crow-cli",
#     "acp",
#     "--debug",
# )


class AuditReplClient(ReplClient):
    """ReplClient that tracks tool calls for auditing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tool_calls = []  # List of tool names called

    async def session_update(self, session_id, update, **kwargs):
        # Intercepts tool call updates
        from acp.schema import AgentMessageChunk, AgentThoughtChunk, ToolCallStart

        if isinstance(update, ToolCallStart):
            self.tool_calls.append(update.title or "unknown")
        await super().session_update(session_id, update, **kwargs)


def analyze_usage(client: AuditReplClient):
    """Analyze which tools were used and report."""
    tools = client.tool_calls
    if not tools:
        print("\n=== NO TOOL CALLS DETECTED ===")
        return

    # Categorize
    rg_used = any("rg" in t.lower() for t in tools)
    find_used = any("find" in t.lower() for t in tools)
    ls_used = any("ls" in t.lower() for t in tools)
    tree_used = any("tree" in t.lower() for t in tools)
    read_used = any("read" in t.lower() for t in tools)
    write_used = any("write" in t.lower() for t in tools)

    print("\n" + "=" * 60)
    print("TOOL USAGE AUDIT")
    print("=" * 60)
    print(f"\nAll tool calls ({len(tools)}):")
    for t in tools:
        print(f"  - {t}")

    print("\nCommand summary:")
    print(f"  rg:    {'✓ USED' if rg_used else '✗ NOT USED'}")
    print(f"  find:  {'✓ USED' if find_used else '✗ NOT USED'}")
    print(f"  ls:    {'✓ USED' if ls_used else '✗ NOT USED'}")
    print(f"  tree:  {'✓ USED' if tree_used else '✗ NOT USED'}")
    print(f"  read:  {'✓ USED' if read_used else '✗ NOT USED'}")
    print(f"  write: {'✓ USED' if write_used else '✗ NOT USED'}")

    # Check for forbidden patterns
    print("\nCompliance:")
    if find_used:
        print("  ⚠ VIOLATION: Used 'find' instead of 'rg'")
    else:
        print("  ✓ Did NOT use 'find' (good)")

    if rg_used:
        print("  ✓ Used 'rg' (good)")
    else:
        print("  ⚠ Did NOT use 'rg'")

    # Check the actual terminal commands for patterns
    # (The tool name might be "terminal" but the command inside is what matters)
    # We need to check the content of tool calls for the actual commands used


async def run_test(user_prompt: str):
    c = AuditReplClient(AGENT_CMD, *AGENT_ARGS)
    await c.send(user_prompt)

    analyze_usage(c)

    # Print the agent's final response
    print("\n=== AGENT RESPONSE ===")
    conversation = c.conversation.get(c._session_id, [])
    for msg in conversation:
        if msg["role"] == "assistant":
            print(msg.get("content", ""))

    await c.close()


@app.command()
def main(
    user_prompt: str = typer.Argument(
        "Search the internet for agent client protocol",
        help="The prompt to send to the agent",
    ),
):
    """Test REPL client with a user prompt."""
    asyncio.run(run_test(user_prompt))


if __name__ == "__main__":
    app()
