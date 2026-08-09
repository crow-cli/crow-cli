import asyncio
import sys
from pathlib import Path
from typing import Any

from acp import spawn_agent_process, text_block
from acp.interfaces import Client
from acp.schema import AvailableCommandsUpdate


class SimpleClient(Client):
    async def request_permission(self, options, session_id, tool_call, **kwargs: Any):
        return {"outcome": {"outcome": "cancelled"}}

    async def session_update(self, session_id, update, **kwargs):
        print(f"update: {session_id} {update}")
        # Check if this is an AvailableCommandsUpdate
        if isinstance(update, AvailableCommandsUpdate):
            print(f"  -> AVAILABLE COMMANDS: {[cmd.name for cmd in update.available_commands]}")


async def main() -> None:
    script = Path("/home/thomas/src/backup/nid-backup/sandbox/crow-acp-learning/echo_agent.py")
    async with spawn_agent_process(SimpleClient(), sys.executable, str(script)) as (
        conn,
        _proc,
    ):
        await conn.initialize(protocol_version=1)
        session = await conn.new_session(cwd=str(script.parent), mcp_servers=[])
        
        print(f"Session created: {session.session_id}")
        print()
        
        # Test 1: Regular message
        print("=== Test 1: Regular message ===")
        await conn.prompt(
            session_id=session.session_id,
            prompt=[text_block("Hello from spawn!")],
        )
        print()
        
        # Test 2: /help command
        print("=== Test 2: /help command ===")
        await conn.prompt(
            session_id=session.session_id,
            prompt=[text_block("/help")],
        )
        print()
        
        # Test 3: /echo command
        print("=== Test 3: /echo command ===")
        await conn.prompt(
            session_id=session.session_id,
            prompt=[text_block("/echo hello world")],
        )
        print()
        
        # Test 4: Unknown command
        print("=== Test 4: Unknown command ===")
        await conn.prompt(
            session_id=session.session_id,
            prompt=[text_block("/unknown")],
        )
        print()
        
        # Test 5: /clear command
        print("=== Test 5: /clear command ===")
        await conn.prompt(
            session_id=session.session_id,
            prompt=[text_block("/clear")],
        )
        print()


asyncio.run(main())
