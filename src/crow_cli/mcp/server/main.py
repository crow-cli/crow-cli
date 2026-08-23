"""crow-cli mcp entry point.

Transports:
  stdio (default) — the classic: the agent spawns us as a child process.
  http            — streamable HTTP service: one server, many clients,
                    endpoint at http://<host>:<port>/mcp.

Usage:
  crow-cli mcp                                   # stdio (unchanged behavior)
  crow-cli mcp --transport http                  # http://127.0.0.1:2769/mcp
  crow-cli mcp --transport http --host H --port P

Env overrides: CROW_MCP_TRANSPORT, CROW_MCP_HOST, CROW_MCP_PORT.
"""

import argparse
import os

# The instance lives in app.py (leaf module, fastmcp-only) so single tool
# facades can import it without dragging in every other tool group.
from crow_cli.mcp.server.app import mcp

# Import tools to register them with the mcp instance
import crow_cli.mcp.editor.main  # noqa: F401
import crow_cli.mcp.memory.main
import crow_cli.mcp.read.main  # noqa: F401
import crow_cli.mcp.task.main  # noqa: F401
import crow_cli.mcp.terminal.main  # noqa: F401
import crow_cli.mcp.vision.main
import crow_cli.mcp.web_fetch.main  # noqa: F401
import crow_cli.mcp.web_search.main  # noqa: F401
import crow_cli.mcp.write.main  # noqa: F401

from crow_cli.mcp.server.logger import logger

# 2769 = CROW on a T9 keypad.
DEFAULT_PORT = 2769


def serve(transport: str, host: str, port: int) -> None:
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
    args = parser.parse_args()
    serve(args.transport, args.host, args.port)


if __name__ == "__main__":
    main()
