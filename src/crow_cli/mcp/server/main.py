"""crow-cli mcp entry point.

Transports:
  stdio (default) — the classic: the agent spawns us as a child process.
  http            — streamable HTTP service: one server, many clients,
                    endpoint at http://<host>:<port>/mcp.

One codebase, many servers. ``--include-tools`` is an ALLOWLIST, so the same
binary can be spawned several times under different names in config.yaml, each
serving a slice of the tool set:

    mcpServers:
      crow-fs:   {command: crow-cli, args: [mcp, --include-tools, "read,write,edit"]}
      crow-web:  {command: crow-cli, args: [mcp, --include-tools, "web_search,web_fetch"]}

It defaults to EVERYTHING. You exclude a tool by not listing it, and a server
started without the flag is byte-for-byte the server that existed before the
flag did.

Usage:
  crow-cli mcp                                   # stdio, all tools
  crow-cli mcp --include-tools read,write,edit   # stdio, three tools
  crow-cli mcp --include-tools read --include-tools write
  crow-cli mcp --transport http --port 2769      # http://127.0.0.1:2769/mcp
  crow-cli mcp --list-tools                      # what --include-tools accepts

Env overrides: CROW_MCP_TRANSPORT, CROW_MCP_HOST, CROW_MCP_PORT.
"""

import argparse
import importlib
import os
import sys
from collections.abc import Sequence

# The instance lives in app.py (leaf module, fastmcp-only) so single tool
# facades can import it without dragging in every other tool group.
from crow_cli.mcp import tool_modules, tool_names
from crow_cli.mcp.server.app import mcp

# Tool modules are NOT imported here. Registration is an import side effect, so
# importing them at module scope would register all thirteen before anyone had
# a chance to say which ones they wanted — and would pay for every tool group
# (vision pulls opencv) on every spawn. register_tools() does it selectively.

from crow_cli.mcp.server.logger import logger

# 2769 = CROW on a T9 keypad.
DEFAULT_PORT = 2769


class ToolSelectionError(ValueError):
    """``--include-tools`` named something that is not a tool, or nothing."""


def resolve_tool_selection(values: Sequence[str] | None) -> list[str] | None:
    """Flatten and validate ``--include-tools`` into an allowlist.

    Both spellings are accepted because config.yaml wants one string
    (``args: [mcp, --include-tools, "read,write"]``) and a shell wants
    repeated flags.

    Returns ``None`` for "not given", which means ALL tools — a different thing
    from an empty list, which would mean a server with nothing on it and is
    always a mistake, so it is refused rather than served.
    """
    if not values:
        return None
    names = [n.strip() for value in values for n in value.split(",")]
    names = [n for n in names if n]
    if not names:
        raise ToolSelectionError(
            "--include-tools was given but resolved to no tool names"
        )
    registry = tool_modules()
    unknown = [n for n in names if n not in registry]
    if unknown:
        raise ToolSelectionError(
            f"unknown tool(s): {', '.join(unknown)}. "
            f"available: {', '.join(sorted(registry))}"
        )
    # Dedupe, keeping order: the same tool listed twice is harmless but noisy.
    return list(dict.fromkeys(names))


def register_tools(include: list[str] | None = None) -> list[str]:
    """Import the tool modules and narrow the server to ``include``.

    Two moves, and both are needed:

    1. Import only the modules that own the selected tools. Registration is the
       ``@mcp.tool`` decorator running at module scope, so not importing a
       module is the cheapest possible way to not serve its tools.
    2. Ask fastmcp to disable the rest. Still required after (1) because a
       module can own several tools — memory owns three, vision owns two — and
       importing it registers all of them.

    ``enable(only=True)`` is an allowlist transform, not a cosmetic hide: a
    disabled tool is absent from ``list_tools`` AND calling it raises
    ``NotFoundError``, so a client cannot reach a tool it was not offered.

    Returns the tool names now served.
    """
    registry = tool_modules()
    selected = list(registry) if include is None else list(include)
    for module in dict.fromkeys(registry[name] for name in selected):
        importlib.import_module(module)
    if include is not None:
        mcp.enable(names=set(include), only=True, components={"tool"})
    return selected


def serve(
    transport: str,
    host: str,
    port: int,
    include_tools: list[str] | None = None,
) -> None:
    served = register_tools(include_tools)
    # The logger writes to a rotating file, never stdout — stdout belongs to
    # the JSON-RPC stream on the stdio transport.
    logger.info(
        "crow-mcp serving %d tool(s): %s", len(served), ", ".join(sorted(served))
    )

    transport = "streamable-http" if transport == "http" else transport

    if transport == "stdio":
        mcp.run(show_banner=False)
    else:
        url = f"http://{host}:{port}/mcp"
        logger.info("crow-mcp serving streamable HTTP at %s", url)
        print(f"crow-mcp serving streamable HTTP at {url}", flush=True)
        mcp.run(transport=transport, host=host, port=port, show_banner=False)


def main():
    parser = argparse.ArgumentParser(
        prog="crow-cli mcp",
        description="crow MCP tools over stdio (default) or streamable HTTP.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "streamable-http"],
        default=os.environ.get("CROW_MCP_TRANSPORT", "stdio"),
        help="stdio = spawned child (default); http = streamable HTTP service",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("CROW_MCP_HOST", "127.0.0.1"),
        help="bind address for the HTTP transport",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("CROW_MCP_PORT", DEFAULT_PORT)),
        help=f"port for the HTTP transport (default {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--include-tools",
        action="append",
        metavar="TOOLS",
        help="allowlist of tools to serve, comma-separated and/or repeated "
        "(default: all of them). Exclude a tool by not listing it.",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="print the tool names --include-tools accepts and exit",
    )
    args = parser.parse_args()

    if args.list_tools:
        for name in tool_names():
            print(name)
        return

    try:
        include = resolve_tool_selection(args.include_tools)
    except ToolSelectionError as exc:
        print(f"crow-cli mcp: {exc}", file=sys.stderr)
        raise SystemExit(2)

    serve(args.transport, args.host, args.port, include_tools=include)


if __name__ == "__main__":
    main()
