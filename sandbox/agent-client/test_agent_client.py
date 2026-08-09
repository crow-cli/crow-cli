"""
Test the agent-client end-to-end.

This spawns agent_client.py (which spawns bridge + echo_agent internally)
and tests the full flow:
    Test Client → agent_client → bridge → echo_agent
"""

import asyncio
from pathlib import Path
from typing import Any

from acp import spawn_agent_process, text_block
from acp.interfaces import Client


class TestClient(Client):
    """Simple test client."""

    async def request_permission(self, options, session_id, tool_call, **kwargs: Any):
        print(f"  PERMISSION REQUEST: {tool_call}")
        return {"outcome": {"outcome": "cancelled"}}

    async def session_update(self, session_id, update, **kwargs):
        print(f"  UPDATE: {update}")


async def main():
    agent_path = Path(__file__).parent / "agent_client.py"

    print("=" * 60)
    print("TEST: Full Stack (Client → agent_client → bridge → echo)")
    print("=" * 60)

    print(f"\n→ Spawning agent-client: {agent_path}")

    # Spawn agent-client (which internally spawns bridge + echo_agent)
    async with spawn_agent_process(
        TestClient(),
        "uv",
        "--project",
        str(agent_path.parent),
        "run",
        str(agent_path),
        cwd=str(agent_path.parent),
    ) as (conn, proc):
        print(f"✓ Agent-client spawned (PID: {proc.pid})\n")

        # Wait for it to initialize (bridge + echo_agent spawn)
        await asyncio.sleep(3)

        # Initialize
        print("→ Initializing...")
        init_response = await conn.initialize(protocol_version=1)
        print(f"✓ Initialized: {init_response}\n")

        # Create session
        print("→ Creating session...")
        session = await conn.new_session(cwd=str(agent_path.parent), mcp_servers=[])
        print(f"✓ Session created: {session.session_id}\n")

        # Send prompt
        print("→ Sending prompt: 'Hello through the bridge!'")
        response = await conn.prompt(
            session_id=session.session_id,
            prompt=[text_block("Hello through the bridge!")],
        )
        print(f"✓ Response: {response}\n")

        print("✓ All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
