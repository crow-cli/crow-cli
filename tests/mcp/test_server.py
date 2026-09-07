"""Server registration smoke test.

Registration is an import side effect of each TOOL module (``@mcp.tool`` runs at
module scope), and ``server.main`` no longer imports them at module scope — it
imports only the ones a given ``--include-tools`` asked for. So this test asks
for all of them via the ``all_tools`` fixture and asserts the full set shows up.

That full set is the primary safety net for a fastmcp upgrade: a breaking change
to the ``@mcp.tool`` / ``FastMCP`` API surfaces here first.
"""

import pytest

from crow_cli.mcp import tool_modules, tool_names

EXPECTED_TOOLS = {
    "read",
    "write",
    "edit",
    "terminal",
    "execute",
    "web_fetch",
    "web_search",
    "list_sessions",
    "query_memory",
    "query_session",
    "capture_webcam",
    "read_image_file",
    "task",
}


class TestServerRegistration:
    def test_server_name(self, all_tools):
        assert all_tools.name == "crow-mcp"

    async def test_all_tools_registered(self, all_tools):
        tools = await all_tools.list_tools()
        names = {t.name for t in tools}
        assert names == EXPECTED_TOOLS

    async def test_tool_count(self, all_tools):
        tools = await all_tools.list_tools()
        assert len(tools) == len(EXPECTED_TOOLS)

    async def test_tools_have_descriptions(self, all_tools):
        # The docstrings ARE the product (the model sees them); every tool
        # must carry one through registration.
        tools = await all_tools.list_tools()
        for tool in tools:
            assert getattr(tool, "description", ""), (
                f"tool {tool.name} lost its description"
            )


class TestToolRegistry:
    """The registry in ``crow_cli.mcp._LAZY`` is the one source of truth.

    ``--list-tools``, ``--include-tools`` validation and ``register_tools`` all
    read it, so drift between it and the set of tools that actually register is
    a user-visible bug: a name the CLI advertises but cannot serve, or a tool
    that serves but cannot be selected.
    """

    def test_registry_matches_the_tools_that_register(self):
        # Catches both directions: a tool added without a registry entry, and a
        # registry entry left behind by a tool that was removed.
        assert set(tool_names()) == EXPECTED_TOOLS

    def test_registry_excludes_the_server_instance(self):
        # "mcp" is in _LAZY so the facade can hand out the singleton; it is not
        # a tool and must never be offered to --include-tools.
        assert "mcp" not in tool_modules()
        assert "mcp" not in tool_names()

    def test_tool_names_is_sorted(self):
        # --list-tools prints this verbatim; sorted output is diffable and
        # stable across runs (dict order is an implementation detail).
        assert tool_names() == sorted(tool_names())

    def test_every_registered_tool_has_an_owning_module(self):
        registry = tool_modules()
        assert set(registry) == EXPECTED_TOOLS
        for name, module in registry.items():
            assert module.startswith("crow_cli.mcp."), f"{name} -> {module}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
