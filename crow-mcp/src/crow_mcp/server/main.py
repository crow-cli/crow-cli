"""crow-mcp entry point.

Transports:
  stdio (default) — the classic: the agent spawns us as a child process.
  http            — streamable HTTP service: one server, many clients,
                    endpoint at http://<host>:<port>/mcp.

Usage:
  crow-mcp                                   # stdio (unchanged behavior)
  crow-mcp --transport http                  # http://127.0.0.1:2769/mcp
  crow-mcp --transport http --host H --port P

Env overrides: CROW_MCP_TRANSPORT, CROW_MCP_HOST, CROW_MCP_PORT.
"""

import argparse
import os

from fastmcp import FastMCP

mcp = FastMCP(
    name="crow-mcp",
    instructions="""
        A comprehensive MCP server for coding agent tools, including:
            - read
            Read file contents with line numbering.

            - write
            Write content to files, creating or overwriting.

            - edit
            Edit files with fuzzy string matching.

            - terminal
            Execute bash commands in a shell session.

            - web_fetch
            Fetch and parse web pages.

            - web_search
            Search the web via SearXNG.
    """,
)

# Import tools to register them with the mcp instance
import crow_mcp.editor.main  # noqa: F401
import crow_mcp.memory.main
import crow_mcp.read.main  # noqa: F401
import crow_mcp.terminal.main  # noqa: F401
import crow_mcp.vision.main
import crow_mcp.web_fetch.main  # noqa: F401
import crow_mcp.web_search.main  # noqa: F401
import crow_mcp.write.main  # noqa: F401

from crow_mcp.server.logger import logger

# 2769 = CROW on a T9 keypad.
DEFAULT_PORT = 2769


def main():
    parser = argparse.ArgumentParser(
        prog="crow-mcp",
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

    transport = "streamable-http" if args.transport == "http" else args.transport

    if transport == "stdio":
        mcp.run(show_banner=False)
    else:
        url = f"http://{args.host}:{args.port}/mcp"
        logger.info("crow-mcp serving streamable HTTP at %s", url)
        print(f"crow-mcp serving streamable HTTP at {url}", flush=True)
        mcp.run(transport=transport, host=args.host, port=args.port, show_banner=False)


if __name__ == "__main__":
    main()
