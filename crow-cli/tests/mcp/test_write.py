"""Tests for the write tool."""

import pytest

from crow_cli.mcp.write.main import write


class TestWriteTool:
    async def test_write_new_file(self, tmp_path):
        p = tmp_path / "out.txt"
        result = await write(file_path=str(p), content="hello\nworld\n")
        assert "Successfully wrote" in result
        assert p.read_text() == "hello\nworld\n"

    async def test_write_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "a" / "b" / "c.txt"
        result = await write(file_path=str(p), content="nested")
        assert "Successfully wrote" in result
        assert p.read_text() == "nested"

    async def test_write_overwrites(self, tmp_path):
        p = tmp_path / "out.txt"
        p.write_text("old content")
        await write(file_path=str(p), content="new")
        assert p.read_text() == "new"

    async def test_write_line_count(self, tmp_path):
        p = tmp_path / "out.txt"
        result = await write(file_path=str(p), content="a\nb\nc")
        # content.count("\n") + 1 == 3
        assert "3 lines" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
