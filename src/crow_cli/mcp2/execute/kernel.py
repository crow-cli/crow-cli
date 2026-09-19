"""A persistent IPython kernel that streams, and keeps output twice.

Ported from ``mcp/execute/kernel.py`` with one change of substance and it is
the reason this file exists separately. v1's :meth:`CrowKernel.execute`
awaited the shell reply and *then* drained iopub into two lists, so output
was only ever available all-at-once, at the end, as a single string. ACP v2
wants a terminal: bytes on the wire as they happen, for a human to watch.

So this version interleaves the two channels and reports each iopub stream
message to a callback the moment it arrives. And it returns
:class:`CellResult` — the same output in two forms, because it has two
audiences:

``raw``
    Every byte the cell wrote, ANSI intact, in arrival order. Base64 this and
    it is ``TerminalUpdate.output`` / ``TerminalOutputChunk`` — the client
    renders it, or passes it straight through to a real terminal.

``text``
    The same bytes with ANSI stripped. This is ``ToolCallUpdate.raw_output``,
    what the model reads. Color and cursor movement are signal for a human and
    noise for a model; sending either audience the other's copy is how you get
    a grey wall of ``\\x1b[0;32m`` in the context window.

Both are capped, independently, because they are billed differently: ``text``
costs context window, ``raw`` costs bandwidth.

Everything hard-won in v1 ports unchanged — the ``parent_header.msg_id``
filter (without it a previous cell that timed out and kept running desyncs
attribution by one, forever), the "kernel busy" notice instead of a bare
``Error:`` from an empty ``queue.Empty``, and discarding ``execute_result``
(the REPL's ``Out[n]`` is a notebook affordance, not program output).
"""

from __future__ import annotations

import queue
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from logging import getLogger
from typing import Optional

from jupyter_client import KernelManager

logger = getLogger(__name__)

#: Full CSI sequences, not just SGR. IPython emits color; a cell can emit
#: cursor movement, and the client has already seen those bytes live — the
#: model must not.
ANSI_RE = re.compile(rb"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")

#: How long to block on either channel before checking the other, and the
#: deadline. Small enough to feel live, large enough to not spin.
POLL_S = 0.05

#: ~5k tokens of context — the same discipline as v1 and as terminal's
#: MAX_CMD_OUTPUT_SIZE.
MAX_TEXT_CHARS = 20_000
_TAIL_CHARS = 4_000

#: Raw bytes are not context, so the cap is about not shipping a megabyte of
#: scrollback in one notification. Generous, and head+tail like the text.
MAX_RAW_BYTES = 256_000
_RAW_TAIL_BYTES = 32_000

#: Called from the kernel thread with each chunk as it arrives.
OutputSink = Callable[[bytes], None]


def strip_ansi(raw: bytes) -> str:
    """ANSI-stripped, newline-normalized text — the model's copy."""
    return (
        ANSI_RE.sub(b"", raw)
        .decode("utf-8", "replace")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )


def cap_text(text: str) -> str:
    """Head+tail truncation so one runaway cell cannot eat the context."""
    if len(text) <= MAX_TEXT_CHARS:
        return text
    head = MAX_TEXT_CHARS - _TAIL_CHARS
    elided = len(text) - head - _TAIL_CHARS
    return f"{text[:head]}\n... [{elided} chars elided] ...\n{text[-_TAIL_CHARS:]}"


def cap_raw(raw: bytes) -> bytes:
    """The same, for the client's copy. Split on a byte boundary, not a char."""
    if len(raw) <= MAX_RAW_BYTES:
        return raw
    head = MAX_RAW_BYTES - _RAW_TAIL_BYTES
    return raw[:head] + f"\n... [{len(raw) - head - _RAW_TAIL_BYTES} bytes elided] ...\n".encode() + raw[-_RAW_TAIL_BYTES:]


@dataclass
class CellResult:
    """One cell's output, in both forms, plus how it ended.

    ``exit_code`` mirrors what a terminal would report, because that is what
    the client is rendering: 0 on success, 1 on an error, None when the cell
    is still running and we stopped waiting for it.
    """

    raw: bytes = b""
    text: str = ""
    status: str = "ok"  # ok | error | busy
    exit_code: Optional[int] = 0
    busy_notice: Optional[str] = None
    #: True when at least one chunk went out live through ``on_output``. A
    #: caller that sent no progressToken gets False and the snapshot instead —
    #: a client that already watched the bytes arrive must not be handed the
    #: whole buffer again to render twice.
    streamed: bool = False


class CrowKernel:
    """A small wrapper around jupyter_client for crow's ``execute`` tool."""

    def __init__(self, python_path: Optional[str] = None, cwd: Optional[str] = None):
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
        can hang; bound it and fall back to a short sleep so startup is never
        unbounded.
        """
        try:
            self.client.wait_for_ready(timeout=15)
        except Exception:
            logger.warning("kernel wait_for_ready timed out; sleeping to settle")
            time.sleep(2)

    def execute(
        self,
        code: str,
        timeout: Optional[float] = 30.0,
        on_output: Optional[OutputSink] = None,
    ) -> CellResult:
        """Run one cell, streaming its output, and return it in both forms.

        ``on_output`` is called from THIS thread with each chunk as it arrives
        — an async caller marshals it onto its own loop. ``timeout`` bounds the
        wait for this cell; ``None`` waits forever, for a long-running process
        the caller is deliberately blocking on. On timeout the cell is NOT
        killed (IPython keeps running it) so the result is ``status="busy"``
        rather than an exception, and the output stays collectable later.
        """
        msg_id = self.client.execute(code)
        deadline = None if timeout is None else time.monotonic() + timeout

        raw = bytearray()
        error: Optional[dict] = None
        got_reply = False
        saw_idle = False

        streamed = False

        def take(chunk: bytes) -> None:
            nonlocal streamed
            raw.extend(chunk)
            if on_output is not None and chunk:
                streamed = True
                on_output(bytes(chunk))

        while True:
            if deadline is not None and time.monotonic() >= deadline:
                return self._busy(raw, timeout, on_output)

            remaining = None if deadline is None else deadline - time.monotonic()
            wait = POLL_S if remaining is None else min(POLL_S, max(remaining, 0.0))

            # iopub first: this is the channel the user is waiting on.
            try:
                msg = self.client.get_iopub_msg(timeout=wait)
            except queue.Empty:
                msg = None
            if msg is not None and msg.get("parent_header", {}).get("msg_id") == msg_id:
                msg_type = msg["msg_type"]
                content = msg["content"]
                if msg_type == "stream":
                    take(content["text"].encode("utf-8", "replace"))
                elif msg_type == "error":
                    error = content
                    take(("\n".join(content.get("traceback", [])) + "\n").encode("utf-8", "replace"))
                elif msg_type == "status" and content["execution_state"] == "idle":
                    saw_idle = True
                # execute_result / display_data: drained and DISCARDED. The
                # REPL's Out[n] is a notebook affordance, not program output;
                # code talks to the model with print().

            # Then the shell reply, non-blocking — a stale one from a previous
            # timed-out cell is discarded, not mistaken for ours.
            if not got_reply:
                try:
                    reply = self.client.get_shell_msg(timeout=0)
                except queue.Empty:
                    reply = None
                if reply is not None and reply.get("parent_header", {}).get("msg_id") == msg_id:
                    got_reply = True

            if got_reply and saw_idle:
                break

        return CellResult(
            raw=cap_raw(bytes(raw)),
            text=cap_text(strip_ansi(bytes(raw))),
            status="error" if error else "ok",
            exit_code=1 if error else 0,
            streamed=streamed,
        )

    def _busy(
        self,
        partial: bytearray,
        timeout: Optional[float],
        on_output: Optional[OutputSink],
    ) -> CellResult:
        """The honest signal for a cell still running past its timeout.

        Replaces the bare ``Error:`` an unhandled ``queue.Empty`` used to
        surface as (its ``str()`` is empty), which read as "broken" and sent
        the caller to reset a kernel that was merely busy.
        """
        notice = (
            f"(kernel busy: the cell did not finish within {timeout}s and is"
            " still running — its output was not captured this call. Re-call"
            " execute to collect it once it completes, and pass a longer"
            " timeout= — or timeout=None to wait — for a long-running cell.)"
        )
        return CellResult(
            raw=cap_raw(bytes(partial)),
            text=notice,
            status="busy",
            exit_code=None,
            busy_notice=notice,
            streamed=on_output is not None and bool(partial),
        )

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
