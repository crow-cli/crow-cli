"""
Real LLM compaction test runner.

Usage:
    uv --project . run test_compact_run.py case_04_unexecuted_tools
    uv --project . run test_compact_run.py --all
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from crow_cli.agent.compact import (
    _clean_messages,
    _collect_tool_call_ids,
    _collect_tool_response_ids,
    _fill_missing_tool_responses,
    compact,
)
from crow_cli.agent.configure import Config, get_default_config_dir
from crow_cli.agent.db import create_database
from crow_cli.agent.llm import configure_llm
from crow_cli.agent.session import Session

FIXTURE_DIR = Path(__file__).parent / "compact_fixtures"
TEST_DB = "/tmp/compact-test.db"


def load_fixture(name: str) -> dict:
    path = FIXTURE_DIR / f"{name}.json"
    if not path.exists():
        print(f"❌ Fixture not found: {path}")
        sys.exit(1)
    return json.loads(path.read_text())


def list_fixtures():
    return sorted([p.stem for p in FIXTURE_DIR.glob("*.json")])


def make_session(fixture_name: str, messages: list[dict]) -> Session:
    """Build a minimal Session object for compaction testing."""
    Path(TEST_DB).unlink(missing_ok=True)

    session = Session(
        agent_id=f"{fixture_name}-1",
        session_id=fixture_name,
        agent_idx=1,
        db_uri=f"sqlite:///{TEST_DB}",
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

    create_database(session.db_uri)
    return session


async def run_case(fixture_name: str, llm):
    """Run compaction for a single fixture with real LLM."""
    fixture = load_fixture(fixture_name)
    messages = fixture["messages"]

    print(f"\n{'=' * 70}")
    print(f"  FIXTURE: {fixture_name}")
    print(f"  {fixture['description']}")
    print(f"  Messages: {fixture['message_count']}")
    print(f"{'=' * 70}")

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
    missing = call_ids - response_ids
    print(f"\n  Tool call IDs: {call_ids}")
    print(f"  Tool response IDs: {response_ids}")
    print(f"  Missing: {missing}")

    session = make_session(fixture_name, messages)
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


async def main():
    parser = argparse.ArgumentParser(description="Run compaction tests with real LLM")
    parser.add_argument(
        "fixture", nargs="?", default=None, help="Fixture name or 'all'"
    )
    args = parser.parse_args()

    if args.fixture == "all" or args.fixture is None:
        fixtures = list_fixtures()
    else:
        fixtures = [args.fixture]

    config = Config.load()
    config.config_dir = Path(
        "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/.crow"
    )
    provider = next(iter(config.llm.providers.values()))
    llm = configure_llm(provider=provider, debug=False)

    for name in fixtures:
        await run_case(name, llm)


if __name__ == "__main__":
    asyncio.run(main())
