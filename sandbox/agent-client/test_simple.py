"""
Simple test: Spawn bridge, connect via WebSocket, send ACP messages.

NO ACP SDK client - just raw WebSocket + JSON-RPC.
"""

import asyncio
import json
from pathlib import Path

import websockets


async def main():
    here = Path(__file__).parent
    stdio_to_ws = here / "stdio_to_ws.py"
    echo_agent = here / "echo_agent.py"

    print("=" * 60)
    print("TEST: Raw WebSocket → Bridge → Echo Agent")
    print("=" * 60)

    # 1. Spawn bridge
    print(f"\n→ Spawning bridge...")
    bridge_proc = await asyncio.create_subprocess_exec(
        "uv",
        "--project",
        str(here),
        "run",
        str(stdio_to_ws),
        "--port",
        "8765",
        "uv",
        "--project",
        str(here),
        "run",
        str(echo_agent),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(here),
    )

    print(f"✓ Bridge spawned (PID: {bridge_proc.pid})")

    try:
        # 2. Wait and connect
        print("→ Waiting for bridge...")
        await asyncio.sleep(2)

        print("→ Connecting to ws://localhost:8765...")
        async with websockets.connect("ws://localhost:8765") as ws:
            print("✓ Connected!\n")

            # 3. Send initialize
            print("→ Sending initialize...")
            await ws.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": 1,
                            "clientCapabilities": {"terminal": False},
                        },
                    }
                )
            )

            response = json.loads(await ws.recv())
            print(f"✓ Response: {response}\n")

            # 4. Send session/new
            print("→ Sending session/new...")
            await ws.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "session/new",
                        "params": {"cwd": str(here), "mcpServers": []},
                    }
                )
            )

            response = json.loads(await ws.recv())
            print(f"✓ Response: {response}\n")

            # 5. Send session/prompt
            session_id = response["result"]["sessionId"]
            print(f"→ Sending session/prompt (session: {session_id})...")
            await ws.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "session/prompt",
                        "params": {
                            "sessionId": session_id,
                            "prompt": [{"type": "text", "text": "Hello!"}],
                        },
                    }
                )
            )

            # Read messages until we get the response to request 3
            while True:
                msg = json.loads(await ws.recv())
                if "id" in msg and msg["id"] == 3:
                    print(f"✓ Final response: {msg}\n")
                    break
                elif "method" in msg:
                    print(f"  Notification: {msg['method']}")

            print("✓ All tests passed!")

    finally:
        print("\n→ Cleaning up bridge...")
        try:
            bridge_proc.terminate()
            await asyncio.wait_for(bridge_proc.wait(), timeout=2.0)
        except (ProcessLookupError, asyncio.TimeoutError):
            try:
                bridge_proc.kill()
                await bridge_proc.wait()
            except ProcessLookupError:
                pass  # Already dead
        print("✓ Done")


if __name__ == "__main__":
    asyncio.run(main())
