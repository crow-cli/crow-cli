"""crow-mcp2 — the ACP v2 agent's MCP server.

A sibling of :mod:`crow_cli.mcp`, not a replacement: agent1 is frozen and
still speaks to the v1 server, so the two coexist until v1 is retired.

Only ``execute`` is ported. It is the one tool a spawned crow agent is handed,
and the one whose v1 implementation could not do what v2 needs — streaming raw
bytes to a client while the cell runs, and returning both the raw buffer and
the ANSI-stripped text so the human and the model each get the version that is
signal for them. See :mod:`crow_cli.mcp2.execute.kernel`.
"""

# Tool name -> the module whose IMPORT registers that tool. Registration is the
# ``@mcp.tool`` decorator running at module scope, so this dict is the whole
# mechanism and the one source of truth for "which tools exist": ``crow-cli
# mcp2 --list-tools`` prints it and :func:`crow_cli.mcp2.main.register_tools`
# imports it. Adding a tool here is what makes it served.
#
# One entry, and one entry by design — this is not v1's registry waiting to be
# filled in. Everything else the agent needs (fs, web, memory, vision, rlm,
# task) is a subtool ambient inside the kernel, reached in-cell rather than
# over MCP, so the surface does not grow the way v1's did. Which is also why
# there is no ``--include-tools``: an allowlist over one tool has nothing to
# allow.
TOOL_MODULES = {"execute": "crow_cli.mcp2.execute.main"}

__all__ = ["TOOL_MODULES", "tool_names"]


def tool_names() -> list[str]:
    """Every servable tool name, sorted. Reads the registry, imports nothing.

    Importing nothing is the point: ``--list-tools`` answers without paying for
    jupyter_client, ipykernel or the subtool package.
    """
    return sorted(TOOL_MODULES)
