import asyncio
import sys
from pathlib import Path
from typing import Any

from acp import spawn_agent_process, text_block
from acp.interfaces import Client


class SimpleClient(Client):
    async def request_permission(self, options, session_id, tool_call, **kwargs: Any):
        return {"outcome": {"outcome": "cancelled"}}

    async def session_update(self, session_id, update, **kwargs):
        print("update:", session_id, update)


async def main() -> None:
    script = Path("echo_agent.py")
    async with spawn_agent_process(SimpleClient(), sys.executable, str(script)) as (
        conn,
        _proc,
    ):
        await conn.initialize(protocol_version=1)
        session = await conn.new_session(cwd=str(script.parent), mcp_servers=[])
        await conn.prompt(
            session_id=session.session_id,
            prompt=[text_block("Hello from spawn!")],
        )


asyncio.run(main())
