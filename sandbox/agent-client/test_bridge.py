"""
Test spawning the bridge directly.
"""

import asyncio
import sys
from pathlib import Path


async def main():
    here = Path(__file__).parent
    stdio_to_ws = here / "stdio_to_ws.py"
    echo_agent = here / "echo_agent.py"

    print(f"Spawning bridge: {stdio_to_ws}")
    print(f"  with echo agent: {echo_agent}")

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

    print(f"Bridge spawned (PID: {proc.pid})")
    print("Waiting 3 seconds...")
    await asyncio.sleep(3)

    print("\nTerminating...")
    proc.terminate()
    await proc.wait()
    print("Done")


if __name__ == "__main__":
    asyncio.run(main())
