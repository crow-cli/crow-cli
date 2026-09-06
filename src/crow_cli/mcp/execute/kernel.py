"""A persistent IPython kernel driven over ZMQ via jupyter_client.

Adapted from the jupyter-kernel-tool gist. The kernel is a subprocess
launched with crow-cli's own interpreter (``sys.executable``), so executed
code runs with crow's dependencies available and can interrogate crow.db.
State persists across :meth:`CrowKernel.execute` calls — this is a REPL,
not a fresh subprocess per call.

Unlike the terminal tool, there is no ``!`` shell escape: bash belongs to
``terminal``. This tool runs Python only.
"""

import queue
import re
import time
from logging import getLogger

from jupyter_client import KernelManager

logger = getLogger(__name__)

# Strip ANSI color codes from tracebacks so the agent reads clean text.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class CrowKernel:
    """A small wrapper around jupyter_client for crow's ``execute`` tool."""

    def __init__(self, python_path: str | None = None, cwd: str | None = None):
        self.km = KernelManager()

        # Point the kernel at crow-cli's own interpreter so the REPL has
        # crow's deps (sqlalchemy/httpx/rich/yaml) and can read crow.db.
        if python_path:
            self.km.kernel_spec.argv[0] = python_path

        if cwd:
            self.km.start_kernel(cwd=cwd)
        else:
            self.km.start_kernel()

        self.client = self.km.client()
        self.client.start_channels()
        self._wait_ready()

    def _wait_ready(self) -> None:
        """Block until the kernel is ready to execute.

        ``wait_for_ready`` is the correct signal, but in some environments it
        can hang (the gist's note); bound it and fall back to a short sleep so
        startup is never unbounded.
        """
        try:
            self.client.wait_for_ready(timeout=15)
        except Exception:
            logger.warning("kernel wait_for_ready timed out; sleeping to settle")
            time.sleep(2)

    def execute(self, code: str, timeout: float | None = 30) -> str:
        """Execute Python code and return what the cell PRINTED.

        stdout + stderr, or the ANSI-stripped traceback on error. The
        REPL's display of the last expression (execute_result / Out[n])
        is drained off iopub and DISCARDED: it is a notebook affordance,
        not program output, and the LLM's view of execute is the program's
        output — plus image blocks the server prepends when vision ran.
        Code talks to the model with print(); values talk to later code by
        being values.

        ``timeout`` bounds the wait for THIS cell (seconds); ``None`` waits
        forever, for a long-running process the caller is deliberately
        blocking on. On timeout the cell is NOT killed — IPython keeps
        running it — so this returns a "kernel busy" notice rather than
        raising, and the cell's output stays collectable on a later call.

        Every message is filtered on ``parent_header.msg_id == msg_id`` for
        this cell. A previous cell that timed out and kept running leaves its
        own shell reply and iopub messages queued; without the filter the
        drain consumes those STALE messages and breaks on the stale idle,
        returning the previous cell's output and desyncing attribution by one
        until a reset. With it, stale messages are discarded and the stream
        re-syncs on its own once the busy cell finishes.
        """
        msg_id = self.client.execute(code)

        reply = self._await_shell_reply(msg_id, timeout)
        if reply is None:
            return self._busy(timeout)

        stdout: list[str] = []
        stderr: list[str] = []
        error = None

        # The cell is done (we hold its execute_reply), so its iopub messages
        # are already buffered — drain them, skipping any stale ones, and stop
        # at THIS cell's idle.
        while True:
            try:
                msg = self.client.get_iopub_msg(timeout=timeout)
            except queue.Empty:
                break
            if msg.get("parent_header", {}).get("msg_id") != msg_id:
                continue

            msg_type = msg["msg_type"]
            content = msg["content"]
            if msg_type == "stream":
                if content["name"] == "stdout":
                    stdout.append(content["text"])
                else:
                    stderr.append(content["text"])
            elif msg_type == "error":
                error = content
            elif msg_type == "status" and content["execution_state"] == "idle":
                break

        return self._format_output(
            stdout="".join(stdout),
            stderr="".join(stderr),
            error=error,
        )

    def _await_shell_reply(self, msg_id: str, timeout: float | None):
        """This cell's execute_reply, or None on timeout.

        Skips stale replies left by a previous cell that timed out and kept
        running, so the wait is bounded by ``timeout`` overall rather than
        restarting it per discarded message. ``timeout=None`` blocks until the
        cell finishes.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                return None
            try:
                reply = self.client.get_shell_msg(timeout=remaining)
            except queue.Empty:
                return None
            if reply.get("parent_header", {}).get("msg_id") == msg_id:
                return reply
            # A previous cell's reply — discard and keep waiting for ours.

    @staticmethod
    def _busy(timeout: float | None) -> str:
        """The honest signal for a cell still running past its timeout.

        Replaces the bare ``Error:`` an unhandled ``queue.Empty`` used to
        surface as (its ``str()`` is empty), which read as "broken" and sent
        the caller to reset a kernel that was merely busy.
        """
        return (
            f"(kernel busy: the cell did not finish within {timeout}s and is"
            " still running — its output was not captured this call. Re-call"
            " execute to collect it once it completes, and pass a longer"
            " timeout= — or timeout=None to wait — for a long-running cell.)"
        )

    def _format_output(
        self,
        stdout: str,
        stderr: str,
        error: dict | None,
    ) -> str:
        """The program's output, nothing else."""
        # Error first — that's what matters when it breaks.
        if error:
            traceback_lines = [
                _ANSI_RE.sub("", line) for line in error.get("traceback", [])
            ]
            return "\n".join(traceback_lines)

        output = []
        if stdout:
            output.append(stdout.rstrip())
        if stderr:
            output.append(stderr.rstrip())
        return "\n".join(output)

    def shutdown(self) -> None:
        """Shut down the kernel subprocess and tear down the ZMQ channels."""
        try:
            self.client.stop_channels()
        except Exception:
            pass
        try:
            self.km.shutdown_kernel(now=True)
        except Exception:
            logger.warning("kernel shutdown raised", exc_info=True)
