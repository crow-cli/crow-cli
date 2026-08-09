"""
Test simple agent directly.
"""

import asyncio
import sys
from pathlib import Path
from typing import Any

from acp import spawn_agent_process, text_block
from acp.interfaces import Client


class TestClient(Client):
    async def request_permission(self, options, session_id, tool_call, **kwargs: Any):
        return {"outcome": {"outcome": "cancelled"}}

    async def session_update(self, session_id, update, **kwargs):
        print(f"UPDATE: {update}")


async def main():
    agent_path = Path(__file__).parent / "simple_agent.py"

    print(f"Testing simple agent: {agent_path}")

    async with spawn_agent_process(
        TestClient(),
        "uv",
        "--project",
        str(agent_path.parent),
        "run",
        str(agent_path),
        cwd=str(agent_path.parent),
    ) as (conn, proc):
        print(f"✓ Simple agent spawned (PID: {proc.pid})")

        # Initialize
        print("\n→ Initializing...")
        init_response = await conn.initialize(protocol_version=1)
        print(f"✓ Initialized: {init_response}")

        # Create session
        print("\n→ Creating session...")
        session = await conn.new_session(cwd=str(agent_path.parent), mcp_servers=[])
        print(f"✓ Session created: {session.session_id}")

        # Send prompt
        print("\n→ Sending prompt: 'Hello!'")
        response = await conn.prompt(
            session_id=session.session_id,
            prompt=[text_block("Hello!")],
        )
        print(f"✓ Response: {response}")


if __name__ == "__main__":
    asyncio.run(main())
