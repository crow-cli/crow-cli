"""
Compaction tests using real conversation fixtures.

Tests the message manipulation logic of compact() against real data,
then runs actual compaction with real LLM.
"""

import asyncio
import json
from pathlib import Path

import pytest
from crow_cli.agent.compact import (
    _clean_messages,
    _collect_tool_call_ids,
    _collect_tool_response_ids,
    _fill_missing_tool_responses,
    compact,
)

FIXTURE_DIR = Path(__file__).parent / "compact_fixtures"


def load_fixture(name: str) -> dict:
    """Load a JSON fixture."""
    path = FIXTURE_DIR / f"{name}.json"
    return json.loads(path.read_text())


def list_fixtures():
    """List all fixture names."""
    return [p.stem for p in sorted(FIXTURE_DIR.glob("*.json"))]


# ── Logic tests: tool call ID collection ──────────────────────────


class TestCollectToolCallIds:
    """Test extraction of tool_call_ids from assistant messages."""

    def test_no_tool_calls(self):
        fixture = load_fixture("case_01_system_user_only")
        ids = _collect_tool_call_ids(fixture["messages"])
        assert ids == set()

    def test_reasoning_only(self):
        fixture = load_fixture("case_02_reasoning_only")
        ids = _collect_tool_call_ids(fixture["messages"])
        assert ids == set()

    def test_content_only(self):
        fixture = load_fixture("case_03_content_only")
        ids = _collect_tool_call_ids(fixture["messages"])
        assert ids == set()

    def test_unexecuted_tools(self):
        fixture = load_fixture("case_04_unexecuted_tools")
        ids = _collect_tool_call_ids(fixture["messages"])
        assert len(ids) == 2  # First assistant has 2 tool_calls

    def test_mid_conversation(self):
        fixture = load_fixture("case_05_mid_conversation_all_responded")
        ids = _collect_tool_call_ids(fixture["messages"])
        assert len(ids) == 4  # Two assistant messages, each with 2 tool_calls

    def test_complete_turn(self):
        fixture = load_fixture("case_07_complete_turn")
        ids = _collect_tool_call_ids(fixture["messages"])
        assert len(ids) == 4  # Only two assistant messages had tool_calls


class TestCollectToolResponseIds:
    """Test extraction of tool_call_ids from tool response messages."""

    def test_no_responses(self):
        fixture = load_fixture("case_04_unexecuted_tools")
        ids = _collect_tool_response_ids(fixture["messages"])
        assert ids == set()

    def test_partial_responses(self):
        fixture = load_fixture("case_06_partial_tool_responses")
        ids = _collect_tool_response_ids(fixture["messages"])
        assert len(ids) == 3  # One of 4 tool responses missing

    def test_all_responses(self):
        fixture = load_fixture("case_07_complete_turn")
        ids = _collect_tool_response_ids(fixture["messages"])
        assert len(ids) == 4  # All 4 tool responses present


class TestFillMissingToolResponses:
    """Test that missing tool responses get fake placeholders."""

    def test_no_missing(self):
        fixture = load_fixture("case_07_complete_turn")
        result = _fill_missing_tool_responses(fixture["messages"])
        # Should be same length - no missing responses
        assert len(result) == len(fixture["messages"])

    def test_unexecuted_tools_get_filled(self):
        fixture = load_fixture("case_04_unexecuted_tools")
        result = _fill_missing_tool_responses(fixture["messages"])
        # 3 original messages + 2 fake tool responses
        assert len(result) == 5
        # Last two should be tool responses
        assert result[-1]["role"] == "tool"
        assert result[-2]["role"] == "tool"
        assert "compaction" in result[-1]["content"].lower()

    def test_partial_get_only_missing_filled(self):
        fixture = load_fixture("case_06_partial_tool_responses")
        result = _fill_missing_tool_responses(fixture["messages"])
        # 6 original + 1 missing = 7
        assert len(result) == 7
        # Exactly one new tool response added
        tool_msgs = [m for m in result if m["role"] == "tool"]
        compaction_tools = [
            m for m in tool_msgs if "compaction" in m.get("content", "").lower()
        ]
        assert len(compaction_tools) == 1

    def test_preserves_existing_responses(self):
        fixture = load_fixture("case_06_partial_tool_responses")
        result = _fill_missing_tool_responses(fixture["messages"])
        # Existing tool responses should be untouched
        existing_ids = _collect_tool_response_ids(fixture["messages"])
        result_ids = _collect_tool_response_ids(result)
        assert existing_ids.issubset(result_ids)


class TestCleanMessages:
    """Test message normalization for LLM input."""

    def test_multimodal_content(self):
        """Content blocks with list format get normalized to string."""
        fixture = load_fixture("case_01_system_user_only")
        # User message has content as list: [{"type": "text", "text": "..."}]
        user_msg = fixture["messages"][1]
        assert isinstance(user_msg["content"], list)

        cleaned = _clean_messages(fixture["messages"])
        assert isinstance(cleaned[1]["content"], str)
        assert "Look through the murder directory" in cleaned[1]["content"]

    def test_preserves_tool_calls(self):
        """tool_calls field should be preserved."""
        fixture = load_fixture("case_04_unexecuted_tools")
        cleaned = _clean_messages(fixture["messages"])
        assert "tool_calls" in cleaned[2]

    def test_preserves_tool_call_id(self):
        """tool_call_id field should be preserved."""
        fixture = load_fixture("case_07_complete_turn")
        cleaned = _clean_messages(fixture["messages"])
        tool_msgs = [m for m in cleaned if m["role"] == "tool"]
        assert all("tool_call_id" in m for m in tool_msgs)


# ── Real LLM tests ────────────────────────────────────────────────


async def test_compact_with_real_llm():
    """Run compact() against real LLM for each fixture."""
    from crow_cli.agent.configure import Config, get_default_config_dir
    from crow_cli.agent.llm import configure_llm
    from crow_cli.agent.session import Session

    config = Config.load()
    config.config_dir = Path(
        "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/.crow"
    )

    provider = next(iter(config.llm.providers.values()))
    llm = configure_llm(provider=provider, debug=False)

    print(f"\n{'=' * 60}")
    print(f"  Running compact() with REAL LLM against {len(list_fixtures())} fixtures")
    print(f"{'=' * 60}")

    for fixture_name in list_fixtures():
        fixture = load_fixture(fixture_name)
        messages = fixture["messages"]

        # Build a minimal Session object (no DB, just in-memory)
        session = Session(
            agent_id=f"test-{fixture_name}-1",
            session_id=fixture_name,
            agent_idx=1,
            db_uri="sqlite:///:memory:",
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

        print(f"\n▶ {fixture_name} ({fixture['message_count']} messages)")
        print(f"   {fixture['description']}")

        try:
            result = await compact(
                session=session,
                llm=llm,
                cwd="/tmp",
                logger=None,  # Skip logging for cleaner output
            )

            # Verify result
            assert result.session_id == fixture_name
            assert result.agent_idx == 2
            assert len(result.messages) == 2  # system + summary
            assert result.messages[0]["role"] == "system"
            assert result.messages[1]["role"] == "assistant"
            summary = result.messages[1]["content"]
            assert len(summary) > 50, "Summary too short"

            print(f"   ✅ Compacted to {len(result.messages)} messages")
            print(f"   Summary: {summary[:100]}...")

        except Exception as e:
            print(f"   ❌ FAILED: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(test_compact_with_real_llm())
