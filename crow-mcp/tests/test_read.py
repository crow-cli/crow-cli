"""Tests for the read tool and its pure helpers."""

import pytest

from crow_mcp.read.main import (
    _format_with_line_numbers,
    _is_binary_file,
    read,
)


class TestIsBinaryFile:
    def test_text_file(self, tmp_path):
        p = tmp_path / "a.txt"
        p.write_text("hello world\nline two\n")
        assert _is_binary_file(p) is False

    def test_binary_null_byte(self, tmp_path):
        p = tmp_path / "b.bin"
        p.write_bytes(b"abc\x00def")
        assert _is_binary_file(p) is True

    def test_empty_file_not_binary(self, tmp_path):
        p = tmp_path / "empty.txt"
        p.write_bytes(b"")
        assert _is_binary_file(p) is False

    def test_missing_file_not_binary(self, tmp_path):
        # OSError opening → treated as not binary.
        assert _is_binary_file(tmp_path / "nope.txt") is False


class TestFormatWithLineNumbers:
    def test_basic_numbering(self):
        out = _format_with_line_numbers("a\nb\nc")
        lines = out.split("\n")
        assert lines[0].endswith("→a")
        assert lines[1].endswith("→b")
        assert lines[2].endswith("→c")

    def test_offset_and_limit(self):
        content = "\n".join(f"line{i}" for i in range(1, 11))  # line1..line10
        out = _format_with_line_numbers(content, offset=2, limit=3)
        # offset is a 0-indexed start here → lines[2:5] = line3..line5
        assert "line3" in out
        assert "line5" in out
        assert "line2" not in out
        assert "line6" not in out

    def test_long_line_truncated(self):
        out = _format_with_line_numbers("x" * 3000)  # > MAX_LINE_LENGTH (2000)
        assert "[line truncated]" in out

    def test_empty_content(self):
        out = _format_with_line_numbers("")
        assert "1" in out  # a single empty line, numbered 1


class TestReadTool:
    async def test_read_simple(self, tmp_path):
        p = tmp_path / "f.txt"
        p.write_text("hello\nworld\n")
        out = await read(file_path=str(p))
        assert "hello" in out and "world" in out
        assert "→" in out

    async def test_read_missing(self, tmp_path):
        out = await read(file_path=str(tmp_path / "nope.txt"))
        assert "Error" in out and "does not exist" in out

    async def test_read_directory(self, tmp_path):
        out = await read(file_path=str(tmp_path))
        assert "Error" in out and "directory" in out

    async def test_read_empty(self, tmp_path):
        p = tmp_path / "empty.txt"
        p.write_text("")
        out = await read(file_path=str(p))
        assert "empty contents" in out

    async def test_read_binary(self, tmp_path):
        p = tmp_path / "b.bin"
        p.write_bytes(b"abc\x00def")
        out = await read(file_path=str(p))
        assert "binary" in out.lower()

    async def test_read_offset_limit(self, tmp_path):
        p = tmp_path / "f.txt"
        p.write_text("\n".join(f"line{i}" for i in range(1, 11)))
        out = await read(file_path=str(p), offset=3, limit=2)
        # user offset is 1-indexed → internal start 2 → line3, line4
        assert "line3" in out and "line4" in out
        assert "line5" not in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
