"""
Single real LLM compaction test - no mocks, no truncation.
"""

import asyncio
import json
from pathlib import Path

from crow_cli.agent.compact import (
    _clean_messages,
    _collect_tool_call_ids,
    _collect_tool_response_ids,
    _fill_missing_tool_responses,
    compact,
)
from crow_cli.agent.configure import Config, get_default_config_dir
from crow_cli.agent.llm import configure_llm
from crow_cli.agent.session import Session

FIXTURE_DIR = Path(__file__).parent / "compact_fixtures"


def load_fixture(name: str) -> dict:
    path = FIXTURE_DIR / f"{name}.json"
    return json.loads(path.read_text())


async def test_case04_unexecuted_tools():
    """Case 4: Assistant with tool_calls but NO tool responses yet."""
    fixture = load_fixture("case_04_unexecuted_tools")
    messages = fixture["messages"]

    print(f"\n{'=' * 70}")
    print(f"  FIXTURE: {fixture['name']}")
    print(f"  {fixture['description']}")
    print(f"  Messages: {fixture['message_count']}")
    print(f"{'=' * 70}")

    # Show what we're feeding in
    for i, m in enumerate(messages):
        role = m.get("role")
        if role == "assistant":
            tcalls = m.get("tool_calls", [])
            tc_ids = [tc["id"] for tc in tcalls] if isinstance(tcalls, list) else []
            print(f"  [{i}] {role}: tool_calls={tc_ids}")
        else:
            content = str(m.get("content", ""))[:120]
            print(f"  [{i}] {role}: {content}")

    call_ids = _collect_tool_call_ids(messages)
    response_ids = _collect_tool_response_ids(messages)
    print(f"\n  Tool call IDs: {call_ids}")
    print(f"  Tool response IDs: {response_ids}")
    print(f"  Missing: {call_ids - response_ids}")

    # Build session
    config = Config.load()
    config.config_dir = Path(
        "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/.crow"
    )
    provider = next(iter(config.llm.providers.values()))
    llm = configure_llm(provider=provider, debug=False)

    session = Session(
        agent_id="test-case04-1",
        session_id="case_04",
        agent_idx=1,
        db_uri="sqlite:////tmp/compact-test-case04.db",
        cwd="/tmp",
    )
    session.messages = messages
    session.model_identifier = "qwen3.5-plus"
    session.tools = [
        {
            "type": "function",
            "function": {
                "name": "terminal",
                "description": "Execute terminal command",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    session.request_params = {"temperature": 0.2}
    session.prompt_id = "test-prompt"
    session.prompt_args = {"workspace": "/tmp"}
    session._db = None
    session._model = None

    # Create tables in the in-memory DB
    from crow_cli.agent.db import create_database
    create_database(session.db_uri)

    print(f"\n  Running compact()...")
    result = await compact(session=session, llm=llm, cwd="/tmp", logger=None)

    print(f"\n{'=' * 70}")
    print(f"  RESULT")
    print(f"{'=' * 70}")
    print(f"  New agent_id: {result.agent_id}")
    print(f"  New session_id: {result.session_id}")
    print(f"  New agent_idx: {result.agent_idx}")
    print(f"  Messages after: {len(result.messages)}")
    print()
    for i, m in enumerate(result.messages):
        content = m.get("content", "")
        print(f"  [{i}] {m['role']}:")
        print(f"  {content}")
        print()


if __name__ == "__main__":
    asyncio.run(test_case04_unexecuted_tools())
