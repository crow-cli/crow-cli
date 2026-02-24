from os import getenv
from typing import Optional

from fastmcp import FastMCP
from httpx import AsyncClient
from pydantic import BaseModel, Field

mcp = FastMCP(name="SearXNGTools")


@mcp.tool
async def web_search(query: str, limit: int = 5) -> str:
    """Search the internet.
    Arguments:
        query: str - Your search query for the search engine.
        limit: int = 5 - optional argument to control the number of results
    Example use:
       result: str = search(query="How to make key lime pie")
    """
    client = AsyncClient(base_url=str(getenv("SEARXNG_URL", "http://localhost:8082")))

    params: dict[str, str] = {"q": query, "format": "json"}

    response = await client.get("/search", params=params)
    response.raise_for_status()

    data = Response.model_validate_json(response.text)

    text = []

    for index, infobox in enumerate(data.infoboxes):
        text.append(f"Infobox: {infobox.infobox}\n")
        text.append(f"ID: {infobox.id}\n")
        text.append(f"Content: {infobox.content}\n")
        text.append("\n")

    if len(data.results) == 0:
        text.append("No results found\n")

    for index, result in enumerate(data.results):
        text.append(f"Title: {result.title}\n")
        text.append(f"URL: {result.url}\n")
        text.append(f"Content: {result.content}\n")
        text.append("\n")

        if index == limit - 1:
            break

    return "".join(text)


class SearchResult(BaseModel):
    url: str
    title: str
    content: str
    # thumbnail: Optional[str] = None
    # engine: str
    # parsed_url: list[str]
    # template: str
    # engines: list[str]
    # positions: list[int]
    # publishedDate: Optional[str] = None
    # score: float
    # category: str


class InfoboxUrl(BaseModel):
    title: str
    url: str


class Infobox(BaseModel):
    infobox: str
    id: str
    content: str
    # img_src: Optional[str] = None
    urls: list[InfoboxUrl]
    # attributes: list[str]
    # engine: str
    # engines: list[str]


class Response(BaseModel):
    query: str
    number_of_results: int
    results: list[SearchResult]
    # answers: list[str]
    # corrections: list[str]
    infoboxes: list[Infobox]
    # suggestions: list[str]
    # unresponsive_engines: list[str]


if __name__ == "__main__":
    mcp.run(transport="stdio")
