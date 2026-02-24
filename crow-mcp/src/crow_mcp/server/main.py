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
            Execute bash commands in a persistent shell session.

            - web_fetch
            Fetch and parse web pages.

            - web_search
            Search the web via SearXNG.
    """,
)

# Import tools to register them with the mcp instance
import crow_mcp.editor.main  # noqa: F401
import crow_mcp.read.main  # noqa: F401
import crow_mcp.terminal.main  # noqa: F401
import crow_mcp.web_fetch.main  # noqa: F401
import crow_mcp.web_search.main  # noqa: F401
import crow_mcp.write.main  # noqa: F401
from crow_mcp.server.logger import logger


def main():
    mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
