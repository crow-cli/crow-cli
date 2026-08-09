"""
Spawn bridge in background, then test it.

Usage:
    ./run_test.sh
"""

import asyncio
import sys
from pathlib import Path

import websockets


async def spawn_bridge():
    """Spawn the bridge and keep it running."""
    here = Path(__file__).parent
    stdio_to_ws = here / "stdio_to_ws.py"
    echo_agent = here / "echo_agent.py"

    print(f"Spawning bridge: {stdio_to_ws}")
    print(f"  with echo agent: {echo_agent}")
    print(f"  on port 8765\n")

    proc = await asyncio.create_subprocess_exec(
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

    print(f"✓ Bridge spawned (PID: {proc.pid})")
    print("  Waiting for bridge to be ready...")

    # Wait for bridge to be ready
    max_retries = 10
    for attempt in range(max_retries):
        try:
            async with websockets.connect("ws://localhost:8765", close_timeout=0.1):
                print("✓ Bridge is ready!\n")
                break
        except:
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5)
            else:
                print("❌ Bridge failed to start")
                proc.kill()
                await proc.wait()
                sys.exit(1)

    # Keep running until Ctrl+C
    try:
        print("Bridge is running. Press Ctrl+C to stop.")
        await proc.wait()
    except KeyboardInterrupt:
        print("\nStopping bridge...")
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        print("✓ Bridge stopped")


if __name__ == "__main__":
    asyncio.run(spawn_bridge())
