"""Tests for the memory query helpers (pure functions — no database)."""

import pytest

from crow_cli.mcp.memory.main import (
    ContentMode,
    _apply_context_window,
    _build_excerpt,
    _extract_display_text,
    _extract_searchable_text,
    _fmt_when,
    _format_message,
    _snippet,
)


class TestExtractSearchableText:
    def test_user_string_content(self):
        assert _extract_searchable_text({"role": "user", "content": "hi"}) == "hi"

    def test_user_block_content(self):
        data = {
            "role": "user",
            "content": [{"type": "text", "text": "hello"}, {"type": "image"}],
        }
        assert _extract_searchable_text(data) == "hello"

    def test_assistant_includes_reasoning_and_tools(self):
        data = {
            "role": "assistant",
            "content": "answer",
            "reasoning_content": "thought",
            "tool_calls": [{"function": {"name": "read", "arguments": "{}"}}],
        }
        text = _extract_searchable_text(data)
        assert "answer" in text
        assert "thought" in text
        assert "read" in text

    def test_tool_role(self):
        data = {"role": "tool", "content": "result", "tool_call_id": "id1"}
        text = _extract_searchable_text(data)
        assert "result" in text and "id1" in text


class TestExtractDisplayText:
    def test_user_blocks(self):
        data = {
            "role": "user",
            "content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}],
        }
        assert _extract_display_text(data) == "a b"

    def test_assistant(self):
        assert _extract_display_text({"role": "assistant", "content": "hi"}) == "hi"

    def test_unknown_role(self):
        assert _extract_display_text({"role": "system"}) == ""


class TestFormatMessage:
    def test_user(self):
        out = _format_message({"role": "user", "content": "hi"}, ContentMode.CONVERSATION)
        assert "**USER**" in out and "hi" in out

    def test_assistant_conversation_hides_thinking(self):
        data = {"role": "assistant", "content": "ans", "reasoning_content": "think"}
        out = _format_message(data, ContentMode.CONVERSATION)
        assert "ans" in out and "think" not in out

    def test_assistant_with_thinking(self):
        data = {"role": "assistant", "content": "ans", "reasoning_content": "think"}
        out = _format_message(data, ContentMode.WITH_THINKING)
        assert "think" in out and "ans" in out

    def test_tool_hidden_in_conversation(self):
        assert (
            _format_message({"role": "tool", "content": "r"}, ContentMode.CONVERSATION)
            is None
        )

    def test_tool_shown_with_tools(self):
        out = _format_message({"role": "tool", "content": "r"}, ContentMode.WITH_TOOLS)
        assert "TOOL_RESULT" in out and "r" in out

    def test_tool_truncates_long_content(self):
        out = _format_message(
            {"role": "tool", "content": "x" * 600}, ContentMode.WITH_TOOLS
        )
        assert "truncated" in out

    def test_empty_user_returns_none(self):
        assert (
            _format_message({"role": "user", "content": ""}, ContentMode.CONVERSATION)
            is None
        )

    def test_agent_idx_tagged_in_prefix(self):
        data = {"role": "assistant", "content": "hi", "_created_at": "03:42:27", "_agent_idx": 2}
        out = _format_message(data, ContentMode.CONVERSATION)
        assert "[03:42:27 · a2]" in out

    def test_agent_idx_without_timestamp(self):
        data = {"role": "assistant", "content": "hi", "_agent_idx": 3}
        out = _format_message(data, ContentMode.CONVERSATION)
        assert "[a3]" in out


class TestBuildExcerpt:
    def test_highlight_centered(self):
        data = {"role": "user", "content": "the quick brown fox jumps"}
        assert "brown" in _build_excerpt(data, "brown")

    def test_no_match_returns_head(self):
        data = {"role": "user", "content": "abcdef"}
        assert _build_excerpt(data, "zzz", max_len=3).startswith("abc")

    def test_long_text_ellipsis(self):
        data = {"role": "user", "content": "x" * 300}
        assert _build_excerpt(data, "nope", max_len=120).endswith("...")


class TestApplyContextWindow:
    def test_zero_context_returns_matches_only(self):
        assert _apply_context_window(list(range(10)), {5}, context=0) == [5]

    def test_context_expands_window(self):
        assert _apply_context_window(list(range(10)), {5}, context=2) == [3, 4, 5, 6, 7]

    def test_context_clamped_at_bounds(self):
        assert _apply_context_window(list(range(5)), {0}, context=3) == [0, 1, 2, 3]

    def test_empty_matches(self):
        assert _apply_context_window(list(range(5)), set(), context=2) == []


class TestFmtWhen:
    def test_trims_to_minute(self):
        assert _fmt_when("2026-07-08T03:42:27.123456+00:00") == "2026-07-08 03:42"

    def test_empty(self):
        assert _fmt_when("") == "—"


class TestSnippet:
    def test_assistant_text(self):
        assert _snippet({"role": "assistant", "content": "hello world"}, "assistant") == "hello world"

    def test_collapses_whitespace(self):
        assert _snippet({"role": "assistant", "content": "a\n\n  b"}, "assistant") == "a b"

    def test_truncates_long(self):
        out = _snippet({"role": "assistant", "content": "x" * 100}, "assistant", max_len=10)
        assert out == "x" * 10 + "…"

    def test_escapes_pipes(self):
        assert _snippet({"role": "assistant", "content": "a | b"}, "assistant") == "a \\| b"

    def test_none_data(self):
        assert _snippet(None, None) == "—"

    def test_empty_falls_back_to_role(self):
        assert _snippet({"role": "tool", "content": ""}, "tool") == "(tool)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
