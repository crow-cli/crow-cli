#!/usr/bin/env python3
"""
Test the stdio-to-ws bridge + echo_agent directly.
Spawn bridge in subprocess, connect via WebSocket, send JSON-RPC.
"""

import asyncio
import json
import sys
from pathlib import Path


async def main():
    here = Path(__file__).parent

    # Start bridge
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(here / "stdio_to_ws.py"),
        "--port",
        "9878",
        sys.executable,
        str(here / "echo_agent.py"),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(here),
    )
    print(f"Bridge PID: {proc.pid}")

    await asyncio.sleep(2)  # Give bridge time to start

    async with asyncio.timeout(10):
        async with await __import__("websockets").connect("ws://localhost:9878") as ws:
            # 1. Initialize
            msg = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 0,
                    "method": "initialize",
                    "params": {"protocolVersion": 1},
                }
            )
            print(f"→ {msg}")
            await ws.send(msg)
            resp = await ws.recv()
            print(f"← {resp}")

            # 2. New session
            msg = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "session/new",
                    "params": {"cwd": "/tmp", "mcpServers": []},
                }
            )
            print(f"→ {msg}")
            await ws.send(msg)
            resp = await ws.recv()
            print(f"← {resp}")

            # 3. Prompt
            msg = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "session/prompt",
                    "params": {
                        "sessionId": "test",
                        "prompt": [{"type": "text", "text": "hello!"}],
                    },
                }
            )
            print(f"→ {msg}")
            await ws.send(msg)

            # Read responses (updates + final response)
            for _ in range(10):
                try:
                    resp = await asyncio.wait_for(ws.recv(), timeout=5)
                    print(f"← {resp}")
                except TimeoutError:
                    break

    proc.terminate()
    await proc.wait()
    print("\nDone")


if __name__ == "__main__":
    asyncio.run(main())
