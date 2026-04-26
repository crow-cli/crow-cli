"""
Multi-compaction test: Launch an ACP agent with a large codebase context
and send multiple prompts to trigger repeated compaction.

After the test completes, it prints:
- Log file location
- Useful SQL queries to inspect compaction results in the database
"""

import asyncio
import json
import subprocess
from pathlib import Path

from client import ReplClient

DB_PATH = "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/.crow/crow-fresh.db"
LOG_DIR = "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/.crow/logs"

AGENT_CMD = "uv"
AGENT_ARGS = (
    "--project",
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent",
    "run",
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/multi_compact.py",
)

# Prompts designed to consume context and trigger repeated compaction
PROMPTS = [
    "Describe the overall structure of this codebase. What are the main projects and their purposes?",
    "Focus on the crow-cli project. How does the agent system work? Walk me through the main entry point, the react loop, and how compaction is triggered.",
    "Now look at the marimo project. How does its architecture differ from crow-cli? What are the key design decisions?",
    "Compare the database schemas between crow-cli and murder. What patterns do they share?",
    "Look at the libChatre project. How does its client-side architecture work? What frameworks does it use?",
]


def print_section(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def run_query(query: str) -> str:
    """Run a sqlite query and return formatted output."""
    try:
        result = subprocess.run(
            ["sqlite3", DB_PATH, query],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() or "(empty result)"
    except subprocess.TimeoutExpired:
        return "(query timed out)"
    except FileNotFoundError:
        return "(sqlite3 not found - install it or run queries manually)"
    except Exception as e:
        return f"(error: {e})"


def print_db_inspection():
    """Print useful queries to inspect compaction results."""
    print_section("DATABASE INSPECTION")
    print(f"\nDatabase: {DB_PATH}\n")

    queries = [
        (
            "Agent records (session_id, agent_id, agent_idx, status)",
            """
            .mode column
            .headers on
            SELECT session_id, agent_id, agent_idx, status, created_at
            FROM agents
            ORDER BY session_id, agent_idx;
            """,
        ),
        (
            "Message counts per agent",
            """
            .mode column
            .headers on
            SELECT a.agent_id, a.agent_idx, COUNT(m.id) as msg_count
            FROM agents a
            LEFT JOIN messages m ON a.agent_id = m.agent_id
            GROUP BY a.agent_id
            ORDER BY a.session_id, a.agent_idx;
            """,
        ),
        (
            "Agents with most messages (potential compaction failures)",
            """
            .mode column
            .headers on
            SELECT a.agent_id, a.agent_idx, COUNT(m.id) as msg_count
            FROM agents a
            LEFT JOIN messages m ON a.agent_id = m.agent_id
            GROUP BY a.agent_id
            HAVING msg_count > 5
            ORDER BY msg_count DESC;
            """,
        ),
        (
            "Session compaction chain",
            """
            .mode column
            .headers on
            SELECT session_id, agent_id, agent_idx,
                   (SELECT COUNT(*) FROM messages m WHERE m.agent_id = a.agent_id) as messages
            FROM agents a
            ORDER BY session_id, agent_idx;
            """,
        ),
        (
            "Duplicate agent_id check (should be empty)",
            """
            .mode column
            .headers on
            SELECT agent_id, COUNT(*) as cnt
            FROM agents
            GROUP BY agent_id
            HAVING cnt > 1;
            """,
        ),
    ]

    for desc, query in queries:
        print(f"\n--- {desc} ---")
        print(f'sqlite3 {DB_PATH} "{query.strip().replace(chr(10), " ")}"')
        result = run_query(query)
        print(result)


async def test():
    c = ReplClient(AGENT_CMD, *AGENT_ARGS)

    print_section("MULTI-COMPACTION TEST")
    print(f"Agent: {' '.join([AGENT_CMD] + list(AGENT_ARGS))}")
    print(f"DB:    {DB_PATH}")
    print(f"Logs:  {LOG_DIR}")
    print(f"\nSending {len(PROMPTS)} prompts to trigger repeated compaction...\n")

    for i, prompt in enumerate(PROMPTS, 1):
        print(f"\n{'─' * 60}")
        print(f"Prompt {i}/{len(PROMPTS)}")
        print(f"{'─' * 60}")
        await c.send(prompt)

    # Print final response
    print_section("FINAL AGENT RESPONSE")
    if c._session_id and c._session_id in c.conversation:
        msgs = c.conversation[c._session_id]
        for msg in msgs:
            if msg["role"] == "assistant":
                content = msg.get("content", "")
                print(content[:3000])
                if len(content) > 3000:
                    print(f"\n... (truncated, {len(content)} chars total)")

    await c.close()

    # Print log location
    print_section("LOG FILE")
    session_prefix = c._session_id if c._session_id else "unknown"
    log_file = f"{LOG_DIR}/crow-cli-{session_prefix}.log"
    print(f"\nLog: {log_file}")
    print(f"  tail -f {log_file}")
    print(f"  grep -i compact {log_file}")

    # Print database inspection queries
    print_db_inspection()


if __name__ == "__main__":
    asyncio.run(test())
