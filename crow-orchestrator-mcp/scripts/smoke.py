#!/usr/bin/env python3
"""Release smoke test for crow-orchestrator-mcp.

Boots the *published* package from PyPI via `uvx` (not the local source) and
checks it exposes the expected tools over the MCP protocol. Run it after a
release to confirm the wheel that landed on PyPI actually serves:

    uv --project . run python scripts/smoke.py

The client (this script) runs in the local venv; the server under test is the
released artifact pulled by uvx. VERSION is pinned to the release you just cut
so a stale uvx cache can't mask a bad publish — bump it after each release.
"""

import asyncio
import sys

from fastmcp import Client

# The release we expect to pull from PyPI. Bump after each publish.
VERSION = "0.1.26"

EXPECTED_TOOLS = {
    "orchestrator_task_read",
    "orchestrator_task_write",
    "task_send",
}

config = {
    "mcpServers": {
        "crow_orchestrator_mcp": {
            "transport": "stdio",
            "command": "uvx",
            "args": [f"crow-orchestrator-mcp=={VERSION}"],
        }
    }
}


async def main() -> int:
    client = Client(config)
    print(f"Booting crow-orchestrator-mcp=={VERSION} from PyPI via uvx ...")
    async with client:
        await client.ping()
        print("✅ ping ok")

        tools = await client.list_tools()
        names = {t.name for t in tools}
        print(f"✅ server reports {len(names)} tool(s):")
        for t in tools:
            first_line = (
                (t.description or "").strip().splitlines()[0] if t.description else ""
            )
            print(f"   - {t.name}: {first_line}")

        if names != EXPECTED_TOOLS:
            print(
                f"\n❌ tool mismatch!\n   expected: {EXPECTED_TOOLS}\n   got:      {names}"
            )
            return 1

    print("\n✅ release smoke test passed — published package exposes the right tools")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
