"""
Test client that spawns agent-client and talks to it.

Usage:
    python fire_up_echo.py /path/to/agent_client.py
"""

import asyncio
import sys
from pathlib import Path
from typing import Any

from acp import spawn_agent_process, text_block
from acp.interfaces import Client


class TestClient(Client):
    """Simple test client that prints updates."""

    async def request_permission(self, options, session_id, tool_call, **kwargs: Any):
        print(f"PERMISSION REQUEST: {tool_call}")
        return {"outcome": {"outcome": "cancelled"}}

    async def session_update(self, session_id, update, **kwargs):
        print(f"SESSION UPDATE: {session_id}")
        print(f"  {update}")


async def main():
    if len(sys.argv) < 2:
        print("Usage: python fire_up_echo.py /path/to/agent_client.py")
        sys.exit(1)

    agent_path = Path(sys.argv[1])
    print(f"Testing agent-client: {agent_path}")

    # Spawn agent-client as subprocess
    async with spawn_agent_process(
        TestClient(),
        "uv",
        "--project",
        str(agent_path.parent),
        "run",
        str(agent_path),
        cwd=str(agent_path.parent),
    ) as (conn, proc):
        print(f"✓ Agent-client spawned (PID: {proc.pid})")

        # Initialize
        print("\n→ Initializing...")
        init_response = await conn.initialize(protocol_version=1)
        print(f"✓ Initialized: {init_response}")

        # Create session
        print("\n→ Creating session...")
        session = await conn.new_session(cwd=str(agent_path.parent), mcp_servers=[])
        print(f"✓ Session created: {session.session_id}")

        # Send prompt
        print("\n→ Sending prompt: 'Hello from test!'")
        response = await conn.prompt(
            session_id=session.session_id,
            prompt=[text_block("Hello from test!")],
        )
        print(f"✓ Response: {response}")

        print("\n✓ Test complete!")


if __name__ == "__main__":
    asyncio.run(main())
