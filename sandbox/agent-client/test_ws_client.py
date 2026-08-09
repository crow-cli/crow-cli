"""
Test WebSocket client that talks ACP to the bridge.

This tests:
1. Bridge (stdio_to_ws.py) is running
2. Bridge has spawned echo_agent.py
3. We can send ACP messages over WebSocket
4. We get responses back
"""

import asyncio
import json
from pathlib import Path

import websockets


async def main():
    port = 8765
    ws_url = f"ws://localhost:{port}"

    print(f"Connecting to bridge at {ws_url}...")

    try:
        async with websockets.connect(ws_url) as ws:
            print("✓ Connected to bridge\n")

            # Test 1: Initialize
            print("→ Sending initialize request...")
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocol_version": 1},
            }
            await ws.send(json.dumps(request))

            response = await ws.recv()
            response_data = json.loads(response)
            print(f"✓ Got response: {response_data}\n")

            # Test 2: New session
            print("→ Sending new_session request...")
            request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "new_session",
                "params": {"cwd": str(Path(__file__).parent), "mcp_servers": []},
            }
            await ws.send(json.dumps(request))

            response = await ws.recv()
            response_data = json.loads(response)
            session_id = response_data["result"]["session_id"]
            print(f"✓ Got session: {session_id}\n")

            # Test 3: Prompt (this will generate session_updates)
            print("→ Sending prompt request...")
            request = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "prompt",
                "params": {
                    "session_id": session_id,
                    "prompt": [{"type": "text", "text": "Hello from WebSocket!"}],
                },
            }
            await ws.send(json.dumps(request))
            print("✓ Prompt sent, waiting for updates...\n")

            # Receive messages until we get the final response
            while True:
                message = await ws.recv()
                data = json.loads(message)

                if "id" in data and data["id"] == 3:
                    # Final response to our prompt
                    print(f"✓ Got final response: {data}\n")
                    break
                elif "method" in data and data["method"] == "session_update":
                    # Session update (streaming)
                    print(f"  UPDATE: {data['params']['update']}")
                else:
                    print(f"  OTHER: {data}")

            print("✓ All tests passed!")

    except Exception as e:
        print(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
