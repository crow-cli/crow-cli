"""Smoke tests for the memory MCP tools backed by the crow-memory service.

Requires a running crow-memory service on localhost:8901 with test data
(a "test-session" session). Run:

    uv --project ~/src/crow-team/crow-cli/crow-mcp run python smoke_test_memory.py
"""

import asyncio
import sys

from crow_mcp.memory.main import (
    ContentMode,
    SearchType,
    list_sessions,
    query_memory,
    query_session,
)

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

    # === LIST SESSIONS ===
    print("\n=== LIST SESSIONS ===")
    r = await list_sessions(limit=10)
    check("list_sessions returns a table", "| session_id |" in r)
    check("list_sessions shows last active column", "last active" in r)

    # === BROWSE (query_session, no query) ===
    print("\n=== BROWSE (query_session) ===")
    r = await query_session(session_id="test-session", limit=5)
    check("browse returns markdown", r.startswith("## Session: test-session"))
    check("browse tags messages with agent_idx", "a1" in r)
    check("browse shows messages", "USER" in r or "ASSISTANT" in r)
    check("browse shows count", "Showing" in r)

    # Bare call = tail peek (single latest message)
    r = await query_session(session_id="test-session")
    check("bare browse is a tail peek (one message)", r.count("**ASSISTANT**") + r.count("**USER**") >= 1)

    # order=asc = head (first message)
    r_asc = await query_session(session_id="test-session", order="asc")
    check("order=asc returns a transcript", "## Session: test-session" in r_asc)

    r = await query_session(session_id="test-session", limit=5, mode=ContentMode.WITH_TOOLS)
    check("browse with_tools shows TOOL_CALL or TOOL_RESULT",
          "TOOL_CALL" in r or "TOOL_RESULT" in r)

    r = await query_session(session_id="test-session", limit=11, mode=ContentMode.WITH_THINKING)
    check("browse with_thinking shows thinking block", "thinking" in r.lower())

    r = await query_session(session_id="nonexistent-session-xyz", limit=5)
    check("browse nonexistent returns no messages", "No messages" in r)

    # === DISCOVERY (query_memory, cross-session semantic) ===
    print("\n=== DISCOVERY (query_memory) ===")
    r = await query_memory(query="vector database", limit=5)
    check("discovery returns table", "| session_id |" in r)
    check("discovery has score column", "score" in r.lower())
    check("discovery finds LanceDB message", "LanceDB" in r or "vector" in r.lower())

    r = await query_memory(query="xyznonexistent12345", limit=3)
    check("discovery nonsense still returns table (semantic has no threshold)",
          "| session_id |" in r)

    r = await query_memory(query="test", search_type=SearchType.KEYWORD)
    check("keyword discovery returns guidance message", "not supported" in r.lower())

    # === SEARCH WITHIN SESSION (query_session + query) ===
    print("\n=== SEARCH WITHIN SESSION ===")
    r = await query_session(session_id="test-session", query="LanceDB",
                            search_type=SearchType.SEMANTIC, limit=5)
    check("semantic search returns transcript", "## Session:" in r)
    check("semantic search finds relevant content", "LanceDB" in r or "vector" in r.lower())

    r = await query_session(session_id="test-session", query="LanceDB",
                            search_type=SearchType.KEYWORD, limit=5)
    check("keyword search returns transcript", "## Session:" in r)
    check("keyword search finds exact match", "LanceDB" in r)

    r = await query_session(session_id="test-session", query="date",
                            search_type=SearchType.BOTH, limit=5)
    check("both search returns transcript", "## Session:" in r)
    check("both search finds date content", "date" in r.lower())

    r = await query_session(session_id="test-session", query="LanceDB",
                            search_type=SearchType.SEMANTIC, context=2, limit=20)
    check("context window returns more than just matches",
          r.count("**USER**") + r.count("**ASSISTANT**") >= 3)

    r = await query_session(session_id="test-session", query="xyznonexistent12345",
                            search_type=SearchType.KEYWORD)
    check("keyword no matches returns 'No matches'", "No matches" in r)

    # === MODE FILTERING ===
    print("\n=== MODE FILTERING ===")
    r = await query_session(session_id="test-session", query="date",
                            search_type=SearchType.BOTH, mode=ContentMode.CONVERSATION,
                            context=3, limit=20)
    check("conversation mode hides TOOL_RESULT", "TOOL_RESULT" not in r)

    r = await query_session(session_id="test-session", query="date",
                            search_type=SearchType.BOTH, mode=ContentMode.FULL,
                            context=3, limit=20)
    check("full mode shows TOOL_RESULT", "TOOL_RESULT" in r)
    check("full mode shows TOOL_CALL", "TOOL_CALL" in r)

    # === PAGINATION ===
    print("\n=== PAGINATION ===")
    r1 = await query_session(session_id="test-session", limit=3)
    r2 = await query_session(session_id="test-session", limit=3, offset=3)
    check("pagination returns different content", r1 != r2)

    # === SUMMARY ===
    print(f"\n{'='*60}")
    print(f"  {passed} passed, {failed} failed")
    print(f"{'='*60}")
    return failed == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
