"""Shared fixtures for the MCP tier.

``crow_cli.mcp.server.app.mcp`` is a MODULE-LEVEL singleton. Every test in this
tier shares one FastMCP instance with every tool module it imports, so a test
that narrows it — which is exactly what ``--include-tools`` does — has to put it
back, or the next test silently sees a server with one tool on it.

``enable()`` appends a transform each time it is called (they accumulate, later
overriding earlier), so the restore is conditional: tests that never narrowed
never pay for one.
"""

import pytest

from crow_cli.mcp import tool_names
from crow_cli.mcp.server.app import mcp
from crow_cli.mcp.server.main import register_tools


@pytest.fixture
def all_tools():
    """The singleton with every tool registered and enabled.

    ``register_tools(None)`` imports all ten tool modules and adds no
    transform, so this is cheap to call from every test that wants the
    whole server.
    """
    register_tools(None)
    return mcp


@pytest.fixture
async def narrow():
    """Narrow the singleton to a tool list; restore ALL of them on teardown.

    Returns a coroutine taking the allowlist and answering with the sorted
    names the server actually ended up serving — so a test asserts on what
    fastmcp reports, not on what it asked for.
    """
    used = False

    async def _narrow(names):
        nonlocal used
        used = True
        register_tools(list(names))
        return sorted(t.name for t in await mcp.list_tools())

    yield _narrow

    if used:
        # Re-import everything first: enable() only lifts a transform, it does
        # not register a module that was pruned.
        register_tools(None)
        mcp.enable(names=set(tool_names()), only=True, components={"tool"})
