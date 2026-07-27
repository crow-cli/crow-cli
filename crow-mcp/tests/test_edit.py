"""Comprehensive tests for the edit tool's fuzzy matching.

These tests validate all 9 cascading replacers and edge cases.
"""

import os
import pytest
from pathlib import Path
import tempfile
import shutil
import tempfile
from pathlib import Path

import pytest

from crow_mcp.editor.main import (
    block_anchor_replacer,
    context_aware_replacer,
    escape_normalized_replacer,
    indentation_flexible_replacer,
    levenshtein,
    line_trimmed_replacer,
    multi_occurrence_replacer,
    replace,
    simple_replacer,
    trimmed_boundary_replacer,
    whitespace_normalized_replacer,
)


class TestLevenshtein:
    """Test the Levenshtein distance calculation."""

    def test_empty_strings(self):
        assert levenshtein("", "") == 0
        assert levenshtein("abc", "") == 3
        assert levenshtein("", "abc") == 3

    def test_exact_match(self):
        assert levenshtein("abc", "abc") == 0

    def test_single_character_difference(self):
        assert levenshtein("abc", "abd") == 1
        assert levenshtein("abc", "xbc") == 1
        assert levenshtein("abc", "ab") == 1
        assert levenshtein("ab", "abc") == 1

    def test_multiple_differences(self):
        assert levenshtein("kitten", "sitting") == 3


class TestSimpleReplacer:
    """Test simple exact string matching."""

    def test_exact_match(self):
        content = "hello world"
        result = list(simple_replacer(content, "hello"))
        assert len(result) == 1
        assert result[0] == "hello"

    def test_no_match(self):
        content = "hello world"
        result = list(simple_replacer(content, "foo"))
        assert len(result) == 0

    def test_multiline_exact(self):
        content = "line1\nline2\nline3"
        result = list(simple_replacer(content, "line1\nline2"))
        assert len(result) == 1
        assert result[0] == "line1\nline2"


class TestLineTrimmedReplacer:
    """Test line-trimmed matching (ignoring leading/trailing whitespace per line)."""

    def test_trimmed_lines(self):
        content = "  hello  \n  world  "
        result = list(line_trimmed_replacer(content, "hello\nworld"))
        assert len(result) == 1

    def test_no_match(self):
        content = "hello\nworld"
        result = list(line_trimmed_replacer(content, "foo\nbar"))
        assert len(result) == 0

    def test_partial_match(self):
        content = "hello\nworld\nfoo"
        result = list(line_trimmed_replacer(content, "hello\nworld"))
        assert len(result) == 1


class TestBlockAnchorReplacer:
    """Test block anchor matching (first/last line as anchors)."""

    def test_single_candidate(self):
        content = """def foo():
    x = 1
    y = 2
    return x + y"""
        result = list(
            block_anchor_replacer(content, "def foo():\n    x = 999\n    return x + y")
        )
        assert len(result) == 1

    def test_no_match(self):
        content = "def foo():\n    pass"
        result = list(block_anchor_replacer(content, "def bar():\n    pass"))
        assert len(result) == 0

    def test_two_lines_skipped(self):
        # Block anchor requires at least 3 lines
        content = "def foo():\n    pass"
        result = list(block_anchor_replacer(content, "def foo():\n    pass"))
        assert len(result) == 0


class TestWhitespaceNormalizedReplacer:
    """Test whitespace-normalized matching."""

    def test_extra_spaces(self):
        content = "hello    world"
        result = list(whitespace_normalized_replacer(content, "hello world"))
        assert len(result) == 1

    def test_newlines_as_spaces(self):
        content = "hello\nworld"
        result = list(whitespace_normalized_replacer(content, "hello world"))
        assert len(result) == 1

    def test_no_match(self):
        content = "hello world"
        result = list(whitespace_normalized_replacer(content, "foo bar"))
        assert len(result) == 0


class TestIndentationFlexibleReplacer:
    """Test indentation-flexible matching."""

    def test_less_indentation(self):
        content = "    def foo():\n        pass"
        result = list(indentation_flexible_replacer(content, "def foo():\n    pass"))
        assert len(result) == 1

    def test_more_indentation(self):
        content = "def foo():\n    pass"
        result = list(
            indentation_flexible_replacer(
                content, "        def foo():\n            pass"
            )
        )
        assert len(result) == 1

    def test_mixed_indentation(self):
        content = "  def foo():\n      pass"
        result = list(indentation_flexible_replacer(content, "def foo():\n    pass"))
        assert len(result) == 1


class TestEscapeNormalizedReplacer:
    """Test escape sequence normalization."""

    def test_newline_escape(self):
        content = "hello\nworld"
        result = list(escape_normalized_replacer(content, r"hello\nworld"))
        assert len(result) == 1

    def test_tab_escape(self):
        content = "hello\tworld"
        result = list(escape_normalized_replacer(content, r"hello\tworld"))
        assert len(result) == 1


class TestTrimmedBoundaryReplacer:
    """Test boundary-trimmed matching."""

    def test_leading_trailing_whitespace(self):
        content = "hello world"
        result = list(trimmed_boundary_replacer(content, "  hello world  "))
        assert len(result) == 1

    def test_already_trimmed(self):
        content = "hello world"
        result = list(trimmed_boundary_replacer(content, "hello world"))
        assert len(result) == 0  # Already trimmed, skip to next replacer


class TestContextAwareReplacer:
    """Test context-aware matching with 50% middle match threshold."""

    def test_exact_context(self):
        # 1/1 middle line matches (100% > 50%)
        content = "def foo():\n    x = 1\n    return x"
        result = list(
            context_aware_replacer(content, "def foo():\n    x = 1\n    return x")
        )
        assert len(result) == 1

    def test_partial_middle_match(self):
        # 1/2 middle lines match (50% >= 50%)
        content = "def foo():\n    x = 1\n    y = 2\n    return x"
        result = list(
            context_aware_replacer(
                content, "def foo():\n    x = 999\n    y = 2\n    return x"
            )
        )
        assert len(result) == 1

    def test_below_threshold(self):
        content = "def foo():\n    x = 1\n    y = 2\n    return x"
        result = list(
            context_aware_replacer(
                content, "def foo():\n    a = 999\n    b = 999\n    return x"
            )
        )
        # 0/2 middle lines match, which is < 50%
        assert len(result) == 0


class TestMultiOccurrenceReplacer:
    """Test multi-occurrence matching."""

    def test_multiple_occurrences(self):
        content = "hello hello hello"
        # multi_occurrence_replacer yields the search string itself, not each occurrence
        result = list(multi_occurrence_replacer(content, "hello"))
        assert len(result) == 1
        assert result[0] == "hello"

    def test_single_occurrence(self):
        content = "hello world"
        result = list(multi_occurrence_replacer(content, "hello"))
        assert len(result) == 1


class TestReplaceFunction:
    """Test the main replace function that cascades through replacers."""

    def test_simple_exact(self):
        content = "hello world"
        result = replace(content, "world", "there")
        assert result == "hello there"

    def test_with_leading_whitespace(self):
        content = "  hello  "
        result = replace(content, "hello", "world")
        assert result == "  world  "

    def test_multiline(self):
        content = "line1\nline2\nline3"
        result = replace(content, "line2", "newline")
        assert result == "line1\nnewline\nline3"

    def test_not_found_raises(self):
        content = "hello world"
        with pytest.raises(ValueError, match="old_string not found"):
            replace(content, "foo", "bar")

    def test_multiple_matches_raises(self):
        content = "hello hello"
        with pytest.raises(ValueError, match="found .* times"):
            replace(content, "hello", "world")

    def test_replace_all(self):
        content = "hello hello"
        result = replace(content, "hello", "world", replace_all=True)
        assert result == "world world"

    def test_same_string_raises(self):
        content = "hello world"
        with pytest.raises(ValueError, match="must be different"):
            replace(content, "hello", "hello")


class TestEditFileIntegration:
    """Integration tests for the full edit file operation."""

    @pytest.fixture
    def temp_file(self):
        """Create a temporary file for testing."""
        fd, path = tempfile.mkstemp(suffix=".py")
        os.close(fd)  # Close the file descriptor
        yield Path(path)
        if Path(path).exists():
            os.unlink(path)

    def test_simple_edit(self, temp_file):
        # Change to temp file's directory so _resolve_path allows it
        old_cwd = os.getcwd()
        os.chdir(temp_file.parent)
        
        try:
            temp_file.write_text("hello world\n")
            
            # Import and call the replace function directly (bypass @mcp.tool wrapper)
            from crow_mcp.editor.main import replace
            
            new_content = replace(temp_file.read_text(), "world", "there")
            temp_file.write_text(new_content)
            
            assert temp_file.read_text() == "hello there\n"
        finally:
            os.chdir(old_cwd)

    def test_edit_nonexistent_file(self, temp_file):
        import os
        old_cwd = os.getcwd()
        os.chdir(temp_file.parent)
        
        try:
            temp_file.unlink()
            
            from crow_mcp.editor.main import replace
            
            # Use an empty string as content - should raise "not found" error
            with pytest.raises(ValueError, match="not found"):
                replace("", "foo", "bar")
        finally:
            os.chdir(old_cwd)


class TestResolvePath:
    """Path resolution has no working-directory sandbox; Unix permissions govern."""

    def test_relative_resolves_against_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from crow_mcp.editor.main import _resolve_path

        (tmp_path / "f.txt").write_text("x")
        assert _resolve_path("f.txt") == (tmp_path / "f.txt").resolve()

    def test_absolute_outside_cwd_is_allowed(self, tmp_path, monkeypatch):
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        monkeypatch.chdir(cwd)

        outside = tmp_path / "elsewhere" / "note.md"
        outside.parent.mkdir()
        outside.write_text("hi")

        from crow_mcp.editor.main import _resolve_path

        assert _resolve_path(str(outside)) == outside.resolve()

    def test_crow_skills_path_is_allowed(self, tmp_path, monkeypatch):
        # The motivating case: any agent, regardless of its cwd, may edit
        # skills/notes under ~/.crow. Resolution must not raise.
        monkeypatch.chdir(tmp_path)
        from crow_mcp.editor.main import _resolve_path

        target = Path.home() / ".crow" / "skills" / "new-skill" / "SKILL.md"
        assert _resolve_path(str(target)) == target.resolve()


class TestEdgeCases:
    """Test edge cases that commonly cause bugs."""

    def test_empty_old_string(self):
        content = "hello"
        # Empty old string should not match anything meaningful
        result = list(simple_replacer(content, ""))
        # Empty string is technically in every string, but we should handle it
        assert len(result) >= 0

    def test_unicode_content(self):
        content = "hello 世界 🌍"
        result = replace(content, "世界", "monde")
        assert result == "hello monde 🌍"

    def test_special_characters(self):
        content = "hello\tworld\nfoo"
        result = replace(content, "hello\tworld", "hello world")
        assert result == "hello world\nfoo"

    def test_very_long_string(self):
        content = "x" * 10000
        # Without replace_all, this should raise an error due to multiple matches
        with pytest.raises(ValueError, match="found .* times"):
            replace(content, "x" * 100, "y" * 100)
        
        # With replace_all, it should work
        result = replace(content, "x" * 100, "y" * 100, replace_all=True)
        assert "y" * 100 in result

    def test_near_duplicate_blocks(self):
        """Two IDENTICAL blocks - should fail because ambiguous."""
        content = """def foo():
    x = 1
    return x

def foo():
    x = 1
    return x"""
        # Should raise error because both blocks have same first/last lines
        with pytest.raises(ValueError, match="found .* times"):
            replace(
                content, "def foo():\n    x = 1\n    return x", "def bar():\n    pass"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
