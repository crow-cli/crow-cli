#!/usr/bin/env python3
"""
Pipe raw ACP JSON-RPC directly to agent-client over stdio.
No client framework. Just echo JSON lines like Zed does.
"""

import asyncio
import json
import sys


async def main():
    agent_path = (
        "/home/thomas/src/crow-ai/crow-cli/sandbox/agent-client/agent_client.py"
    )
    session_id = None

    proc = await asyncio.create_subprocess_exec(
        "uv",
        "--project",
        "/home/thomas/src/crow-ai/crow-cli/sandbox/agent-client",
        "run",
        str(agent_path),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    print(f"PID: {proc.pid}")

    messages = []  # Collect all incoming messages

    async def read_output():
        nonlocal session_id
        """Read and print all stdout from agent."""
        buffer = b""
        while True:
            chunk = await proc.stdout.read(4096)
            if not chunk:
                if buffer:
                    line = buffer.decode("utf-8").strip()
                    if line:
                        print(f"← {line}")
                        messages.append(json.loads(line))
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                text = line.decode("utf-8").strip()
                if text:
                    print(f"← {text}")
                    try:
                        msg = json.loads(text)
                        messages.append(msg)
                        # Capture sessionId from session/new response
                        if msg.get("id") == 1 and "result" in msg:
                            session_id = msg["result"].get("sessionId")
                    except:
                        pass

    output_task = asyncio.create_task(read_output())

    async def send(msg):
        """Send a JSON-RPC message."""
        data = json.dumps(msg) + "\n"
        print(f"→ {data.strip()}")
        proc.stdin.write(data.encode())
        await proc.stdin.drain()

    # 1. Initialize
    await send(
        {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {"readTextFile": True, "writeTextFile": True},
                    "terminal": True,
                },
                "clientInfo": {
                    "name": "test-client",
                    "title": "Test",
                    "version": "0.1",
                },
            },
        }
    )
    await asyncio.sleep(5)

    # 2. New session
    await send(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "session/new",
            "params": {
                "cwd": "/home/thomas/src/crow-ai/crow-cli/sandbox/agent-client",
                "mcpServers": [],
            },
        }
    )
    await asyncio.sleep(3)

    print(f"\nCaptured sessionId: {session_id}")

    if not session_id:
        print("ERROR: No sessionId received!")
        # Try to find it in collected messages
        for m in messages:
            if "result" in m and "sessionId" in m.get("result", {}):
                session_id = m["result"]["sessionId"]
                print(f"Found in messages: {session_id}")
                break

    # 3. Prompt
    await send(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/prompt",
            "params": {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "hello!"}],
            },
        }
    )
    await asyncio.sleep(15)

    print("\n=== Done ===")
    proc.stdin.close()
    await proc.wait()
    await output_task


if __name__ == "__main__":
    asyncio.run(main())
