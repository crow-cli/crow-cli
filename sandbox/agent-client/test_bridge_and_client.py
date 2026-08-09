"""
Test runner that:
1. Spawns stdio_to_ws bridge (which spawns echo_agent)
2. Waits for bridge to be ready
3. Connects with test client
4. Cleans up
"""

import asyncio
import sys
from pathlib import Path

import websockets


async def test_client():
    """Test WebSocket client."""
    port = 8765
    ws_url = f"ws://localhost:{port}"

    print(f"Connecting to bridge at {ws_url}...")

    # Retry connection
    max_retries = 10
    for attempt in range(max_retries):
        try:
            async with websockets.connect(ws_url) as ws:
                print("✓ Connected to bridge\n")

                # Test 1: Initialize
                print("→ Sending initialize request...")
                import json
                request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": 1,  # ← camelCase!
                        "clientCapabilities": {
                            "terminal": False,
                            "fs": {
                                "readTextFile": False,
                                "writeTextFile": False
                            }
                        }
                    }
                }
                await ws.send(json.dumps(request))

                response = await ws.recv()
                response_data = json.loads(response)
                print(f"✓ Got response: {response_data}\n")

                # Test 2: New session
                print("→ Sending session/new request...")
                request = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "session/new",  # ← Use slash notation!
                    "params": {
                        "cwd": str(Path(__file__).parent),
                        "mcpServers": []  # ← camelCase not snake_case!
                    }
                }
                await ws.send(json.dumps(request))
                
                response = await ws.recv()
                response_data = json.loads(response)
                
                if "error" in response_data:
                    print(f"❌ Error in response: {response_data}")
                    raise RuntimeError(f"session/new failed: {response_data['error']}")
                
                session_id = response_data["result"]["sessionId"]  # ← camelCase!
                print(f"✓ Got session: {session_id}\n")
                
                # Test 3: Prompt
                print("→ Sending session/prompt request...")
                request = {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "session/prompt",  # ← Use slash notation!
                    "params": {
                        "sessionId": session_id,  # ← camelCase!
                        "prompt": [
                            {"type": "text", "text": "Hello from WebSocket!"}
                        ]
                    }
                }
                await ws.send(json.dumps(request))

                response = await ws.recv()
                response_data = json.loads(response)
                
                if "error" in response_data:
                    print(f"❌ Error in response: {response_data}")
                    raise RuntimeError(f"new_session failed: {response_data['error']}")
                
                session_id = response_data["result"]["session_id"]
                print(f"✓ Got session: {session_id}\n")

                # Test 3: Prompt
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
                
                # Receive messages
                message = await ws.recv()
                data = json.loads(message)
                print(f"RAW RESPONSE: {data}")
                
                if "error" in data:
                    print(f"❌ Error in prompt response: {data}")
                    raise RuntimeError(f"session/prompt failed: {data['error']}")
                
                if "id" in data and data["id"] == 3:
                    print(f"✓ Got final response: {data}\n")
                else:
                    print(f"  OTHER: {data}")

                print("✓ All tests passed!")
                return True

        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  Attempt {attempt + 1} failed: {e}, retrying...")
                await asyncio.sleep(0.5)
            else:
                print(f"❌ Failed to connect after {max_retries} attempts: {e}")
                raise


async def main():
    here = Path(__file__).parent
    stdio_to_ws = here / "stdio_to_ws.py"
    echo_agent = here / "echo_agent.py"

    print("=" * 60)
    print("TEST: Bridge + Echo Agent over WebSocket")
    print("=" * 60)

    # Spawn bridge
    print(f"\n→ Spawning bridge: {stdio_to_ws}")
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

    print(f"✓ Bridge spawned (PID: {bridge_proc.pid})\n")

    try:
        # Run test client
        await test_client()
    finally:
        # Cleanup
        print("\n→ Cleaning up bridge...")
        try:
            bridge_proc.terminate()
            await asyncio.wait_for(bridge_proc.wait(), timeout=2.0)
            print("✓ Bridge terminated")
        except asyncio.TimeoutError:
            bridge_proc.kill()
            await bridge_proc.wait()
            print("✓ Bridge killed")
        except ProcessLookupError:
            print("✓ Bridge already terminated")


if __name__ == "__main__":
    asyncio.run(main())
