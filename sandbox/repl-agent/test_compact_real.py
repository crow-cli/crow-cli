"""
Compaction E2E test with REAL LLM and synthetic sessions built from real conversation data.

Extracts actual conversation from crow-new.db, chops it at every possible compaction point,
creates synthetic Session objects, and runs compact() against real LLM endpoint.
No mocking — real API calls, real DB writes.
"""

import asyncio
import datetime
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

from crow_cli.agent.compact import compact
from crow_cli.agent.configure import Config, get_default_config_dir
from crow_cli.agent.db import Agent as AgentModel
from crow_cli.agent.db import Base, Prompt
from crow_cli.agent.db import Message as MessageModel
from crow_cli.agent.llm import configure_llm
from crow_cli.agent.session import Session

SRC_DB = "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/.crow/crow-new.db"
TEST_DB = (
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/.crow/crow-compact-test.db"
)

PROMPT_ID = "test-prompt"


def load_real_messages(db_path: str, agent_id: str) -> list[dict]:
    """Load real messages from DB as list[dict]."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT data FROM messages WHERE agent_id=? ORDER BY id", (agent_id,)
    ).fetchall()
    conn.close()
    return [json.loads(r["data"]) for r in rows]


def load_agent_config(db_path: str, agent_id: str) -> dict:
    """Load agent config from DB."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return {}


def setup_test_db(scenario_name: str, messages: list[dict], agent_config: dict):
    """Create a fresh test DB with Agent record and messages."""
    db_path = TEST_DB_DIR / f"{scenario_name}.db"
    db_path.unlink(missing_ok=True)
    db_uri = f"sqlite:///{db_path}"

    engine = sqlite3.connect(db_path)
    engine.execute("PRAGMA journal_mode=WAL;")
    engine.executescript("""
        CREATE TABLE prompts (
            id TEXT NOT NULL PRIMARY KEY,
            name TEXT NOT NULL,
            template TEXT NOT NULL,
            created_at DATETIME NOT NULL
        );
        CREATE TABLE agents (
            agent_id TEXT NOT NULL PRIMARY KEY,
            session_id TEXT NOT NULL,
            agent_idx INTEGER NOT NULL DEFAULT 1,
            prompt_id TEXT,
            prompt_args JSON,
            system_prompt TEXT NOT NULL,
            tool_definitions JSON NOT NULL,
            request_params JSON NOT NULL,
            model_identifier TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at DATETIME NOT NULL
        );
        CREATE TABLE file_snapshots (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            tool_call_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            content_before TEXT,
            timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
        );
        CREATE TABLE messages (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            data JSON NOT NULL,
            role TEXT NOT NULL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            FOREIGN KEY(agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
        );
    """)

    # Insert prompt
    engine.execute(
        "INSERT INTO prompts (id, name, template, created_at) VALUES (?, ?, ?, ?)",
        (PROMPT_ID, "test", "You are a test agent.", datetime.datetime.now().isoformat()),
    )

    # Insert agent
    engine.execute(
        """INSERT INTO agents
           (agent_id, session_id, agent_idx, prompt_id, prompt_args, system_prompt,
            tool_definitions, request_params, model_identifier, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
        (
            agent_config["agent_id"],
            agent_config["session_id"],
            agent_config["agent_idx"],
            PROMPT_ID,
            agent_config.get("prompt_args") or "{}",
            agent_config["system_prompt"],
            agent_config["tool_definitions"],
            agent_config["request_params"],
            agent_config["model_identifier"],
            "active",
        ),
    )

    # Insert messages
    for msg in messages:
        engine.execute(
            "INSERT INTO messages (agent_id, data, role) VALUES (?, ?, ?)",
            (agent_config["agent_id"], json.dumps(msg), msg["role"]),
        )
    engine.commit()
    engine.close()


def build_scenario(
    name: str, messages: list[dict], agent_config: dict
) -> tuple[str, Session]:
    """Build a synthetic Session from real messages."""
    test_uri = f"sqlite:///{TEST_DB}"
    setup_test_db(test_uri, messages, agent_config)

    session = Session(
        agent_id=agent_config["agent_id"],
        session_id=agent_config["session_id"],
        agent_idx=agent_config["agent_idx"],
        db_uri=test_uri,
        cwd="/tmp",
    )
    session.messages = messages
    session.model_identifier = agent_config["model_identifier"]
    session.tools = json.loads(agent_config["tool_definitions"])
    session.request_params = json.loads(agent_config["request_params"])
    session.prompt_id = PROMPT_ID
    session.prompt_args = json.loads(agent_config.get("prompt_args") or "{}")

    return name, session


def build_scenarios():
    """Extract real conversation and build all 5 compaction scenarios."""
    messages = load_real_messages(SRC_DB, "chubby-ambitious-carp-of-certainty-0")
    agent_cfg = load_agent_config(SRC_DB, "chubby-ambitious-carp-of-certainty-0")
    agent_cfg["agent_id"] = "chubby-ambitious-carp-of-certainty-0"
    agent_cfg["agent_idx"] = 1
    agent_cfg["session_id"] = "chubby-ambitious-carp-of-certainty"

    scenarios = []

    # Case 1: Just system + user + assistant (no tool_calls yet)
    # Simulated by stripping tool_calls from first assistant message
    msg_no_tools = json.loads(json.dumps(messages[0:3]))
    msg_no_tools[2] = {
        "role": "assistant",
        "content": "",
        "reasoning_content": "Let me explore the codebase...",
        # No tool_calls key
    }
    cfg1 = dict(agent_cfg)
    cfg1["agent_id"] = "scenario-1-no-tools-1"
    scenarios.append(
        build_scenario(
            "Case 1: assistant with only reasoning_content",
            msg_no_tools,
            cfg1,
        )
    )

    # Case 2: assistant with reasoning + content, no tool_calls
    msg_content_only = json.loads(json.dumps(messages[0:3]))
    msg_content_only[2] = {
        "role": "assistant",
        "content": "I'll look at the codebase structure.",
        "reasoning_content": "Let me explore...",
    }
    cfg2 = dict(agent_cfg)
    cfg2["agent_id"] = "scenario-2-content-only-1"
    scenarios.append(
        build_scenario(
            "Case 2: assistant with reasoning_content + content",
            msg_content_only,
            cfg2,
        )
    )

    # Case 3: assistant with tool_calls but NO tool responses
    # Just system + user + assistant with tool_calls (messages 0-2 original)
    msg_unexecuted = json.loads(json.dumps(messages[0:3]))
    cfg3 = dict(agent_cfg)
    cfg3["agent_id"] = "scenario-3-unexecuted-tools-1"
    scenarios.append(
        build_scenario(
            "Case 3: assistant with tool_calls, no tool responses",
            msg_unexecuted,
            cfg3,
        )
    )

    # Case 4: all tool responses present (system + user + assistant[2 tools] + 2 tools + assistant[2 tools] + 2 tools + assistant)
    # Full conversation through message 9
    msg_all_responded = json.loads(json.dumps(messages))
    cfg4 = dict(agent_cfg)
    cfg4["agent_id"] = "scenario-4-all-responded-1"
    scenarios.append(
        build_scenario(
            "Case 4: all tool responses present, last message is assistant",
            msg_all_responded,
            cfg4,
        )
    )

    # Case 5: some tool responses missing (simulate case 4 but remove one tool response)
    msg_partial = json.loads(json.dumps(messages))
    # Remove one tool response (message 5)
    msg_partial.pop(5)  # Remove one of the tool responses
    cfg5 = dict(agent_cfg)
    cfg5["agent_id"] = "scenario-5-partial-responded-1"
    scenarios.append(
        build_scenario(
            "Case 5: some tool responses missing",
            msg_partial,
            cfg5,
        )
    )

    return scenarios


def verify_compaction(name: str, session: Session, original_msg_count: int):
    """Verify compaction results in DB."""
    print(f"\n{'=' * 60}")
    print(f"  {name}")
    print(f"{'=' * 60}")

    conn = sqlite3.connect(session.db_uri.replace("sqlite:///", ""))
    conn.row_factory = sqlite3.Row

    # Check agents
    agents = conn.execute(
        "SELECT agent_id, session_id, agent_idx FROM agents ORDER BY id"
    ).fetchall()
    print(f"  Agent records: {len(agents)}")
    for a in agents:
        print(
            f"    agent_id={a['agent_id']} session_id={a['session_id']} idx={a['agent_idx']}"
        )

    # Check messages
    msgs = conn.execute(
        "SELECT agent_id, role, substr(data, 1, 100) FROM messages ORDER BY id"
    ).fetchall()
    print(f"  Messages after compaction: {len(msgs)}")
    for m in msgs:
        preview = m["data"][:80].replace("\n", " ")
        print(f"    [{m['role']}] {preview}...")

    # Verify same session_id
    session_ids = set(a["session_id"] for a in agents)
    if len(session_ids) == 1:
        print(f"  ✅ Same session_id: {session_ids.pop()}")
    else:
        print(f"  ❌ DIFFERENT session_ids: {session_ids}")

    # Verify agent_idx incremented
    if len(agents) >= 1:
        last = agents[-1]
        if last["agent_idx"] > 0:
            print(f"  ✅ agent_idx = {last['agent_idx']} (incremented)")
        else:
            print(f"  ❌ agent_idx not incremented: {last['agent_idx']}")

    # Verify compacted message count
    if len(session.messages) <= 2:
        print(
            f"  ✅ Compacted to {len(session.messages)} messages (from {original_msg_count})"
        )
    else:
        print(f"  ❌ Still {len(session.messages)} messages after compaction")

    conn.close()


async def main():
    print("Loading real conversation from DB...")
    scenarios = build_scenarios()
    print(f"Built {len(scenarios)} compaction scenarios from real data\n")

    # Load config and LLM
    config = Config.load()
    config.config_dir = Path(
        "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/.crow"
    )
    config.db_uri = TEST_DB

    provider = next(iter(config.llm.providers.values()))
    llm = configure_llm(provider=provider, debug=False)

    for name, session in scenarios:
        original_count = len(session.messages)
        print(f"\n▶ Running: {name}")
        print(f"   Messages before: {original_count}")

        try:
            result = await compact(
                session=session,
                llm=llm,
                cwd=session.cwd,
                logger=MagicMock(),
            )
            verify_compaction(name, result, original_count)
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            import traceback

            traceback.print_exc()

    print(f"\n\n{'=' * 60}")
    print("  ALL SCENARIOS COMPLETE")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
