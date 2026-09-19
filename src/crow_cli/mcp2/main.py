"""``crow-cli mcp2`` — serve the ACP v2 tool surface.

The v2 sibling of :mod:`crow_cli.mcp.server.main`, and deliberately a smaller
file. Two of v1's three jobs do not exist here:

* There is no ``--include-tools``. mcp2 serves ``execute`` and only
  ``execute`` — the rest of the v1 surface is reached through subtools ambient
  in the kernel (see :mod:`crow_cli.mcp2.server`), so the registry has one
  entry by design and an allowlist over it would have nothing to allow. That
  removes ``resolve_tool_selection``, ``ToolSelectionError`` and the
  ``enable(only=True)`` half of ``register_tools`` wholesale.
* There is no shared logger module to import. v1's
  :mod:`crow_cli.mcp.server.logger` binds its path at module scope and logs a
  placeholder error on import; this uses :func:`crow_cli.agent.logger.setup_logger`
  — the same helper ``agent2`` already uses — pointed at its own file, so the
  two servers' logs do not interleave.

What is kept is the transport split, because it is the reason the kernel is
keyed by ACP session id rather than by process: ``stdio`` is one server per
agent (the client spawns and owns it, so the kernel lifetime is the session
lifetime), ``http`` is one long-lived kernel host multiplexing many clients,
each ``execute`` call carrying its session id in ``_meta``.

Usage:
  crow-cli mcp2                                # stdio, the default
  crow-cli mcp2 --transport http --port 2770   # http://127.0.0.1:2770/mcp
  crow-cli mcp2 --list-tools                   # what is served
  python -m crow_cli.mcp2.main                 # same, without the console script

Env overrides: CROW_MCP2_TRANSPORT, CROW_MCP2_HOST, CROW_MCP2_PORT.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path

from crow_cli.agent.logger import setup_logger
from crow_cli.mcp2 import TOOL_MODULES, tool_names
from crow_cli.mcp2.server import mcp

# The tool modules are NOT imported here. Registration is an import side
# effect, so importing crow_cli.mcp2.execute.main at module scope would
# register ``execute`` before register_tools() ran and turn the registry in
# crow_cli.mcp2 — the thing ``--list-tools`` prints and the one source of
# truth for what is served — into decoration. serve() reaches the modules'
# teardown through sys.modules for the same reason.

# 2769 is CROW on a T9 keypad and belongs to the v1 server. The two are meant
# to coexist — agent1 is frozen and still talks to crow-mcp — so v2 takes the
# next one instead of sharing.
DEFAULT_PORT = 2770

# What ``serve`` accepts. "http" is the spelling an operator writes and
# "streamable-http" the one fastmcp wants; both are listed because both reach
# this function (the console script normalizes nothing, ``-m`` gets here via
# argparse's own choices).
TRANSPORTS = ("stdio", "http", "streamable-http")

# Not Config.config_dir: loading a Config to find a log file would read yaml,
# resolve env vars and pull in the memory client, and v1's server does not do
# it either. Same path v1 hardcodes, one file over.
LOG_PATH = Path.home() / ".agents" / "crow" / "logs" / "crow-mcp2.log"


def register_tools() -> list[str]:
    """Import every tool module and return the names now served.

    Importing IS registering — the ``@mcp.tool`` decorator runs at module
    scope — so there is nothing else to do. Unlike v1 this is idempotent and
    unconditional: there is no selection to honour.
    """
    for module in dict.fromkeys(TOOL_MODULES.values()):
        importlib.import_module(module)
    return tool_names()


def serve(transport: str, host: str, port: int) -> None:
    """Register the tools and block serving them on ``transport``.

    Raises ``ValueError`` for a transport fastmcp does not have. Checked here
    rather than left to ``mcp.run`` because of what happens in between: the
    HTTP branch announces its url before it blocks, so a typo would print a
    listening address for a server that never starts and then fail.
    """
    if transport not in TRANSPORTS:
        raise ValueError(
            f"unknown transport: {transport!r}. "
            f"expected one of {', '.join(TRANSPORTS)}"
        )
    served = register_tools()
    # A rotating file, never stdout: on the stdio transport stdout IS the
    # JSON-RPC stream and one stray line is a protocol violation.
    logger = setup_logger(LOG_PATH, name="crow_cli.mcp2_logger")
    logger.info("crow-mcp2 serving %d tool(s): %s", len(served), ", ".join(served))

    transport = "streamable-http" if transport == "http" else transport
    try:
        if transport == "stdio":
            mcp.run(show_banner=False)
        else:
            url = f"http://{host}:{port}/mcp"
            logger.info("crow-mcp2 serving streamable HTTP at %s", url)
            # stdout is free on this transport, and the operator wants the url.
            print(f"crow-mcp2 serving streamable HTTP at {url}", flush=True)
            mcp.run(transport=transport, host=host, port=port, show_banner=False)
    finally:
        # Every kernel is a child ipykernel process. A client that closes the
        # pipe lets mcp.run() return, and without this the kernels outlive the
        # server that spawned them. (A client that SIGKILLs us takes the
        # opposite risk — nothing runs — which is why the agent reaps its own
        # MCP subprocesses through the per-session AsyncExitStack.)
        #
        # sys.modules, not an import at the top of this file: see the note
        # there. Present and imported because register_tools() ran above, and
        # a tool module with no shutdown_all is an AttributeError on purpose —
        # it owns processes this file cannot see any other way.
        for module in dict.fromkeys(TOOL_MODULES.values()):
            sys.modules[module].shutdown_all()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="crow-cli mcp2",
        description="crow's ACP v2 MCP tools over stdio (default) or streamable HTTP.",
    )
    parser.add_argument(
        "--transport",
        choices=list(TRANSPORTS),
        default=os.environ.get("CROW_MCP2_TRANSPORT", "stdio"),
        help="stdio = spawned child (default); http = streamable HTTP service",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("CROW_MCP2_HOST", "127.0.0.1"),
        help="bind address for the HTTP transport",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("CROW_MCP2_PORT", DEFAULT_PORT)),
        help=f"port for the HTTP transport (default {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="print the served tool names and exit",
    )
    args = parser.parse_args()

    if args.list_tools:
        for name in tool_names():
            print(name)
        return

    serve(args.transport, args.host, args.port)


if __name__ == "__main__":
    main()
