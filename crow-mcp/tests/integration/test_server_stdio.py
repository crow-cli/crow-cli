"""End-to-end smoke test: boot the real crow-mcp server over stdio and drive
it through the MCP protocol, exactly as a client (crow-cli) would.

This is the integration tier — opt-in via `--run-integration` (or
CROW_RUN_INTEGRATION=1). It spawns a subprocess server, so it is slower and
non-hermetic compared to the unit suite. Its job is to prove the whole server
wires up over the transport: registration, a real tool round-trip that hits
disk, and the terminal stub behaving sanely on the wire.
"""

import os

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

# crow-mcp project root: tests/integration/<this file> -> up two -> crow-mcp
CROW_MCP_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

EXPECTED_TOOLS = {
    "read",
    "write",
    "edit",
    "terminal",
    "web_fetch",
    "web_search",
    "query_memory",
    "capture_webcam",
    "read_image_file",
}


@pytest.fixture
async def client():
    """A live crow-mcp server spoken to over stdio, as a real client would."""
    config = {
        "mcpServers": {
            "crow_mcp": {
                "transport": "stdio",
                "command": "uv",
                "args": ["--project", CROW_MCP_DIR, "run", "crow-mcp"],
                "cwd": CROW_MCP_DIR,
            }
        }
    }
    async with Client(config) as c:
        yield c


class TestServerOverStdio:
    async def test_ping(self, client):
        await client.ping()

    async def test_full_toolset_registered_over_wire(self, client):
        tools = await client.list_tools()
        assert {t.name for t in tools} == EXPECTED_TOOLS

    async def test_write_read_roundtrip_hits_disk(self, client, tmp_path):
        """write must actually hit disk and read must return it over the wire."""
        target = tmp_path / "e2e-roundtrip.txt"
        marker = "crow-e2e-marker-12345"

        wrote = await client.call_tool(
            "write", {"file_path": str(target), "content": marker}
        )
        assert not getattr(wrote, "isError", False)
        assert target.read_text() == marker  # really landed on the filesystem

        read_back = await client.call_tool("read", {"file_path": str(target)})
        assert not getattr(read_back, "isError", False)
        assert marker in read_back.content[0].text  # and comes back over stdio

    async def test_terminal_stub_errors_cleanly_on_wire(self, client):
        """The terminal tool is a schema-only stub; over the wire it surfaces as
        a ToolError rather than crashing the server or hanging the session."""
        with pytest.raises(ToolError) as excinfo:
            await client.call_tool("terminal", {"command": "echo x"})
        msg = str(excinfo.value)
        assert "client-side terminal" in msg
        assert "LLM tool selection" in msg
