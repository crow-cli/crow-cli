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

import asyncio
import json
import queue
import sys
import threading
import time

import pytest

from crow_cli.mcp2.execute import kernel as kernel_mod
from crow_cli.mcp2.execute import main as execute_main
from crow_cli.mcp2.execute.kernel import (
    ABANDON_S,
    OCCUPIED,
    CrowKernel,
    KernelDead,
    _Inflight,
)


@pytest.fixture(autouse=True)
def _reap_kernels():
    """``_kernels`` is module state and each entry is a live child process."""
    yield
    execute_main.shutdown_all()


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
    kernel._abandon = threading.Event()
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


# -- cancel: the kernel has to come back -------------------------------------
#
# The lock above stops two readers aborting the process. It cannot stop an
# abandoned cell OWNING the kernel, which is the other half of the same
# incident: the user pressed cancel on a cell started with ``timeout=1700``,
# and every call for the next 28 minutes answered "(kernel busy)".


def _server_is_told_about_abandoned_requests() -> bool:
    """Whether the installed mcp tells the SERVER that a request was abandoned.

    mcp 2.x plans a courtesy ``notifications/cancelled`` into every outbound
    request (``cancel_on_abandon`` in ``mcp.shared.jsonrpc_dispatcher``, a
    module 1.x does not have); 1.x pops the local response stream in
    ``send_request``'s ``finally`` and says nothing on the wire, so a client
    that gives up on a call leaves the server's handler running to completion.

    The kernel-side recovery is identical either way and the tests below cover
    it directly. What this gates is only the end-to-end claim that a cancel
    TRAVELS, which is a library capability and not something crow can supply.
    """
    try:
        from mcp.shared.jsonrpc_dispatcher import (  # noqa: F401
            cancelled_request_id_from_params,
        )
    except ImportError:
        return False
    return True


needs_cancel_on_the_wire = pytest.mark.skipif(
    not _server_is_told_about_abandoned_requests(),
    reason="mcp 1.x sends no notifications/cancelled, so a client-side cancel "
    "never reaches the server handler",
)


def test_interrupt_without_a_kernel_manager_is_a_no_op():
    """``bare_kernel`` builds no ``km``, and neither does a failed start.

    The caller is on a cancel path with nowhere to put an exception: an
    interrupt that cannot be sent has to answer False, not raise.
    """
    assert bare_kernel(FakeClient([])).interrupt() is False


def _wait_until_busy(kernel) -> None:
    """Block until a cell started elsewhere owns the kernel."""
    for _ in range(200):
        if kernel._lock.acquire(blocking=False):
            kernel._lock.release()
            time.sleep(0.05)
        else:
            return
    pytest.fail("the cell never took the kernel")


def test_abandoning_a_cell_gets_the_kernel_back(real_kernel):
    """A cancel is not a timeout, and the kernel is the difference.

    On timeout the caller still wants the cell — it keeps running and its output
    stays collectable, which is the whole ``_inflight`` contract. On cancel the
    caller has given up on it and wants the KERNEL back, but the abandoned
    thread polls to its deadline holding ``_lock``. ``timeout=None`` is the
    shape the incident actually had, and the deadline it never reaches.
    """
    finished = threading.Event()

    def long_cell():
        real_kernel.execute("import time; time.sleep(120)", timeout=None)
        finished.set()

    threading.Thread(target=long_cell, daemon=True).start()
    _wait_until_busy(real_kernel)

    started = time.monotonic()
    real_kernel.abandon()
    assert finished.wait(30), "the abandoned cell never ended"
    elapsed = time.monotonic() - started
    assert elapsed < ABANDON_S, f"the kernel took {elapsed:.0f}s to come back"

    # Free AND usable, which is the only thing the next call cares about.
    assert real_kernel.execute("print('alive')", timeout=30).text.strip() == "alive"


def test_a_late_abandon_does_not_kill_the_next_cell(real_kernel):
    """The cancel can arrive after the worker already returned.

    ``to_thread`` hands back a cancelled future the moment the caller goes
    away, and the thread it started may have finished a millisecond earlier. A
    flag left set would then be picked up by the next cell — one nobody
    abandoned — and interrupt it.
    """
    assert real_kernel.execute("print('one')", timeout=30).text.strip() == "one"
    real_kernel.abandon()  # nothing running
    assert real_kernel.execute("print('two')", timeout=30).text.strip() == "two"


def test_an_abandoned_cell_is_signalled_again_until_it_ends(monkeypatch):
    """One SIGINT is not enough, because the first one can be swallowed.

    A signal that lands before the kernel picks the cell up reaches an idle
    kernel and does nothing, and the thread doing the abandoning cannot tell
    that apart from "still working". So it re-sends on an interval, and gives up
    on a bound rather than holding the lock forever.
    """
    monkeypatch.setattr(kernel_mod, "ABANDON_S", 0.6)
    monkeypatch.setattr(kernel_mod, "ABANDON_RETRY_S", 0.2)
    kernel = bare_kernel(FakeClient([]))  # nothing ever arrives: the cell never ends
    sent = []
    monkeypatch.setattr(kernel, "interrupt", lambda: sent.append(1) or True)
    threading.Timer(0.1, kernel.abandon).start()

    result = kernel.execute("import time; time.sleep(99)", timeout=60)

    assert result.status == "busy"
    assert len(sent) >= 2, "a swallowed SIGINT was never re-sent"
    assert not kernel._abandon.is_set(), "the flag outlived the cell it was for"


def test_collecting_an_abandoned_cell_does_not_interrupt_it_again(monkeypatch):
    """``execute("")`` is the documented way to collect a cell still running.

    An abandon that stayed latched would turn that into a second SIGINT, killing
    the very cell the caller came back for.
    """
    monkeypatch.setattr(kernel_mod, "ABANDON_S", 0.3)
    monkeypatch.setattr(kernel_mod, "ABANDON_RETRY_S", 0.1)
    # No shell reply yet, so the cell is still running when it is abandoned;
    # the reply is added below, in time for the collection only.
    client = FakeClient([_stream("later "), _idle()], shell=[])
    kernel = bare_kernel(client)
    sent = []
    monkeypatch.setattr(kernel, "interrupt", lambda: sent.append(1) or True)
    threading.Timer(0.05, kernel.abandon).start()

    assert kernel.execute("import time; time.sleep(99)", timeout=5).status == "busy"
    assert sent, "the abandoned cell was never interrupted"

    sent.clear()
    client._shell.append(_reply())
    assert kernel.execute("", timeout=5).text == "later "
    assert sent == [], "collecting the cell interrupted it"


@pytest.mark.asyncio
async def test_run_cell_abandons_the_cell_when_its_caller_goes_away():
    """``to_thread`` cannot cancel its thread, so this is the only hook there is.

    A cancelled call raises out of the await and leaves the worker polling to
    its deadline. The abandon flag is what the worker reads to stop.
    """
    released = threading.Event()
    calls = []

    class FakeKernel:
        def execute(self, code, timeout, on_output=None):
            released.wait(30)
            return "late"

        def abandon(self):
            calls.append("abandon")
            released.set()  # the real worker ends the cell; this ends the fake

    task = asyncio.create_task(execute_main._run_cell(FakeKernel(), "sleep", None))
    await asyncio.sleep(0.3)  # let the worker get into execute()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls == ["abandon"]


@needs_cancel_on_the_wire
@pytest.mark.asyncio
async def test_a_cancel_over_the_wire_leaves_the_kernel_usable():
    """The incident, end to end, minus the part the lock already fixed.

    The client gives up on a ``timeout=None`` cell. What the session must NOT
    see is what it did see: a kernel that answers "(kernel busy)" for the rest
    of the abandoned cell's life, and — once that wedged the server far enough
    to kill it — a bare "Connection closed" on every call after, forever.
    """
    from fastmcp import Client

    from crow_cli.mcp2.server import mcp

    sid = "cancel-over-the-wire"
    async with Client(mcp) as client:

        async def call(code, **args):
            result = await client.call_tool(
                "execute", {"code": code, **args}, meta={"session_id": sid}
            )
            return json.loads(result.content[0].text)

        abandoned = asyncio.create_task(
            client.call_tool(
                "execute",
                {"code": "import time; time.sleep(120)", "timeout": None},
                meta={"session_id": sid},
            )
        )
        await asyncio.sleep(4)  # let the cell take the kernel
        abandoned.cancel()
        with pytest.raises(asyncio.CancelledError):
            await abandoned

        # Polled rather than asserted once: the cancel notification, the SIGINT
        # and the abandoned worker releasing the lock are three asynchronous
        # events, and the claim under test is that they settle in seconds — not
        # that they settle before the very next call. Without the interrupt the
        # loop runs out its deadline, because the cell sleeps for 120.
        deadline = time.monotonic() + 45
        while True:
            after = await call("print('alive')", timeout=30)
            if after["exit_code"] == 0:
                break
            assert "busy" in after["output"], after["output"]
            assert time.monotonic() < deadline, "the kernel never came back"
            await asyncio.sleep(0.5)
        assert "alive" in after["output"]


# -- the caller's reset signal -----------------------------------------------


@pytest.mark.asyncio
async def test_a_meta_reset_replaces_the_kernel_and_keeps_the_client():
    """``_meta.reset_kernel`` is the caller's lever; ``reset=True`` is the model's.

    The distinction is the whole point. A client watching a session wedge cannot
    ask the model to reset — the model is inside the wedged turn — and rebuilding
    the MCP client to get a fresh interpreter respawns a subprocess and re-lists
    the tools for nothing. This resets the kernel and leaves everything else up.
    """
    from fastmcp import Client

    from crow_cli.mcp2.server import mcp

    sid = "meta-reset"
    async with Client(mcp) as client:

        async def call(code, **meta):
            result = await client.call_tool(
                "execute", {"code": code}, meta={"session_id": sid, **meta}
            )
            return json.loads(result.content[0].text)

        assert (await call("x = 1"))["exit_code"] == 0
        before = execute_main._kernels[sid]

        reset = await call("", reset_kernel=True)
        assert reset["exit_code"] == 0
        assert "reset" in reset["output"].lower()
        # Popped, not restarted in place: an empty reset cell builds no kernel,
        # so the next real cell starts the fresh one.
        assert execute_main._kernels.get(sid) is not before

        # The SAME client, on the SAME connection, still works — that is what
        # separates this from reconnecting.
        lost = await call("print(x)")
        assert lost["exit_code"] == 1 and "NameError" in lost["output"]
        assert (await call("print('still here')"))["output"].strip() == "still here"


@pytest.mark.asyncio
async def test_the_models_schema_carries_no_reset_signal():
    """The signal is the agent's, so the model can neither see nor forge it.

    ``_meta`` is filtered out of the LLM-facing schema along with ``ctx``; a
    ``reset_kernel`` argument would hand the model a way to wipe its own REPL
    from inside a cell, and a client's reset would stop being distinguishable
    from one the model talked itself into.
    """
    from fastmcp import Client

    from crow_cli.mcp2.server import mcp

    async with Client(mcp) as client:
        [tool] = [t for t in await client.list_tools() if t.name == "execute"]
    assert set(tool.inputSchema.get("properties", {})) == {
        "code", "reset", "timeout", "prelude_path", "python_path",
    }
