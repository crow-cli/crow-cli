import asyncio

from fastmcp import Client

client = Client("main.py")


def _text(result) -> str:
    """Extract text from CallToolResult."""
    if hasattr(result, "data") and result.data:
        return str(result.data)
    if result.content:
        return "\n".join(str(c.text) for c in result.content if hasattr(c, "text"))
    return str(result)


async def test_discovery():
    """Test 1: Discovery mode — search across all sessions."""
    print("=" * 60)
    print("TEST 1: Discovery mode (query='cheese')")
    print("=" * 60)
    result = await client.call_tool("query_memory", {"query": "cheese", "limit": 5})
    print(_text(result))
    print()


async def test_browse_session():
    """Test 2: Browse mode — list messages in a session."""
    print("=" * 60)
    print("TEST 2: Browse session (no query)")
    print("=" * 60)
    result = await client.call_tool(
        "query_memory",
        {"session_id": "fuzzy-metal-gorilla-of-masquerade", "limit": 10},
    )
    print(_text(result))
    print()


async def test_deep_dive():
    """Test 3: Deep dive — search within a session."""
    print("=" * 60)
    print("TEST 3: Deep dive (session + query)")
    print("=" * 60)
    result = await client.call_tool(
        "query_memory",
        {
            "session_id": "fuzzy-metal-gorilla-of-masquerade",
            "query": "sqlalchemy",
            "limit": 10,
        },
    )
    print(_text(result))
    print()


async def test_with_context():
    """Test 4: Deep dive with context window."""
    print("=" * 60)
    print("TEST 4: Deep dive with context=3")
    print("=" * 60)
    result = await client.call_tool(
        "query_memory",
        {
            "session_id": "fuzzy-metal-gorilla-of-masquerade",
            "query": "sqlalchemy",
            "context": 3,
            "limit": 20,
        },
    )
    print(_text(result))
    print()


async def test_with_thinking():
    """Test 5: Include thinking content."""
    print("=" * 60)
    print("TEST 5: mode='with_thinking'")
    print("=" * 60)
    result = await client.call_tool(
        "query_memory",
        {
            "session_id": "fuzzy-metal-gorilla-of-masquerade",
            "query": "sqlalchemy",
            "mode": "with_thinking",
            "context": 2,
            "limit": 10,
        },
    )
    print(_text(result))
    print()


async def test_with_tools():
    """Test 6: Include tool calls and results."""
    print("=" * 60)
    print("TEST 6: mode='with_tools'")
    print("=" * 60)
    result = await client.call_tool(
        "query_memory",
        {
            "session_id": "fuzzy-metal-gorilla-of-masquerade",
            "query": "terminal",
            "mode": "with_tools",
            "context": 2,
            "limit": 10,
        },
    )
    print(_text(result))
    print()


async def test_full_mode():
    """Test 7: Full mode — everything."""
    print("=" * 60)
    print("TEST 7: mode='full'")
    print("=" * 60)
    result = await client.call_tool(
        "query_memory",
        {
            "session_id": "fuzzy-metal-gorilla-of-masquerade",
            "query": "sqlalchemy",
            "mode": "full",
            "context": 2,
            "limit": 10,
        },
    )
    print(_text(result))
    print()


async def test_pagination():
    """Test 8: Pagination with offset."""
    print("=" * 60)
    print("TEST 8: Pagination (offset=5, limit=5)")
    print("=" * 60)
    result = await client.call_tool(
        "query_memory",
        {
            "session_id": "fuzzy-metal-gorilla-of-masquerade",
            "limit": 5,
            "offset": 5,
        },
    )
    print(_text(result))
    print()


async def test_agent_idx_filter():
    """Test 9: Filter by agent_idx within session."""
    print("=" * 60)
    print("TEST 9: agent_idx=1 filter")
    print("=" * 60)
    result = await client.call_tool(
        "query_memory",
        {
            "session_id": "fuzzy-metal-gorilla-of-masquerade",
            "agent_idx": 1,
            "limit": 5,
        },
    )
    print(_text(result))
    print()


async def test_time_filter():
    """Test 10: Time range filtering."""
    print("=" * 60)
    print("TEST 10: Time filter (after='2026-05-24T13:00:00')")
    print("=" * 60)
    result = await client.call_tool(
        "query_memory",
        {
            "session_id": "fuzzy-metal-gorilla-of-masquerade",
            "after": "2026-05-24T13:00:00",
            "limit": 10,
        },
    )
    print(_text(result))
    print()


async def test_no_matches():
    """Test 11: Query that returns no results."""
    print("=" * 60)
    print("TEST 11: No matches (query='xyznonexistent')")
    print("=" * 60)
    result = await client.call_tool(
        "query_memory",
        {
            "session_id": "fuzzy-metal-gorilla-of-masquerade",
            "query": "xyznonexistent",
        },
    )
    print(_text(result))
    print()


async def test_list_tools():
    """Sanity check: list available tools."""
    print("=" * 60)
    print("TOOL LIST")
    print("=" * 60)
    tools = await client.list_tools()
    for tool in tools:
        print(f"  - {tool.name}: {tool.description[:80]}...")
    print()


async def main():
    async with client:
        await test_list_tools()
        await test_discovery()
        await test_browse_session()
        await test_deep_dive()
        await test_with_context()
        await test_with_thinking()
        await test_with_tools()
        await test_full_mode()
        await test_pagination()
        await test_agent_idx_filter()
        await test_time_filter()
        await test_no_matches()


if __name__ == "__main__":
    asyncio.run(main())
