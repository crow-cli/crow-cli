"""Headless PTY terminal for the agent's ``terminal`` tool.

This is the ACP terminal tool contract's code path
(create / output / kill / wait / release). It is deliberately separated
from the human-facing terminal emulator (:mod:`crow_cli.tui.widgets.terminal_tool`
+ :mod:`crow_cli.tui.ansi`): no Textual widget, no ANSI state, no folds,
no UI-derived sizing — just a PTY, raw byte capture, and process
lifecycle. Tuning the emulator for fullscreen TUIs (helix) cannot
regress the agent tool, and vice versa.

The conversation may attach *display* listeners which mirror the output
into a widget for human eyes; display failures never affect capture.
"""

from __future__ import annotations

import asyncio
from asyncio.subprocess import Process
import codecs
from contextlib import suppress
import fcntl
import logging
import os
import pty
import shlex
import signal
import struct
import termios
from collections import deque
from typing import Awaitable, Callable, Mapping

from crow_cli.tui.shell_read import shell_read
from crow_cli.tui.widgets.terminal_tool import Command, ToolState

logger = logging.getLogger(__name__)

OutputListener = Callable[[str], Awaitable[None]]
ExitListener = Callable[[int | None], Awaitable[None]]


class AgentTerminal:
    """A headless PTY command runner with raw-byte output capture.

    Args:
        command: The command to run.
        output_byte_limit: Maximum bytes of output to retain, or `None`
            for no limit.
    """

    def __init__(
        self, command: Command, *, output_byte_limit: int | None = None
    ) -> None:
        self._command = command
        self._output_byte_limit = output_byte_limit
        self._process: Process | None = None
        self._task: asyncio.Task | None = None
        self._fd: int | None = None
        self._return_code: int | None = None
        self._released: bool = False
        self._exit_event = asyncio.Event()
        self._ready_event = asyncio.Event()
        self._spawn_error: Exception | None = None
        self._output: deque[bytes] = deque()
        self._output_bytes_count = 0
        self._bytes_read = 0
        self._output_listeners: list[OutputListener] = []
        self._exit_listeners: list[ExitListener] = []

    @property
    def return_code(self) -> int | None:
        """The command return code, or `None` if not yet set."""
        return self._return_code

    @property
    def released(self) -> bool:
        """Has the terminal been released?"""
        return self._released

    @property
    def tool_state(self) -> ToolState:
        """Current state of the terminal (output + exit status)."""
        output, truncated = self.get_output()
        return ToolState(
            output=output, truncated=truncated, return_code=self.return_code
        )

    def add_output_listener(self, listener: OutputListener) -> None:
        """Subscribe to decoded output chunks (display mirror)."""
        self._output_listeners.append(listener)

    def add_exit_listener(self, listener: ExitListener) -> None:
        """Subscribe to process exit (display finalization)."""
        self._exit_listeners.append(listener)

    @staticmethod
    def resize_pty(fd: int, columns: int, rows: int) -> None:
        """Set the PTY window size.

        Args:
            fd: File descriptor.
            columns: Columns (width).
            rows: Rows (height).
        """
        size = struct.pack("HHHH", rows, columns, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, size)

    async def start(self, width: int = 80, height: int = 24) -> None:
        """Spawn the PTY and the command.

        Args:
            width: Initial PTY columns.
            height: Initial PTY rows.

        Raises:
            Exception: If the process failed to spawn.
        """
        self._task = asyncio.create_task(
            self._guarded_run(width, height),
            name=f"AgentTerminal {self._command}",
        )
        await self._ready_event.wait()
        if self._spawn_error is not None:
            raise self._spawn_error

    async def _guarded_run(self, width: int, height: int) -> None:
        try:
            await self._run(width, height)
        except Exception as error:
            self._spawn_error = error
            logger.exception("Agent terminal failed: %s", self._command)
        finally:
            self._ready_event.set()
            for listener in self._exit_listeners:
                try:
                    await listener(self._return_code)
                except Exception:
                    logger.exception("Exit listener failed")
            self._exit_event.set()

    async def _run(self, width: int, height: int) -> None:
        master, slave = pty.openpty()
        self._fd = master

        flags = fcntl.fcntl(master, fcntl.F_GETFL)
        fcntl.fcntl(master, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # Size the PTY before the child is born so programs render at the
        # right dimensions on their first paint.
        self.resize_pty(master, width or 80, height or 24)

        command = self._command
        environment = os.environ | command.env

        if " " in command.command:
            run_command = command.command
        else:
            run_command = f"{command.command} {shlex.join(command.args)}"

        shell = os.environ.get("SHELL", "sh")
        run_command = shlex.join([shell, "-c", run_command])

        def _new_pty_session() -> None:
            # The child must own the PTY as its controlling terminal, or
            # programs that ask /dev/tty for the size get the OUTER
            # terminal's dimensions and never receive SIGWINCH.
            os.setsid()
            fcntl.ioctl(slave, getattr(termios, "TIOCSCTTY", 0x540E))

        process = self._process = await asyncio.create_subprocess_shell(
            run_command,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=environment,
            cwd=command.cwd,
            preexec_fn=_new_pty_session,
        )

        os.close(slave)
        self._ready_event.set()

        BUFFER_SIZE = 64 * 1024 * 2
        reader = asyncio.StreamReader(BUFFER_SIZE)
        protocol = asyncio.StreamReaderProtocol(reader)

        loop = asyncio.get_event_loop()
        transport, _ = await loop.connect_read_pipe(
            lambda: protocol, os.fdopen(master, "rb", 0)
        )

        unicode_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            while True:
                data = await shell_read(reader, BUFFER_SIZE)
                if data:
                    self._record_output(data)
                    if (process_data := unicode_decoder.decode(data)) and (
                        listeners := self._output_listeners
                    ):
                        for listener in listeners:
                            # Display is best-effort: a broken mirror must
                            # never break capture.
                            loop.create_task(
                                self._call_output_listener(listener, process_data)
                            )
                if not data:
                    break
        finally:
            transport.close()

        self._return_code = await process.wait()

    @staticmethod
    async def _call_output_listener(
        listener: OutputListener, text: str
    ) -> None:
        try:
            await listener(text)
        except Exception:
            logger.exception("Output listener failed")

    def _record_output(self, data: bytes) -> None:
        """Keep a record of the output bytes, bounded by the limit."""
        self._output.append(data)
        self._output_bytes_count += len(data)
        self._bytes_read += len(data)

        if self._output_byte_limit is None:
            return

        while self._output_bytes_count > self._output_byte_limit and self._output:
            oldest_bytes = self._output[0]
            oldest_bytes_count = len(oldest_bytes)
            if self._output_bytes_count - oldest_bytes_count < self._output_byte_limit:
                break
            self._output.popleft()
            self._output_bytes_count -= oldest_bytes_count

    def get_output(self) -> tuple[str, bool]:
        """Get the captured output.

        Returns:
            Output text and a bool indicating truncation.
        """
        output_bytes = b"".join(self._output)

        def is_continuation(byte_value: int) -> bool:
            return (byte_value & 0b11000000) == 0b10000000

        truncated = False
        if (
            self._output_byte_limit is not None
            and len(output_bytes) > self._output_byte_limit
        ):
            truncated = True
            output_bytes = output_bytes[-self._output_byte_limit :]
            # Must start on a utf-8 boundary
            for offset, byte_value in enumerate(output_bytes):
                if not is_continuation(byte_value):
                    if offset:
                        output_bytes = output_bytes[offset:]
                    break

        output = output_bytes.decode("utf-8", "replace")
        return output, truncated

    async def wait_for_exit(self) -> tuple[int | None, str | None]:
        """Wait for the process to exit."""
        await self._exit_event.wait()
        return (self.return_code or 0, None)

    def kill(self) -> bool:
        """Kill the process (whole group, so children don't orphan).

        Returns:
            `True` if a process was killed, or `False` if none was running.
        """
        if self.return_code is not None:
            return False
        if self._process is None:
            return False
        pid = self._process.pid
        try:
            pgid = os.getpgid(pid)
        except OSError:
            pgid = None
        try:
            if pgid is not None and pgid == pid:
                os.killpg(pgid, signal.SIGKILL)
            else:
                self._process.kill()
        except OSError:
            try:
                self._process.kill()
            except Exception:
                return False
        return True

    def release(self) -> None:
        """Release the terminal (may no longer be used from ACP)."""
        self._released = True


__all__ = ["AgentTerminal"]
