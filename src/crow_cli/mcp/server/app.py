"""The FastMCP instance — shared by every tool module.

Lives in its own leaf module so a single tool facade (e.g. the memory
telemetry tools, also surfaced directly on the CLI) can be imported
without registering — and paying the import cost of — every other tool
group (vision pulls opencv). server/main.py imports this AND every tool
module to build the full server.
"""

from fastmcp import FastMCP

from crow_cli.mcp.server.memtrim import MemoryTrimMiddleware

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

# Long-lived HTTP server: RSS is an allocator high-water mark, not a live
# count. Trim freed heap back to the OS on a cadence so the footprint tracks
# the live set instead of ratcheting to every transient peak.
mcp.add_middleware(MemoryTrimMiddleware(every=10))
