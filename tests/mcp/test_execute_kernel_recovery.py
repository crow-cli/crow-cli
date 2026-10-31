"""The kernel must survive junk on its sockets, and reset must always work.

Two failures met here and each one alone was fatal.

``Bad address (src/fq.cpp:56)`` is libzmq aborting the PROCESS. It happens when
two threads read the same socket, which is exactly what a timed-out cell did:
its poll loop kept running while the next call started another one. The MCP
server died with it, the kernel saw its parent exit, and every later call —
``reset=True`` included — failed with "Connection closed".

``ValueError: b'<IDS|MSG>' is not in list`` is jupyter_client's frame parser
rejecting a frame that is not a Jupyter message. The bytes are junk; the socket
is fine. It used to escape the poll loop, end the cell, and leave the client
wedged.
"""

import queue
import sys
import threading
import time

import pytest

from crow_cli.mcp2.execute import main as execute_main
from crow_cli.mcp2.execute.kernel import OCCUPIED, CrowKernel, KernelDead, _Inflight


def _stream(text: str, msg_id: str = "m1") -> dict:
    return {
        "msg_type": "stream",
        "parent_header": {"msg_id": msg_id},
        "content": {"name": "stdout", "text": text},
    }


def _idle(msg_id: str = "m1") -> dict:
    return {
        "msg_type": "status",
        "parent_header": {"msg_id": msg_id},
        "content": {"execution_state": "idle"},
    }


def _reply(msg_id: str = "m1") -> dict:
    return {"parent_header": {"msg_id": msg_id}, "content": {"status": "ok"}}


class FakeClient:
    """A kernel client whose channels are scripts rather than sockets."""

    def __init__(self, iopub, shell=None):
        self._iopub = list(iopub)
        self._shell = list(shell if shell is not None else [_reply()])
        self.executed = []
        self.stopped = False

    def execute(self, code):
        self.executed.append(code)
        return "m1"

    def get_iopub_msg(self, timeout=None):
        if not self._iopub:
            raise queue.Empty
        item = self._iopub.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def get_shell_msg(self, timeout=0):
        if not self._shell:
            raise queue.Empty
        return self._shell.pop(0)

    def stop_channels(self):
        self.stopped = True


def bare_kernel(client) -> CrowKernel:
    """A CrowKernel without a subprocess: only the poll loop is under test."""
    kernel = CrowKernel.__new__(CrowKernel)
    kernel.client = client
    kernel._lock = threading.Lock()
    kernel._cancelled = threading.Event()
    kernel._inflight = None
    kernel.dead = False
    return kernel


def test_an_unparseable_frame_does_not_end_the_cell():
    client = FakeClient([ValueError("no DELIM"), _stream("hello"), _idle()])
    result = bare_kernel(client).execute("print('hello')", timeout=5)

    assert result.text == "hello"
    assert result.status == "ok"
    assert client.executed == ["print('hello')"]


def test_a_read_error_marks_the_kernel_dead():
    client = FakeClient([RuntimeError("socket closed")])
    kernel = bare_kernel(client)

    with pytest.raises(KernelDead):
        kernel.execute("print(1)", timeout=1)

    assert kernel.dead is True


def test_a_second_cell_is_refused_rather_than_read_concurrently():
    """The abort was two readers on one socket. Refusing is the fix."""
    client = FakeClient([_stream("x"), _idle()])
    kernel = bare_kernel(client)
    kernel._lock.acquire()  # another cell owns the kernel

    result = kernel.execute("print('second')", timeout=1)

    assert result.busy_notice == OCCUPIED
    assert client.executed == [], "the socket must not be touched"


def test_an_abandoned_cell_is_collected_by_the_next_call():
    """The cell outlives the call that started it; its bytes stay here."""
    client = FakeClient([_stream("later "), _stream("output"), _idle()])
    kernel = bare_kernel(client)
    kernel._inflight = _Inflight(msg_id="m1", raw=bytearray(b"already "))

    result = kernel.execute("", timeout=5)

    assert result.text == "already later output"
    assert kernel._inflight is None
    assert client.executed == []


def test_shutdown_returns_while_a_cell_holds_the_kernel():
    """Reset is the one thing that has to work when nothing else does."""
    kernel = bare_kernel(FakeClient([]))
    held = threading.Event()

    def hold():
        kernel._lock.acquire()
        held.set()
        time.sleep(1.5)
        kernel._lock.release()

    threading.Thread(target=hold, daemon=True).start()
    assert held.wait(5)

    started = time.monotonic()
    kernel.shutdown()
    elapsed = time.monotonic() - started

    assert elapsed < 0.5, "shutdown waited on the busy cell"
    assert kernel.dead is True
    assert kernel._cancelled.is_set()


def test_a_dead_kernel_is_replaced_instead_of_reused(monkeypatch):
    class Dead:
        dead = True

        def __init__(self):
            self.shut = False

        def shutdown(self):
            self.shut = True

    class Fresh:
        dead = False

        def __init__(self, *a, **kw):
            pass

    dead = Dead()
    monkeypatch.setattr(execute_main, "_kernels", {"k": dead})
    monkeypatch.setattr(execute_main, "CrowKernel", Fresh)
    monkeypatch.setattr(execute_main, "_run_prelude", lambda *a, **kw: None)

    kernel = execute_main.get_kernel("k", "/tmp")

    assert isinstance(kernel, Fresh)
    assert dead.shut is True


# -- against a real kernel ---------------------------------------------------


@pytest.fixture
def real_kernel():
    kernel = CrowKernel(python_path=sys.executable)
    try:
        yield kernel
    finally:
        kernel.shutdown()


def test_a_real_cell_runs_and_a_concurrent_one_is_refused(real_kernel):
    done = threading.Event()

    def slow():
        real_kernel.execute("import time; time.sleep(2); print('slow')", timeout=10)
        done.set()

    threading.Thread(target=slow, daemon=True).start()
    time.sleep(0.3)  # let the slow cell take the kernel

    result = real_kernel.execute("print('other')", timeout=0.5)
    assert result.busy_notice == OCCUPIED

    assert done.wait(20)
    assert real_kernel.execute("print('alive')", timeout=15).text.strip() == "alive"


@pytest.mark.asyncio
async def test_reset_works_while_a_cell_is_still_running():
    """The scenario that killed the session: a busy cell, then reset=True."""
    import json

    from fastmcp import Client

    from crow_cli.mcp2.server import mcp

    async with Client(mcp) as client:

        async def call(code, **args):
            result = await client.call_tool(
                "execute",
                {"code": code, **args},
                meta={"session_id": "reset-while-busy"},
            )
            return json.loads(result.content[0].text)

        busy = await call("import time; time.sleep(30)", timeout=0.5)
        assert busy["timed_out"] is True

        reset = await call("", reset=True)
        assert reset["exit_code"] == 0
        assert "reset" in reset["output"].lower()

        after = await call("print('fresh kernel')", timeout=30)
        assert "fresh kernel" in after["output"]
