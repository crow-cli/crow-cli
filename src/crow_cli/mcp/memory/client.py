"""Manual smoke script for the three memory tools.

Runs against a live MCP server (which must be reachable) reading the
shared sqlite db (~/.agents/crow/crow.db). Not part of pytest — run directly:

    uv run python src/crow_cli/mcp/memory/client.py [session_id]
"""

import asyncio
import sys

from fastmcp import Client

client = Client("main.py")

SESSION = sys.argv[1] if len(sys.argv) > 1 else None


def _text(result) -> str:
    if hasattr(result, "data") and result.data:
        return str(result.data)
    if result.content:
        return "\n".join(str(c.text) for c in result.content if hasattr(c, "text"))
    return str(result)


async def show(title: str, tool: str, args: dict):
    print("=" * 70)
    print(f"{title}: {tool}({args})")
    print("=" * 70)
    print(_text(await client.call_tool(tool, args)))
    print()


async def main():
    async with client:
        print("TOOLS:")
        for t in await client.list_tools():
            print(f"  - {t.name}")
        print()

        await show("Sessions by activity", "list_sessions", {"limit": 10})
        await show("Cross-session discovery", "query_memory", {"query": "memory", "limit": 5})

        if SESSION:
            await show("Bare tail peek", "query_session", {"session_id": SESSION})
            await show("Head (first message)", "query_session",
                       {"session_id": SESSION, "order": "asc"})
            await show("Recent 5", "query_session", {"session_id": SESSION, "limit": 5})
            await show("Semantic in-session", "query_session",
                       {"session_id": SESSION, "query": "memory", "context": 2, "limit": 5})
            await show("Keyword in-session", "query_session",
                       {"session_id": SESSION, "query": "memory",
                        "search_type": "keyword", "limit": 5})
        else:
            print("(pass a session_id arg to exercise query_session)")


if __name__ == "__main__":
    asyncio.run(main())
