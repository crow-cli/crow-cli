"""The terminal MCP tool — cwd routing, driven through a REAL in-process
fastmcp Client (the shape the agent uses, meta included). Spawns real
shells; commands are stateless and bounded by timeout.
"""

import os

import pytest
from fastmcp import Client

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mcp_app():
    from crow_cli.mcp.server.app import mcp
    import crow_cli.mcp.terminal.main  # noqa: F401 — registers the tool

    return mcp


async def _call(mcp_app, command, cwd=None, **kwargs):
    async with Client(mcp_app) as client:
        if cwd:
            kwargs["meta"] = {"cwd": cwd, "session_id": "test-owner"}
        result = await client.call_tool("terminal", {"command": command}, **kwargs)
    return result.content[0].text


async def test_schema_hides_context(mcp_app):
    """The LLM sees only the command args — ctx (and the cwd/session_id
    riding the call meta) is filtered out of the schema."""
    async with Client(mcp_app) as client:
        tools = await client.list_tools()
    [tool] = [t for t in tools if t.name == "terminal"]
    assert set(tool.inputSchema.get("properties", {}).keys()) == {
        "command",
        "is_input",
        "timeout",
        "reset",
    }


async def test_echo(mcp_app):
    out = await _call(mcp_app, "echo hello-crow", cwd="/tmp")
    assert "hello-crow" in out
    assert "exit code 0" in out


async def test_stderr_is_captured(mcp_app):
    """stderr is merged into the returned output (an agent needs it to debug)."""
    out = await _call(mcp_app, "bash -c 'echo oops >&2'", cwd="/tmp")
    assert "oops" in out


async def test_command_error_text_captured(mcp_app):
    """A failing command surfaces its error text in the output."""
    out = await _call(mcp_app, "ls /definitely/not/here", cwd="/tmp")
    assert "No such file or directory" in out


async def test_chained_commands(mcp_app):
    out = await _call(mcp_app, "echo alpha && echo beta", cwd="/tmp")
    assert "alpha" in out and "beta" in out


async def test_meta_cwd_routes_the_shell(mcp_app, tmp_path):
    """The caller-injected cwd (the ACP session's) decides the shell's
    directory — NOT the server process's launch dir."""
    out = await _call(mcp_app, "pwd", cwd=str(tmp_path))
    assert str(tmp_path) in out
    assert os.getcwd() not in out


async def test_no_meta_falls_back_to_process_cwd(mcp_app, tmp_path, monkeypatch):
    """A bare caller (no meta) gets the server process's cwd — the
    historical single-session behavior."""
    monkeypatch.chdir(tmp_path)
    out = await _call(mcp_app, "pwd")
    assert str(tmp_path) in out


async def test_sessions_isolated_per_cwd(mcp_app, tmp_path):
    """Each cwd gets its own terminal session: shells in different
    directories never share state."""
    out_a = await _call(mcp_app, "pwd", cwd="/tmp")
    out_b = await _call(mcp_app, "pwd", cwd=str(tmp_path))
    assert "/tmp" in out_a and str(tmp_path) in out_b


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
