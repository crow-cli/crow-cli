"""Tests for the terminal tool (spawns a real shell; bounded by timeout).

Commands are chosen to be stateless and to never kill the persistent shell
session (e.g. `false` for a non-zero exit instead of a bare `exit`).
"""

import pytest

# `from`-import (not `import ... as`) — the module sits in a circular import
# chain (terminal.main <-> server.main) that breaks the `import a.b.c as x` form.
from crow_mcp.terminal.main import terminal


class TestTerminalTool:
    async def test_echo(self):
        out = await terminal(command="echo hello-crow", timeout=20)
        assert "hello-crow" in out
        assert "exit code 0" in out

    async def test_stderr_is_captured(self):
        """stderr is merged into the returned output (an agent needs it to debug)."""
        out = await terminal(command="bash -c 'echo oops >&2'", timeout=20)
        assert "oops" in out

    async def test_command_error_text_captured(self):
        """A failing command surfaces its error text in the output."""
        out = await terminal(command="ls /definitely/not/here", timeout=20)
        assert "No such file or directory" in out

    async def test_chained_commands(self):
        out = await terminal(command="echo alpha && echo beta", timeout=20)
        assert "alpha" in out and "beta" in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
