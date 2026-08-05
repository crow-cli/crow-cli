"""Regression: a long-lived crow-mcp server must see sessions written by
OTHER processes after it has opened its store.

When crow-memory was a single HTTP service, one process owned every read and
write, so it always saw its own data. Now that it is in-process, the crow-mcp
server is a long-lived process that opens its LanceDB tables once, while
crow-cli agents write from SEPARATE processes. LanceDB's default connection
does NO cross-process refresh (read_consistency_interval unset), so the server
keeps serving a stale snapshot: list_sessions omits new sessions and
query_session returns "No messages found" for them.

MemoryStore connects with read_consistency_interval=timedelta(0) to fix this.
This test reproduces the exact two-process scenario through the REAL server,
against an isolated temp DB (never the real ~/.crow/memory.lance):

  1. boot the server over stdio pointed at a fresh temp DB,
  2. call list_sessions once (forces the server to open its store),
  3. write a session from THIS process (a different process than the server),
  4. assert the server now sees it via list_sessions AND query_session.

Without the fix, step 4 fails. Integration tier — opt-in via --run-integration.
"""

import os

import numpy as np
import pytest
from fastmcp import Client

from crow_memory.embed import EMBED_DIM
from crow_memory.store import MemoryStore

# crow-mcp project root: tests/integration/<this file> -> up two -> crow-mcp
CROW_MCP_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

SID = "cross-proc-visibility-session"
MARKER = "cross-proc-marker-7f3a"


class StubEmbedders:
    """Zero multivectors so the writer uses the real add_agent/add_message code
    path without loading ColBERT/ColQwen2. Visibility across processes does not
    depend on embedding quality, only on the rows being committed."""

    def embed_text(self, text: str) -> np.ndarray:
        return np.zeros((1, EMBED_DIM), dtype=np.float32)

    def embed_text_query(self, text: str) -> np.ndarray:
        return np.zeros((1, EMBED_DIM), dtype=np.float32)


@pytest.fixture
async def server(tmp_path):
    """A live crow-mcp server over stdio, pointed at an isolated temp DB."""
    db_path = str(tmp_path / "memory.lance")
    config = {
        "mcpServers": {
            "crow_mcp": {
                "transport": "stdio",
                "command": "uv",
                "args": ["--project", CROW_MCP_DIR, "run", "crow-mcp"],
                "cwd": CROW_MCP_DIR,
                "env": {**os.environ, "CROW_MEMORY_PATH": db_path},
            }
        }
    }
    async with Client(config) as c:
        yield c, db_path


def _write_session_from_this_process(db_path: str) -> None:
    """Write a session + messages from THIS process — a different process than
    the running MCP server — which is the condition that triggers the bug."""
    store = MemoryStore(db_path, StubEmbedders())
    agent_id = f"{SID}-1"
    store.add_agent({
        "agent_id": agent_id,
        "session_id": SID,
        "agent_idx": 1,
        "cwd": "/tmp",
        "model_identifier": "stub-model",
    })
    store.add_message(agent_id, {"role": "user", "content": "hello across processes"})
    store.add_message(agent_id, {"role": "assistant", "content": MARKER})


class TestCrossProcessVisibility:
    async def test_server_sees_sessions_written_by_other_process(self, server):
        client, db_path = server

        # 1+2. Force the server to open its store on the (empty) temp DB.
        first = await client.call_tool("list_sessions", {})
        assert not getattr(first, "isError", False)
        assert "No sessions found" in first.content[0].text

        # 3. Write from this process (not the server process).
        _write_session_from_this_process(db_path)

        # 4a. list_sessions must now include the new session.
        listed = await client.call_tool("list_sessions", {})
        assert not getattr(listed, "isError", False)
        assert SID in listed.content[0].text, (
            "long-lived server did not see a session written by another process "
            "(LanceDB read_consistency_interval not refreshing cross-process)"
        )

        # 4b. query_session must return the messages, not "No messages found".
        queried = await client.call_tool("query_session", {"session_id": SID})
        assert not getattr(queried, "isError", False)
        text = queried.content[0].text
        assert "No messages found" not in text
        assert MARKER in text


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--run-integration"])
