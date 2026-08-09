"""
Test the echo agent directly (without agent-client).
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
        print(f"UPDATE: {session_id} {update}")


async def main():
    echo_agent = Path(__file__).parent / "echo_agent.py"

    print(f"Testing echo agent: {echo_agent}")

    async with spawn_agent_process(TestClient(), "uv", "run", str(echo_agent)) as (
        conn,
        proc,
    ):
        print("Connected to echo agent")

        # Initialize
        init_response = await conn.initialize(protocol_version=1)
        print(f"Initialized: {init_response}")

        # Create session
        session = await conn.new_session(cwd=str(echo_agent.parent), mcp_servers=[])
        print(f"Session created: {session.session_id}")

        # Send prompt
        print("Sending prompt...")
        response = await conn.prompt(
            session_id=session.session_id,
            prompt=[text_block("Hello from test!")],
        )
        print(f"Response: {response}")


if __name__ == "__main__":
    asyncio.run(main())
