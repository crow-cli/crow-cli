"""
Generate JSON fixtures from real conversation data for compaction testing.

Extracts real messages from crow-new.db and slices at every possible
compaction point. Each fixture is a JSON file representing the message
history at a point where compaction could trigger.
"""

import json
from pathlib import Path

SRC_DB = "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/.crow/crow-new.db"
FIXTURE_DIR = Path(
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/compact_fixtures"
)
FIXTURE_DIR.mkdir(parents=True, exist_ok=True)


def load_messages():
    """Load real messages from DB."""
    import sqlite3

    conn = sqlite3.connect(SRC_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT data FROM messages WHERE agent_id='chubby-ambitious-carp-of-certainty-0' ORDER BY id"
    ).fetchall()
    conn.close()
    return [json.loads(r["data"]) for r in rows]


def save_fixture(name: str, messages: list[dict], description: str):
    """Save messages as JSON fixture with metadata."""
    fixture = {
        "name": name,
        "description": description,
        "message_count": len(messages),
        "messages": messages,
    }
    path = FIXTURE_DIR / f"{name}.json"
    path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False))
    print(f"  {path.name}: {len(messages)} messages")


def generate_fixtures():
    """Slice real conversation at every possible compaction point."""
    messages = load_messages()
    print(f"Loaded {len(messages)} messages from real conversation\n")

    # Case 1: Just system + user (no assistant response yet)
    # Compaction wouldn't trigger (too few messages), but good baseline
    save_fixture(
        "case_01_system_user_only",
        messages[0:2],
        "Just system + user messages. Too short to compact.",
    )

    # Case 2: Assistant with only reasoning_content (no content, no tool_calls)
    # Simulated by stripping tool_calls from message 3
    msg_no_tools = json.loads(json.dumps(messages[0:3]))
    msg_no_tools[2] = {
        "role": "assistant",
        "content": "",
        "reasoning_content": "Let me explore the codebase structure...",
    }
    save_fixture(
        "case_02_reasoning_only",
        msg_no_tools,
        "Assistant with only reasoning_content. No tool_calls, no content.",
    )

    # Case 3: Assistant with reasoning + content, no tool_calls
    msg_content_only = json.loads(json.dumps(messages[0:3]))
    msg_content_only[2] = {
        "role": "assistant",
        "content": "I'll look at the codebase structure.",
        "reasoning_content": "Let me explore...",
    }
    save_fixture(
        "case_03_content_only",
        msg_content_only,
        "Assistant with reasoning_content + content. No tool_calls.",
    )

    # Case 4: Assistant with tool_calls, NO tool responses yet
    # Real message 3 has 2 tool_calls, no responses
    save_fixture(
        "case_04_unexecuted_tools",
        json.loads(json.dumps(messages[0:3])),
        "Assistant with tool_calls but no tool responses. All tools pending.",
    )

    # Case 5: All tool responses present, last message is assistant (with more tool_calls)
    # Messages 0-6: system, user, assistant[2 tools], 2 tools, assistant[2 tools]
    save_fixture(
        "case_05_mid_conversation_all_responded",
        json.loads(json.dumps(messages[0:7])),
        "Mid-conversation: all tool responses present, last msg is assistant with new tool_calls.",
    )

    # Case 6: Same as case 5 but one tool response missing
    # Remove message 4 (second tool response of first assistant)
    msg_partial = json.loads(json.dumps(messages[0:7]))
    msg_partial.pop(4)  # Remove call_288156... response
    save_fixture(
        "case_06_partial_tool_responses",
        msg_partial,
        "Mid-conversation: one tool response missing from first assistant's tool_calls.",
    )

    # Case 7: All tool responses present, last message is assistant (final, no tool_calls)
    # Full conversation through message 9
    save_fixture(
        "case_07_complete_turn",
        json.loads(json.dumps(messages)),
        "Complete turn: all tool responses present, last msg is assistant with no tool_calls.",
    )

    # Case 8: Full conversation but last assistant message stripped to reasoning only
    msg_reasoning_end = json.loads(json.dumps(messages))
    msg_reasoning_end[-1] = {
        "role": "assistant",
        "content": "",
        "reasoning_content": "Let me summarize what I found...",
    }
    save_fixture(
        "case_08_reasoning_ending",
        msg_reasoning_end,
        "Full conversation but last assistant has only reasoning_content.",
    )

    # Case 9: Full conversation but last assistant has reasoning + content
    msg_content_ending = json.loads(json.dumps(messages))
    msg_content_ending[-1] = {
        "role": "assistant",
        "content": "Here's what I found in the codebase...",
        "reasoning_content": "Let me summarize...",
    }
    save_fixture(
        "case_09_content_ending",
        msg_content_ending,
        "Full conversation but last assistant has reasoning + content.",
    )

    print(f"\nGenerated 9 fixtures in {FIXTURE_DIR}")


if __name__ == "__main__":
    generate_fixtures()
