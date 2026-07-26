"""Tests for the terminal tool stub.

The terminal tool is a schema-only docstring holder: the model sees its
docstring for tool selection, but execution happens client-side (the Crow ACP
client owns a real PTY — see crow-cli's tests/unit/test_client_terminal.py).
Calling the MCP tool directly therefore raises NotImplementedError. These
tests lock in that contract and guard the docstring, which IS the product.
"""

import pytest

# `from`-import (not `import ... as`) — the module sits in a circular import
# chain (terminal.main <-> server.main) that breaks the `import a.b.c as x` form.
from crow_mcp.terminal.main import terminal


class TestTerminalStub:
    async def test_raises_not_implemented(self):
        """The tool is a schema holder; direct execution is delegated to the client."""
        with pytest.raises(NotImplementedError):
            await terminal(command="echo hello")

    async def test_raises_regardless_of_args(self):
        """No argument combination executes locally."""
        with pytest.raises(NotImplementedError):
            await terminal(command="ls", timeout=5, reset=True)

    async def test_error_points_to_client_execution(self):
        """The error explains where execution actually happens."""
        with pytest.raises(NotImplementedError) as excinfo:
            await terminal(command="x")
        msg = str(excinfo.value)
        assert "client-side terminal" in msg
        assert "LLM tool selection" in msg

    def test_docstring_is_the_schema(self):
        """The docstring is what the model sees — guard the key contract lines."""
        doc = terminal.__doc__
        assert doc is not None
        assert "bash command" in doc
        assert "FRESH shell" in doc
        assert "chain commands" in doc


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
