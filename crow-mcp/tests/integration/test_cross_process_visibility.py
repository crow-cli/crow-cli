"""Regression (service era): a long-lived crow-mcp server must see sessions
written by OTHER processes through the crow-memory service.

Predecessor of this test guarded against LanceDB stale-snapshot bugs when
every process opened its own in-process DB. That bug class is structurally
dead now — one service owns the data — but the guarantee still deserves a
test: the MCP server must read from the SHARED service (no private DB, no
local cache), so a write made by this process via crow-memory-sdk must be
immediately visible through the server's list_sessions / query_session tools.

Integration tier — opt-in via --run-integration. Requires a running
crow-memory service (CROW_MEMORY_URL, default http://127.0.0.1:27697).
Writes one uniquely-named marker session per run (the store is append-only).
"""

import os
import uuid

import pytest
from fastmcp import Client

from crow_memory_sdk import SyncMemoryClient

# crow-mcp project root: tests/integration/<this file> -> up two -> crow-mcp
CROW_MCP_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

RUN_ID = uuid.uuid4().hex[:8]
SID = f"cross-proc-visibility-{RUN_ID}"
MARKER = f"cross-proc-marker-{RUN_ID}"


@pytest.fixture
async def server():
    """A live crow-mcp server over stdio, talking to the shared service."""
    config = {
        "mcpServers": {
            "crow_mcp": {
                "transport": "stdio",
                "command": "uv",
                "args": ["--project", CROW_MCP_DIR, "run", "crow-mcp-dev"],
                "cwd": CROW_MCP_DIR,
                "env": dict(os.environ),
            }
        }
    }
    async with Client(config) as c:
        yield c


def _write_session_from_this_process() -> None:
    """Write a session + messages from THIS process — a different process than
    the running MCP server — via the shared crow-memory service."""
    with SyncMemoryClient() as mem:
        agent_id = f"{SID}-1"
        mem.create_agent(
            agent_id=agent_id,
            session_id=SID,
            agent_idx=1,
            cwd="/tmp",
            prompt_id="",
            prompt_args={},
            system_prompt="",
            tool_definitions=[],
            request_params={},
            model_identifier="stub-model",
        )
        mem.add_message(agent_id, {"role": "user", "content": "hello across processes"})
        mem.add_message(agent_id, {"role": "assistant", "content": MARKER})


class TestCrossProcessVisibility:
    async def test_server_sees_sessions_written_by_other_process(self, server):
        client = server

        # Write from this process (not the server process).
        _write_session_from_this_process()

        # list_sessions must include the new session.
        listed = await client.call_tool("list_sessions", {"limit": 200})
        assert not getattr(listed, "isError", False)
        assert SID in listed.content[0].text, (
            "MCP server did not see a session written by another process "
            "through the crow-memory service — is it reading a private DB?"
        )

        # query_session must return the messages, not "No messages found".
        queried = await client.call_tool("query_session", {"session_id": SID})
        assert not getattr(queried, "isError", False)
        text = queried.content[0].text
        assert "No messages found" not in text
        assert MARKER in text


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--run-integration"])
