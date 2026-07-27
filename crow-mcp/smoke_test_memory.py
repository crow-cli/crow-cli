"""Smoke tests for the query_memory MCP tool backed by crow-memory service.

Requires a running crow-memory service on localhost:8901 with test data.
Run: uv --project ~/src/crow-team/crow-cli/crow-mcp run python smoke_test_memory.py
"""

import asyncio
import sys

from crow_mcp.memory.main import query_memory, ContentMode, SearchType

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    status = "PASS" if condition else "FAIL"
    if not condition:
        failed += 1
    else:
        passed += 1
    msg = f"  [{status}] {name}"
    if detail and not condition:
        msg += f" — {detail}"
    print(msg)


async def main():
    global passed, failed

    # Seed check: browse mode should return messages
    print("\n=== BROWSE MODE ===")
    r = await query_memory(session_id="test-session", limit=5)
    check("browse returns markdown", r.startswith("## Session: test-session"))
    check("browse shows agent idx", "Agent: 1" in r)
    check("browse shows messages", "USER" in r or "ASSISTANT" in r)
    check("browse shows count", "Showing" in r)

    # Browse with mode=with_tools
    r = await query_memory(session_id="test-session", limit=5, mode=ContentMode.WITH_TOOLS)
    check("browse with_tools shows TOOL_CALL or TOOL_RESULT",
          "TOOL_CALL" in r or "TOOL_RESULT" in r)

    # Browse with mode=with_thinking
    r = await query_memory(session_id="test-session", limit=11, mode=ContentMode.WITH_THINKING)
    check("browse with_thinking shows thinking block",
          "thinking" in r.lower())

    # Browse nonexistent session
    r = await query_memory(session_id="nonexistent-session-xyz", limit=5)
    check("browse nonexistent returns no messages", "No messages" in r)

    # === DISCOVERY MODE (semantic, no session_id) ===
    print("\n=== DISCOVERY MODE (semantic) ===")
    r = await query_memory(query="vector database", limit=5)
    check("discovery returns table", "| session_id |" in r)
    check("discovery has score column", "score" in r.lower())
    check("discovery finds LanceDB message", "LanceDB" in r or "vector" in r.lower())

    # Discovery with nonsense query (semantic always returns something)
    r = await query_memory(query="xyznonexistent12345", limit=3)
    check("discovery nonsense still returns table (semantic has no threshold)",
          "| session_id |" in r)

    # Keyword discovery (not supported without session_id)
    r = await query_memory(query="test", search_type=SearchType.KEYWORD)
    check("keyword discovery returns guidance message",
          "not supported" in r.lower() or "session_id" in r.lower())

    # === DEEP DIVE MODE (session_id + query) ===
    print("\n=== DEEP DIVE MODE ===")

    # Semantic deep dive
    r = await query_memory(session_id="test-session", query="LanceDB",
                           search_type=SearchType.SEMANTIC, limit=5)
    check("semantic deep dive returns transcript", "## Session:" in r)
    check("semantic deep dive finds relevant content",
          "LanceDB" in r or "vector" in r.lower())

    # Keyword deep dive
    r = await query_memory(session_id="test-session", query="LanceDB",
                           search_type=SearchType.KEYWORD, limit=5)
    check("keyword deep dive returns transcript", "## Session:" in r)
    check("keyword deep dive finds exact match", "LanceDB" in r)

    # Both deep dive
    r = await query_memory(session_id="test-session", query="date",
                           search_type=SearchType.BOTH, limit=5)
    check("both deep dive returns transcript", "## Session:" in r)
    check("both deep dive finds date content", "date" in r.lower())

    # Deep dive with context window
    r = await query_memory(session_id="test-session", query="LanceDB",
                           search_type=SearchType.SEMANTIC, context=2, limit=20)
    check("context window returns more than just matches",
          r.count("**USER**") + r.count("**ASSISTANT**") >= 3)

    # Deep dive with no matches (keyword)
    r = await query_memory(session_id="test-session", query="xyznonexistent12345",
                           search_type=SearchType.KEYWORD)
    check("keyword no matches returns 'No matches'", "No matches" in r)

    # === MODE FILTERING ===
    print("\n=== MODE FILTERING ===")

    # conversation mode should NOT show tool results
    r = await query_memory(session_id="test-session", query="date",
                           search_type=SearchType.BOTH, mode=ContentMode.CONVERSATION,
                           context=3, limit=20)
    check("conversation mode hides TOOL_RESULT", "TOOL_RESULT" not in r)

    # full mode should show everything
    r = await query_memory(session_id="test-session", query="date",
                           search_type=SearchType.BOTH, mode=ContentMode.FULL,
                           context=3, limit=20)
    check("full mode shows TOOL_RESULT", "TOOL_RESULT" in r)
    check("full mode shows TOOL_CALL", "TOOL_CALL" in r)

    # === PAGINATION ===
    print("\n=== PAGINATION ===")
    r1 = await query_memory(session_id="test-session", limit=3)
    r2 = await query_memory(session_id="test-session", limit=3, offset=3)
    check("pagination returns different content", r1 != r2)

    # === SUMMARY ===
    print(f"\n{'='*60}")
    print(f"  {passed} passed, {failed} failed")
    print(f"{'='*60}")
    return failed == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
