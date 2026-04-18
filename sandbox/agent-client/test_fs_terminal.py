"""
Test client that spawns agent-client and asks it to read a file and run date.
Tests both fs.read_text_file and terminal/create client-side tools.
"""

import asyncio
from typing import Any

from acp import spawn_agent_process, text_block
from acp.interfaces import Client


class TestClient(Client):
    async def request_permission(self, options, session_id, tool_call, **kwargs: Any):
        print(f"[PERMISSION] {tool_call}", flush=True)
        return {"outcome": {"outcome": "auto_allow"}}

    async def session_update(self, session_id, update, **kwargs: Any):
        print(f"[UPDATE] {update}", flush=True)

    async def create_terminal(self, command, session_id, **kwargs):
        print(f"[create_terminal] cmd={command}", flush=True)
        raise NotImplementedError("create_terminal not implemented")

    async def terminal_output(self, session_id, terminal_id, **kwargs):
        print(f"[terminal_output] terminal={terminal_id}", flush=True)
        raise NotImplementedError("terminal_output not implemented")

    async def wait_for_terminal_exit(self, session_id, terminal_id, **kwargs):
        print(f"[wait_for_exit] terminal={terminal_id}", flush=True)
        raise NotImplementedError("wait_for_exit not implemented")

    async def read_text_file(self, path, session_id, **kwargs):
        print(f"[read_text_file] path={path}", flush=True)
        raise NotImplementedError("read_text_file not implemented")

    async def write_text_file(self, content, path, session_id, **kwargs):
        print(f"[write_text_file] path={path}", flush=True)
        raise NotImplementedError("write_text_file not implemented")


async def main():
    agent_path = (
        "/home/thomas/src/crow-ai/crow-cli/sandbox/agent-client/agent_client.py"
    )
    agent_dir = "/home/thomas/src/crow-ai/crow-cli/sandbox/agent-client"
    print(f"Testing agent-client: {agent_path}", flush=True)

    async with spawn_agent_process(
        TestClient(),
        "uv",
        "--project",
        agent_dir,
        "run",
        agent_path,
        cwd=agent_dir,
    ) as (conn, proc):
        print(f"✓ spawned (PID: {proc.pid})", flush=True)

        print("→ Initializing...", flush=True)
        init_response = await conn.initialize(protocol_version=1)
        print(f"✓ init: {init_response}", flush=True)

        print("→ Creating session...", flush=True)
        session = await conn.new_session(cwd=agent_dir, mcp_servers=[])
        print(f"✓ session: {session.session_id}", flush=True)

        # This should trigger both fs.read_text_file AND terminal/create
        print("→ Prompt: 'read README.md and run date'", flush=True)
        response = await conn.prompt(
            session_id=session.session_id,
            prompt=[text_block("read the file README.md then run the date command")],
        )
        print(f"✓ response: {response}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
