"""The execute kernel's timeout path — regression for EXECUTE_TODO B2/B3/B4/B5.

A cell that outlives its timeout returns an honest "(kernel busy: …)" notice
instead of a bare, traceback-less ``Error:`` (an unhandled ``queue.Empty``
whose ``str()`` is empty), the cell is NOT killed, and — the subtle one — the
NEXT cell re-syncs via ``parent_header.msg_id`` filtering instead of
inheriting the stale cell's output. Before the fix, a timed-out cell left its
iopub messages (including its final ``status:idle``) queued, so the next
execute drained those and broke on the STALE idle, returning the PREVIOUS
cell's output and desyncing attribution by one until a kernel reset.

Plus the MCP tool's ``timeout`` argument (B2): the caller can raise the
ceiling for a long-running process, and it actually reaches the kernel.
"""

import sys

import pytest
from fastmcp import Client

from crow_cli.mcp.execute.kernel import CrowKernel


@pytest.fixture
def kernel():
    k = CrowKernel(python_path=sys.executable)
    try:
        yield k
    finally:
        k.shutdown()


def test_long_cell_returns_busy_not_bare_error(kernel):
    """B3/B5: a cell that outlives the timeout yields the honest busy notice,
    not an empty ``Error:``/exception — and the kernel survives it (still
    usable on the next call, not wedged, not killed)."""
    out = kernel.execute("import time; time.sleep(3); print('slept')", timeout=1)
    assert "kernel busy" in out
    assert kernel.execute("print('alive')", timeout=15).strip() == "alive"


def test_next_cell_resyncs_after_a_timeout(kernel):
    """B4: the cell after a timeout returns ITS OWN output, not the stale
    output of the cell that was still running. msg_id filtering re-syncs the
    stream with no kernel reset — the old code returned 'LATE' here."""
    busy = kernel.execute("import time; time.sleep(3); print('LATE')", timeout=1)
    assert "kernel busy" in busy
    # Waits for the kernel to free up, then returns its OWN output; the stale
    # 'LATE' (parent msg_id of the abandoned cell) must NOT be misattributed.
    out = kernel.execute("print('SECOND')", timeout=15)
    assert "SECOND" in out
    assert "LATE" not in out


@pytest.mark.asyncio
async def test_execute_tool_forwards_timeout():
    """B2: the MCP execute tool exposes ``timeout`` and forwards it to the
    kernel — a cell that outlives the PASSED timeout comes back busy, which
    the hardcoded 30s default could never have produced."""
    from crow_cli.mcp.server.app import mcp
    import crow_cli.mcp.execute.main  # noqa: F401 — registers the tool
    from crow_cli.mcp.execute.main import shutdown_all

    try:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "execute",
                {"code": "import time; time.sleep(3); print('done')", "timeout": 1},
                meta={"session_id": "timeout-test"},
            )
        text = result.content[0].text
        assert "kernel busy" in text
        assert "done" not in text
    finally:
        shutdown_all()
