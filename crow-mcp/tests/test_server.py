"""Server registration smoke test.

Importing crow_mcp.server.main executes every @mcp.tool decorator across all
tool modules. Asserting the full tool set registers correctly is the primary
safety net for a fastmcp upgrade: a breaking change to the @mcp.tool /
FastMCP API surfaces here first.
"""

import pytest

from crow_mcp.server.main import mcp

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


class TestServerRegistration:
    def test_server_name(self):
        assert mcp.name == "crow-mcp"

    async def test_all_tools_registered(self):
        tools = await mcp.list_tools()
        names = {t.name for t in tools}
        assert names == EXPECTED_TOOLS

    async def test_tool_count(self):
        tools = await mcp.list_tools()
        assert len(tools) == len(EXPECTED_TOOLS)

    async def test_tools_have_descriptions(self):
        # The docstrings ARE the product (the model sees them); every tool
        # must carry one through registration.
        tools = await mcp.list_tools()
        for tool in tools:
            assert getattr(tool, "description", ""), (
                f"tool {tool.name} lost its description"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
