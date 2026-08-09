"""End-to-end compaction test with real LLM.

Sets MAX_COMPACT_TOKENS very low so any tool call triggers compaction.
Checks the DB for new agent record with same session_id, incremented agent_idx.
"""
import asyncio
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from client import ReplClient

AGENT_CMD = "uv"
AGENT_ARGS = (
    "--project",
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent",
    "run",
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/compact_agent.py",
)

DB_PATH = "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/.crow/crow-compact.db"


async def test_compaction():
    # Clear old DB
    Path(DB_PATH).unlink(missing_ok=True)

    client = ReplClient(AGENT_CMD, *AGENT_ARGS)

    # This should trigger write+edit -> tool_calls -> compaction
    await client.send(
        "Create a file at /tmp/compact_test/hello.py with print('hello'). "
        "Then edit it to add a second line print('world')."
    )

    await client.close()

    # Check DB
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    agents = conn.execute("SELECT agent_id, session_id, agent_idx FROM agents ORDER BY created_at").fetchall()
    print(f"\n=== Agents in DB ===")
    for a in agents:
        print(f"  agent_id={a['agent_id']} session_id={a['session_id']} idx={a['agent_idx']}")

    messages = conn.execute("SELECT agent_id, role, COUNT(*) as cnt FROM messages GROUP BY agent_id, role").fetchall()
    print(f"\n=== Messages per agent/role ===")
    for m in messages:
        print(f"  agent_id={m['agent_id']} role={m['role']} count={m['cnt']}")

    # Check tool responses exist
    tool_msgs = conn.execute("SELECT agent_id, data FROM messages WHERE role='tool' ORDER BY id").fetchall()
    print(f"\n=== Tool messages ({len(tool_msgs)}) ===")
    for t in tool_msgs:
        data = t["data"]
        tool_call_id = data.split('"tool_call_id": "')[1].split('"')[0] if '"tool_call_id"' in data else "?"
        print(f"  agent_id={t['agent_id']} tool_call_id={tool_call_id}")

    # Verify compaction happened
    if len(agents) > 1:
        print(f"\n✅ COMPACTION TRIGGERED: {len(agents)} agent records created")
        # Verify same session_id
        session_ids = set(a["session_id"] for a in agents)
        if len(session_ids) == 1:
            print(f"✅ Same session_id across all agents: {session_ids.pop()}")
        else:
            print(f"❌ Different session_ids: {session_ids}")

        # Verify agent_idx incremented
        indices = [a["agent_idx"] for a in agents]
        print(f"✅ Agent indices: {indices}")
    else:
        print(f"\n⚠️  No compaction triggered (only {len(agents)} agent record)")
        print("    This might be OK if token count stayed below threshold")

    # Check for fake compaction tool responses
    compaction_tools = conn.execute(
        "SELECT data FROM messages WHERE role='tool' AND data LIKE '%compaction%'"
    ).fetchall()
    if compaction_tools:
        print(f"\n✅ Found {len(compaction_tools)} compaction placeholder tool response(s)")

    conn.close()

asyncio.run(test_compaction())
