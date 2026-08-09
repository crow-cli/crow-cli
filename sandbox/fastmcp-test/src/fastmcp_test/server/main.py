from fastmcp import FastMCP

mcp = FastMCP(
    name="crow-mcp",
    instructions="""
        A comprehensive MCP server for coding agent tools
    """,
)

if __name__ == "__main__":
    mcp.run()


def main():
    """Entry point for running the MCP server."""
    mcp.run()

