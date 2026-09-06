"""The execute MCP tool — a persistent IPython kernel (REPL) per session,
driven through a REAL in-process fastmcp Client (the shape the agent uses,
meta included). Spawns a real kernel subprocess with crow's interpreter;
state persists across calls within a session.
"""

import pytest
from fastmcp import Client

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mcp_app():
    from crow_cli.mcp.server.app import mcp
    import crow_cli.mcp.execute.main  # noqa: F401 — registers the tool

    return mcp


@pytest.fixture(autouse=True)
def _cleanup_kernels():
    """Shut down every kernel after each test so subprocesses never leak and
    state never bleeds between tests."""
    yield
    from crow_cli.mcp.execute.main import shutdown_all

    shutdown_all()


async def _call(mcp_app, code, session_id="test-session", cwd=None, reset=False):
    async with Client(mcp_app) as client:
        meta = {"session_id": session_id}
        if cwd:
            meta["cwd"] = cwd
        args = {"code": code}
        if reset:
            args["reset"] = True
        result = await client.call_tool("execute", args, meta=meta)
    return result.content[0].text


async def test_schema_hides_context(mcp_app):
    """The LLM sees only the model-facing args — code/reset/timeout. ctx (and
    the session_id/cwd/db_uri riding the call meta) is filtered out of the
    schema; timeout is deliberately visible (B2: the caller raises the ceiling
    for a long-running cell)."""
    async with Client(mcp_app) as client:
        tools = await client.list_tools()
    [tool] = [t for t in tools if t.name == "execute"]
    assert set(tool.inputSchema.get("properties", {}).keys()) == {
        "code",
        "reset",
        "timeout",
    }


async def test_no_out_n_in_output(mcp_app):
    """The REPL's display of the last expression is NOT a channel: a bare
    expression produces no output. print() is how code talks back."""
    out = await _call(mcp_app, "1 + 1")
    assert out == "[no output]"


async def test_state_persists_across_calls(mcp_app):
    """The whole point: a variable set in one call is alive in the next."""
    await _call(mcp_app, "x = 42", session_id="persist")
    out = await _call(mcp_app, "print(x * 2)", session_id="persist")
    assert out.strip() == "84"


async def test_stdout_captured(mcp_app):
    out = await _call(mcp_app, "print('hello-crow')")
    assert "hello-crow" in out


async def test_error_traceback_is_clean(mcp_app):
    """A raised exception surfaces an ANSI-stripped traceback, error-first."""
    out = await _call(mcp_app, "1/0")
    assert "ZeroDivisionError" in out
    assert "\x1b[" not in out  # no raw ANSI escapes


async def test_crow_interpreter_and_deps(mcp_app):
    """The kernel runs crow's OWN interpreter, so crow's deps are importable
    and sys.executable points inside the project venv."""
    ver = await _call(mcp_app, "import sqlalchemy; print(sqlalchemy.__version__)")
    assert "." in ver  # a version string like '2.0.51' came back
    exe = await _call(mcp_app, "import sys; print(sys.executable)")
    assert ".venv" in exe or "crow-cli" in exe


async def test_reset_clears_state(mcp_app):
    """reset=True shuts the kernel down and starts fresh — state is gone."""
    await _call(mcp_app, "y = 99", session_id="resettable")
    msg = await _call(mcp_app, "", session_id="resettable", reset=True)
    assert "reset" in msg.lower()
    out = await _call(mcp_app, "y", session_id="resettable")
    assert "NameError" in out


async def test_sessions_isolated(mcp_app):
    """Two session ids get two kernels: state never leaks between them."""
    await _call(mcp_app, "secret = 'alpha'", session_id="sess-a")
    out = await _call(mcp_app, "print(secret)", session_id="sess-b")
    assert "NameError" in out
    out_a = await _call(mcp_app, "print(secret)", session_id="sess-a")
    assert "alpha" in out_a


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
