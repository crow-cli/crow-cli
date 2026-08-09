"""
Test WebSocket client using ACP SDK (not reinventing the wheel).

This tests:
1. Bridge is running separately
2. We connect via ACP WebSocket client
3. We use ACP SDK methods, not raw JSON-RPC
"""

import asyncio
from pathlib import Path
from typing import Any

from acp import text_block
from acp.client.websocket_client import WebSocketClient
from acp.interfaces import Client


class TestClient(Client):
    async def request_permission(self, options, session_id, tool_call, **kwargs: Any):
        return {"outcome": {"outcome": "cancelled"}}

    async def session_update(self, session_id, update, **kwargs):
        print(f"  UPDATE: {update}")


async def main():
    port = 8765
    ws_url = f"ws://localhost:{port}"

    print("=" * 60)
    print("TEST: ACP WebSocket Client → Bridge → Echo Agent")
    print("=" * 60)
    print(f"\nConnecting to: {ws_url}")

    # Use ACP's WebSocket client
    client = WebSocketClient(TestClient(), ws_url)

    async with client.connect() as conn:
        print("✓ Connected via ACP WebSocket client\n")

        # Initialize
        print("→ Initializing...")
        init_response = await conn.initialize(protocol_version=1)
        print(f"✓ Initialized: {init_response}\n")

        # Create session
        print("→ Creating session...")
        session = await conn.new_session(cwd=str(Path(__file__).parent), mcp_servers=[])
        print(f"✓ Session created: {session.session_id}\n")

        # Send prompt
        print("→ Sending prompt...")
        response = await conn.prompt(
            session_id=session.session_id,
            prompt=[text_block("Hello from ACP WebSocket client!")],
        )
        print(f"✓ Response: {response}\n")

        print("✓ All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
