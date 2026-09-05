"""Zero-day imports: fresh kernels (start AND reset) come up with
crow_cli.tools ambient via the prelude, and the in-kernel subtool register
captures calls made inside cells for the server-side drain.
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
    yield
    from crow_cli.mcp.execute.main import shutdown_all

    shutdown_all()


async def _call(mcp_app, code, session_id="prelude-test", reset=False):
    async with Client(mcp_app) as client:
        meta = {"session_id": session_id}
        args = {"code": code}
        if reset:
            args["reset"] = True
        result = await client.call_tool("execute", args, meta=meta)
    return result.content[0].text


async def test_edit_is_ambient_on_start(mcp_app):
    """The prelude ran: bare `edit` resolves with no import in the cell."""
    out = await _call(mcp_app, "edit")
    assert "crow_cli.tools.edit.edit" in out and "EditResult" in out


async def test_edit_runs_and_registers(mcp_app, tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("one\ntwo\n")
    out = await _call(mcp_app, f"r = await edit({str(f)!r}, 'one', 'ONE')\nr")
    assert "EditResult" in out and "+1/-1" in out
    assert f.read_text().startswith("ONE")

    # The entry sits in kernel memory, stamped and drainable. Identity is
    # None until the per-cell prologue (begin_cell) is wired into execute.
    out2 = await _call(
        mcp_app,
        "from crow_cli.tools.register import drain\n"
        "[(e.tool, e.status, e.result_kind, e.parent_tool_call_id) for e in drain()]",
    )
    assert "('edit', 'completed', 'diff', None)" in out2


async def test_edit_failure_traceback_and_failed_entry(mcp_app, tmp_path):
    out = await _call(
        mcp_app, f"await edit({str(tmp_path / 'ghost.txt')!r}, 'a', 'b')"
    )
    assert "EditError" in out and "does not exist" in out
    out2 = await _call(
        mcp_app,
        "from crow_cli.tools.register import drain\n"
        "[(e.tool, e.status) for e in drain()]",
    )
    assert "('edit', 'failed')" in out2


async def test_edit_ambient_after_reset(mcp_app):
    """Reset goes through get_kernel too — the prelude reruns."""
    await _call(mcp_app, "", reset=True)
    out = await _call(mcp_app, "edit")
    assert "crow_cli.tools.edit.edit" in out and "EditResult" in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
