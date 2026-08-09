"""
Crow Builtin MCP Server

Combines all builtin tools into one MCP server:
- file_editor: View, create, edit files
- web_search: Search the web via SearXNG
- fetch: Fetch and parse web pages

This is the default MCP server for crow agents.
"""

import markdownify
import readabilipy.simple_json
from httpx import AsyncClient

from crow_mcp.server.logger import logger
from crow_mcp.server.main import mcp

# Create the combined MCP server
# mcp = FastMCP(name="crow-builtin")


DEFAULT_USER_AGENT = "CrowAgent/1.0"


async def fetch_url(url: str, user_agent: str = DEFAULT_USER_AGENT) -> tuple[str, str]:
    """Fetch URL and return (content, prefix)."""
    async with AsyncClient() as client:
        response = await client.get(
            url,
            follow_redirects=True,
            headers={"User-Agent": user_agent},
            timeout=30,
        )
        response.raise_for_status()
        page_raw = response.text

    content_type = response.headers.get("content-type", "")
    is_html = (
        "<html" in page_raw[:100] or "text/html" in content_type or not content_type
    )

    if is_html:
        ret = readabilipy.simple_json.simple_json_from_html_string(
            page_raw, use_readability=True
        )
        if ret.get("content"):
            content = markdownify.markdownify(
                ret["content"], heading_style=markdownify.ATX
            )
            return content, ""
        return "<error>Failed to parse HTML</error>", ""
    else:
        return page_raw, f"Content type: {content_type}\n"


@mcp.tool
async def web_fetch(
    url: str,
    max_length: int = 5000,
    start_index: int = 0,
    raw: bool = False,
) -> str:
    """Fetch a URL and extract content as markdown.

    Args:
        url: URL to fetch
        max_length: Max characters to return (default 5000)
        start_index: Start at this character (for pagination)
        raw: Get raw HTML instead of markdown

    Returns:
        Page content as markdown (or raw HTML if raw=True)
    """
    try:
        content, prefix = await fetch_url(url)

        if raw:
            # Return raw HTML
            total_len = len(content)
            truncated = content[start_index : start_index + max_length]
            if start_index >= total_len:
                return "<error>No more content available.</error>"
            result = f"{prefix}Raw HTML from {url}:\n{truncated}"
            if len(truncated) == max_length and start_index + max_length < total_len:
                result += f"\n\n<error>Content truncated. Call fetch with start_index={start_index + max_length}</error>"
            return result

        total_len = len(content)
        if start_index >= total_len:
            return "<error>No more content available.</error>"

        truncated = content[start_index : start_index + max_length]
        result = f"{prefix}Contents of {url}:\n{truncated}"

        if len(truncated) == max_length and start_index + max_length < total_len:
            result += f"\n\n<error>Content truncated. Call fetch with start_index={start_index + max_length}</error>"

        return result

    except Exception as e:
        return f"Error fetching {url}: {e}"
