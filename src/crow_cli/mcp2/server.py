"""The FastMCP instance for the v2 tool surface.

Separate from ``crow_cli.mcp.server.app`` on purpose: mcp2 is not a superset
of mcp. ACP v2 deleted the client execution surface — ``clientCapabilities.fs``
and ``clientCapabilities.terminal`` along with ``fs/read_text_file``,
``fs/write_text_file`` and ``terminal/create|output|release|wait_for_exit|kill``
— so the tools that existed to drive those are not ported, and the ones that
remain change shape (``execute`` becomes a terminal). Registering them onto the
v1 instance would put both shapes on one schema list, and the model would pick
whichever it liked.

Only ``execute`` is here. The rest of the v1 surface is reached through the
kernel's own subtools — ``fs``, ``web``, ``memory``, ``vision``, ``rlm`` —
which is how a spawned agent already works: it is handed ``execute`` and
nothing else, and does its file and network work in-cell.
"""

from fastmcp import FastMCP

from crow_cli.mcp.server.memtrim import MemoryTrimMiddleware

mcp = FastMCP(
    name="crow-mcp2",
    instructions="""
        The crow agent tool surface for ACP v2.

            - execute
            Run one cell in this session's persistent IPython kernel. Output
            arrives twice: as raw terminal bytes for the client to render, and
            as ANSI-stripped text for the model.

        File, web, memory, vision and delegation work happens through the
        subtools ambient in the kernel (fs, web, memory, vision, rlm), not
        through separate MCP tools.
    """,
)

# Long-lived HTTP server: RSS is an allocator high-water mark, not a live
# count. Trim freed heap back to the OS on a cadence so the footprint tracks
# the live set instead of ratcheting to every transient peak.
mcp.add_middleware(MemoryTrimMiddleware(every=10))
