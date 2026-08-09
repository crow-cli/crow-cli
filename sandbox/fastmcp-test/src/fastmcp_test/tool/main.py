from fastmcp_test.server import mcp


@mcp.tool
def add_numbers(a: float, b: float):
    """Add two numbers together"""
    return a + b
