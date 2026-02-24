"""
Crow Builtin MCP Server

Combines all builtin tools into one MCP server:
- file_editor: View, create, edit files
- web_search: Search the web via SearXNG
- fetch: Fetch and parse web pages

This is the default MCP server for crow agents.
"""

import logging
import os

from httpx import AsyncClient
from pydantic import BaseModel

from crow_mcp.server.logger import logger
from crow_mcp.server.main import mcp

# Create the combined MCP server
# mcp = FastMCP(name="crow-builtin")


class SearchResult(BaseModel):
    url: str
    title: str
    content: str


class InfoboxUrl(BaseModel):
    title: str
    url: str


class Infobox(BaseModel):
    infobox: str
    id: str
    content: str
    urls: list[InfoboxUrl]


class SearchResponse(BaseModel):
    query: str
    number_of_results: int
    results: list[SearchResult]
    infoboxes: list[Infobox]


@mcp.tool
async def web_search(queries: list[str], limit: int = 10) -> str:
    """## Search Tool Instructions
    **Search the internet. USE THIS LIBERALLY.**
    If you are:
    - Uncertain about the user's query
    - About to make something up
    - Suspecting the USER is making something up
    - Working with a library/API you haven't seen recently
    - Debugging an error message you don't recognize
    Then SEARCH. Search in parallel (4-5 max). Search before you hallucinate.
    SEARCH INTERNET AS MUCH AS FILESYSTEM! I PITY THE FOOL WHO DON'T USE WEB SEARCH!
    This is not a fallback tool. This is a primary tool. Good developers search the internet constantly. So should you.
    **Tips for better results:**
    - To search a specific website, add the site name to your query (e.g., "python async stackoverflow" or "react hooks site:reactjs.org")
    - To find recent results, add timeframes to your query (e.g., "rust 2024", "next.js news this week")
    - If a snippet looks promising but is cut off, use the fetch tool to pull down the full page
    **Arguments:**
    - `query: str` - Your search query for the search engine
    - `limit: int = 5` - Optional, control the number of results
    **Example use:**
    result: str = search(query="How to make key lime pie")
    """
    searxng_url = os.getenv("SEARXNG_URL", "http://localhost:2946")
    client = AsyncClient(base_url=searxng_url)
    results = []
    for query in queries:
        params = {"q": query, "format": "json"}
        response = await client.get("/search", params=params)
        response.raise_for_status()

        data = SearchResponse.model_validate_json(response.text)

        text = []

        for infobox in data.infoboxes:
            text.append(f"Infobox: {infobox.infobox}\n")
            text.append(f"ID: {infobox.id}\n")
            text.append(f"Content: {infobox.content}\n\n")

        if not data.results:
            text.append("No results found\n")

        for i, result in enumerate(data.results):
            text.append(f"Title: {result.title}\n")
            text.append(f"URL: {result.url}\n")
            text.append(f"Content: {result.content}\n\n")
            if i == limit - 1:
                break

        query_results = "".join(text)
        results.append(f"Query:\n{query}\n\nResults:\n{query_results}")
    return "\n".join(results)
