"""A persistent IPython kernel driven over ZMQ via jupyter_client.

Adapted from the jupyter-kernel-tool gist. The kernel is a subprocess
launched with crow-cli's own interpreter (``sys.executable``), so executed
code runs with crow's dependencies available and can interrogate crow.db.
State persists across :meth:`CrowKernel.execute` calls — this is a REPL,
not a fresh subprocess per call.

Unlike the terminal tool, there is no ``!`` shell escape: bash belongs to
``terminal``. This tool runs Python only.
"""

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

    def execute(self, code: str, timeout: float = 30) -> str:
        """Execute Python code and return what the cell PRINTED.

        stdout + stderr, or the ANSI-stripped traceback on error. The
        REPL's display of the last expression (execute_result / Out[n])
        is drained off iopub and DISCARDED: it is a notebook affordance,
        not program output, and the LLM's view of execute is the program's
        output — plus image blocks the server prepends when vision ran.
        Code talks to the model with print(); values talk to later code by
        being values.
        """
        self.client.execute(code)
        reply = self.client.get_shell_msg(timeout=timeout)

        stdout: list[str] = []
        stderr: list[str] = []
        error = None

        # Drain iopub messages until the kernel reports idle for this cell.
        while True:
            try:
                msg = self.client.get_iopub_msg(timeout=timeout)
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
            except Exception:
                break

        return self._format_output(
            stdout="".join(stdout),
            stderr="".join(stderr),
            error=error,
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
