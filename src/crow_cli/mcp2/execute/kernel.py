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
import threading
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

#: A frame jupyter_client cannot parse. ``feed_identities`` raises ValueError
#: when the DELIM is missing, and that is a property of the BYTES, not of the
#: kernel: dropping the frame and reading on is the whole recovery.
_GARBAGE = (ValueError, KeyError)

#: How long an abandoned cell gets to die in, and how often SIGINT is re-sent
#: while it does not. Re-sent rather than sent once because a signal that lands
#: before the kernel picks the cell up is swallowed by an idle kernel, and the
#: thread doing the abandoning cannot tell that apart from "still working".
#: Ten seconds is far past a KeyboardInterrupt and far short of the deadline it
#: replaces, which for a ``timeout=None`` cell does not exist.
ABANDON_S = 10.0
ABANDON_RETRY_S = 0.5

#: What the caller is told when it asks a kernel to run a cell while another
#: cell still holds it. Two threads on one ZMQ socket is what killed the
#: server (libzmq aborts with "Bad address"); a refusal is the fix.
OCCUPIED = (
    "(kernel busy: an earlier cell is still running in this kernel. Re-call"
    " execute with empty code to collect its output when it finishes, or pass"
    " reset=True to abandon it and start a fresh kernel.)"
)


class KernelDead(Exception):
    """The kernel's channels are unusable. The caller builds a new one."""


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


@dataclass
class _Inflight:
    """The cell the kernel is running, and every byte it has written so far.

    Held on the kernel rather than on the stack of whichever call started it:
    a call that times out returns, the cell does not, and the next call has to
    be able to pick the output up where this one left off.
    """

    msg_id: str
    raw: bytearray = field(default_factory=bytearray)
    error: Optional[dict] = None
    got_reply: bool = False
    saw_idle: bool = False


class CrowKernel:
    """A small wrapper around jupyter_client for crow's ``execute`` tool.

    One cell at a time, enforced by a lock. That is not tidiness: the previous
    version let a timed-out cell's thread keep polling while the next call
    started polling too, and two readers on one ZMQ socket make libzmq abort
    the whole process ("Bad address", src/fq.cpp). The server died, the kernel
    saw its parent exit, and every later call — including reset — failed with
    "Connection closed".
    """

    def __init__(self, python_path: Optional[str] = None, cwd: Optional[str] = None):
        #: Serializes channel access. Reset deliberately never waits on it for
        #: long: a wedged cell must be abandonable.
        self._lock = threading.Lock()
        #: Set by :meth:`shutdown`; the poll loop returns at the next tick
        #: instead of waiting for a cell that is never coming back.
        self._cancelled = threading.Event()
        #: Set by :meth:`abandon`; the poll loop interrupts the cell it is
        #: draining and stops waiting for it. Distinct from ``_cancelled``
        #: because it means something different: shutdown is the kernel going
        #: away, abandon is one cell being given up on.
        self._abandon = threading.Event()
        self._inflight: Optional[_Inflight] = None
        #: Set when a channel raised something that is not a parse failure.
        self.dead = False

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
        except _GARBAGE as exc:
            # Same junk-frame case as the poll loop: the kernel may well be
            # fine. Settle and go.
            logger.warning("kernel readiness saw an unparseable frame: %s", exc)
            time.sleep(2)
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
        if self.dead:
            raise KernelDead("the kernel's channels are gone")
        if not self._lock.acquire(timeout=2 * POLL_S):
            # Somebody else's cell owns the socket. Refusing is the point —
            # two readers on one socket is what aborted the process.
            return self._notice(OCCUPIED, timeout)

        try:
            return self._execute_locked(code, timeout, on_output)
        except KernelDead:
            self.dead = True
            raise
        finally:
            self._lock.release()

    def _execute_locked(
        self,
        code: str,
        timeout: Optional[float],
        on_output: Optional[OutputSink],
    ) -> CellResult:
        cell = self._inflight
        if cell is None:
            # A late :meth:`abandon` was for the cell that just finished, not
            # for this one. Cleared here rather than there because only starting
            # a cell makes "nothing is running" true again — and an attach to an
            # existing ``_inflight`` must NOT clear it, or collecting an
            # abandoned cell's output would un-abandon it.
            self._abandon.clear()
            cell = self._inflight = _Inflight(msg_id=self.client.execute(code))
        elif code.strip():
            # A real cell is still running; there is nowhere to put another.
            return self._notice(OCCUPIED, timeout)

        result, done = self._drain(cell, timeout, on_output)
        if done:
            self._inflight = None
        return result

    def _drain(
        self,
        cell: _Inflight,
        timeout: Optional[float],
        on_output: Optional[OutputSink],
    ) -> tuple[CellResult, bool]:
        """Poll both channels until the cell is done, the deadline passes, or
        this kernel is abandoned. Returns the result and whether it is final."""
        deadline = None if timeout is None else time.monotonic() + timeout
        streamed = False
        #: Latched from ``_abandon`` on first sight, and from then on it is the
        #: reason to stop waiting rather than ``deadline`` — which for a
        #: ``timeout=None`` cell does not exist, and that is the case a cancel
        #: has to rescue.
        give_up_at: Optional[float] = None
        next_signal = 0.0

        def take(chunk: bytes) -> None:
            nonlocal streamed
            cell.raw.extend(chunk)
            if on_output is not None and chunk:
                streamed = True
                on_output(bytes(chunk))

        while True:
            if self._cancelled.is_set():
                return self._snapshot(cell, streamed, timeout), False

            if self._abandon.is_set():
                # Cleared on sight so a later attach to this same ``_inflight``
                # (``execute("")``, the documented way to collect an abandoned
                # cell) drains it instead of interrupting it all over again.
                self._abandon.clear()
                give_up_at = time.monotonic() + ABANDON_S
                next_signal = 0.0
                logger.info("cell abandoned by its caller — interrupting the kernel")

            now = time.monotonic()
            if give_up_at is not None:
                if now >= give_up_at:
                    logger.warning(
                        "an interrupted cell did not end within %.0fs — giving up "
                        "on it; the kernel stays busy until it does",
                        ABANDON_S,
                    )
                    return self._snapshot(cell, streamed, timeout), False
                if now >= next_signal:
                    if not self.interrupt():
                        # Nothing to signal with. Waiting out the window would
                        # change nothing, so stop now and let the caller see the
                        # cell is still running.
                        give_up_at = now
                    next_signal = now + ABANDON_RETRY_S
            elif deadline is not None and now >= deadline:
                return self._snapshot(cell, streamed, timeout), False

            remaining = None if deadline is None else deadline - time.monotonic()
            wait = POLL_S if remaining is None else min(POLL_S, max(remaining, 0.0))

            # iopub first: this is the channel the user is waiting on.
            try:
                msg = self.client.get_iopub_msg(timeout=wait)
            except queue.Empty:
                msg = None
            except _GARBAGE as exc:
                # A frame that is not a Jupyter message. The bytes are junk,
                # the socket is not: log it and read the next frame.
                logger.warning("dropped an unparseable iopub frame: %s", exc)
                msg = None
            except Exception as exc:
                raise KernelDead(f"iopub read failed: {exc}") from exc

            if msg is not None and msg.get("parent_header", {}).get("msg_id") == cell.msg_id:
                msg_type = msg["msg_type"]
                content = msg["content"]
                if msg_type == "stream":
                    take(content["text"].encode("utf-8", "replace"))
                elif msg_type == "error":
                    cell.error = content
                    take(("\n".join(content.get("traceback", [])) + "\n").encode("utf-8", "replace"))
                elif msg_type == "status" and content["execution_state"] == "idle":
                    cell.saw_idle = True
                # execute_result / display_data: drained and DISCARDED. The
                # REPL's Out[n] is a notebook affordance, not program output;
                # code talks to the model with print().

            # Then the shell reply, non-blocking — a stale one from a previous
            # timed-out cell is discarded, not mistaken for ours.
            if not cell.got_reply:
                try:
                    reply = self.client.get_shell_msg(timeout=0)
                except queue.Empty:
                    reply = None
                except _GARBAGE as exc:
                    logger.warning("dropped an unparseable shell frame: %s", exc)
                    reply = None
                except Exception as exc:
                    raise KernelDead(f"shell read failed: {exc}") from exc
                if reply is not None and reply.get("parent_header", {}).get("msg_id") == cell.msg_id:
                    cell.got_reply = True

            if cell.got_reply and cell.saw_idle:
                return (
                    CellResult(
                        raw=cap_raw(bytes(cell.raw)),
                        text=cap_text(strip_ansi(bytes(cell.raw))),
                        status="error" if cell.error else "ok",
                        exit_code=1 if cell.error else 0,
                        streamed=streamed,
                    ),
                    True,
                )

    def _snapshot(
        self, cell: _Inflight, streamed: bool, timeout: Optional[float]
    ) -> CellResult:
        """What has arrived so far, for a cell we stopped waiting on."""
        result = self._busy(bytearray(cell.raw), timeout, None)
        result.streamed = streamed
        return result

    def _notice(self, notice: str, timeout: Optional[float]) -> CellResult:
        return CellResult(
            text=notice, status="busy", exit_code=None, busy_notice=notice
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

    def abandon(self) -> None:
        """Give up on the running cell and get the kernel back. Non-blocking.

        What a cancel means, as against a timeout. On timeout the caller still
        wants the cell: it keeps running, ``_inflight`` keeps its output, and a
        later ``execute("")`` collects it. On cancel the caller is gone and the
        cell is worth nothing — but the KERNEL is not, and the kernel is behind
        ``_lock``, which the abandoned thread holds until its deadline. With
        ``timeout=None``, the documented way to block on a long cell, that
        deadline does not exist, so every later call answers :data:`OCCUPIED`
        forever. That is the incident this exists for: a cancel on a cell
        started with ``timeout=1700`` wedged the session for 28 minutes, and
        then — via the two readers the wedge provoked — killed the server.

        A flag rather than a direct :meth:`interrupt`, for two reasons. The
        caller is on an ``except CancelledError`` path, where the surrounding
        cancel scope re-delivers cancellation to anything that checkpoints, so
        it cannot await; and only the thread already inside :meth:`_drain` knows
        whether there is a cell to interrupt yet — a SIGINT that lands before
        the kernel picks the cell up is swallowed by an idle kernel. Setting an
        event is neither problem, and the thread that owns the socket does the
        signalling, which keeps the one-reader-per-socket invariant the lock
        exists to protect.

        Safe with nothing running: the flag is cleared when the next cell
        starts, so a cancel that arrives late cannot kill a cell nobody
        abandoned.
        """
        self._abandon.set()

    def interrupt(self) -> bool:
        """SIGINT the kernel process. Best effort: never raises, returns success.

        IPython turns it into a ``KeyboardInterrupt`` in the running cell, the
        cell ends, the shell reply and idle status arrive, ``_drain`` returns
        and the lock is free — about a second instead of the cell's deadline.
        Called by :meth:`_drain` on behalf of :meth:`abandon`, which re-sends it
        while the cell does not end; public because a caller that knows a cell
        is running should not have to go through the flag to say so.

        ``km`` is read through ``getattr`` because tests build a kernel around
        a fake client with no manager, and an interrupt that cannot be sent is
        a no-op, not an AttributeError.
        """
        km = getattr(self, "km", None)
        if km is None:
            return False
        try:
            km.interrupt_kernel()
        except Exception:
            logger.warning("kernel interrupt failed", exc_info=True)
            return False
        logger.info("interrupted the kernel")
        return True

    def shutdown(self) -> None:
        """Shut the kernel down. Never blocks, and never needs a live channel.

        Reset is the one thing that has to work when everything else does not,
        so this refuses to wait on a cell: the cancelled flag ends the poll
        loop, and the teardown itself runs off-thread when the lock is held.
        Closing sockets underneath a thread blocked reading them is precisely
        the libzmq abort that started this, so ``stop_channels`` only runs when
        the lock says no reader is inside.
        """
        self._cancelled.set()
        self.dead = True
        if self._lock.acquire(blocking=False):
            try:
                self._teardown(stop_channels=True)
            finally:
                self._lock.release()
            return
        threading.Thread(target=self._teardown, args=(False,), daemon=True).start()

    def _teardown(self, stop_channels: bool) -> None:
        if stop_channels:
            try:
                self.client.stop_channels()
            except Exception:
                logger.warning("stop_channels raised", exc_info=True)
        try:
            self.km.shutdown_kernel(now=True)
        except Exception:
            logger.warning("kernel shutdown raised", exc_info=True)
