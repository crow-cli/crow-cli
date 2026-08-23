"""Client-side terminal for the Crow ACP client.

Runs the agent's terminal commands in a real PTY so the behavior matches the
IDE's client-side terminals (lapce/zed) closely enough to be a faithful harness
for prompt-surface-area work:

* commands run in a tty (TERM/COLORTERM set like zed), so tty-sensitive
  programs behave the same as they would under the real client terminals;
* the real exit status is captured via ``waitpid`` — not scraped from a PS1
  marker the way crow-mcp's standalone terminal does (that scraping is what
  mis-reports exit codes);
* output is tail-truncated to ``output_byte_limit`` (mirrors lapce);
* the agent receives lightly ANSI-stripped text — the same "clean text to the
  model" contract the grid-based IDE terminals provide. The IDE parses output
  through an alacritty grid; here we use a small regex strip, which is enough
  for this microscope client (we are not trying to wow anyone here).

Stdlib only (``pty`` + ``os``); no terminal-emulator library, no new deps.
"""

import asyncio
import os
import pty
import re
import signal
import subprocess
import threading
import uuid

# Match zed (terminal.rs): ask the child to emit color so tty-sensitive
# behavior matches the real client terminals. We strip it back out for the
# agent's clean text.
TERM_ENV = {"TERM": "xterm-256color", "COLORTERM": "truecolor"}

# Good-enough ANSI strip for the model (the IDE uses a full grid instead).
# Covers CSI, OSC, other C1 controls, charset selection, and carriage returns
# (so progress-bar overwrites collapse the way a grid would).
_ANSI_RE = re.compile(
    r"""
    \x1b\[[\x30-\x3f]*[\x20-\x2f]*[\x40-\x7e]   # CSI  (e.g. ESC[31m, ESC[?2004h)
    | \x1b\][^\x07\x1b]*(?:\x07|\x1b\\)          # OSC  (title, hyperlinks)
    | \x1b[()*+][0-9A-Za-z]                      # charset selection
    | \x1b[@-Z\\-_]                              # other C1 / Fe controls
    | \r                                         # carriage return
    """,
    re.VERBOSE,
)


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences and carriage returns from terminal text."""
    return _ANSI_RE.sub("", text)


class ClientTerminal:
    """A single command run in a PTY, supervised for its real exit status.

    Lifecycle mirrors the ACP terminal contract: ``start()`` (terminal/create),
    ``wait_exit()`` (terminal/wait_for_exit), ``output()`` (terminal/output),
    ``kill()`` (terminal/kill), ``release()`` (terminal/release).
    """

    def __init__(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        output_byte_limit: int | None = None,
    ):
        self.command = command
        self.cwd = cwd or None
        self.output_byte_limit = output_byte_limit or 0
        self.env = {**os.environ, **TERM_ENV, **(env or {})}

        self._buf = bytearray()  # raw bytes, tail-kept to output_byte_limit
        self.truncated = False
        self.exit_code: int | None = None
        self.signal_name: str | None = None

        self._exit_event = threading.Event()
        self._master_fd: int | None = None
        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Spawn the command in a PTY via subprocess and start the reader.

        ``pty.openpty()`` only creates a pty fd pair (no fork); ``Popen`` does
        the fork+exec in C, which is safe in this multi-threaded process and
        avoids the ``forkpty()`` DeprecationWarning / deadlock hazard. The slave
        pty is the child's stdio, so programs see a real tty (isatty() is True)
        and behave as they would under the IDE's client terminals.
        """
        master, slave = pty.openpty()
        try:
            self._proc = subprocess.Popen(
                ["bash", "-c", self.command],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=self.cwd,
                env=self.env,
                start_new_session=True,
            )
        finally:
            # The child keeps its own reference to the slave; the parent only
            # needs the master side to read output.
            os.close(slave)
        self._master_fd = master
        self._reader = threading.Thread(
            target=self._read_loop,
            name=f"client-term-{self._proc.pid}",
            daemon=True,
        )
        self._reader.start()

    def _read_loop(self) -> None:
        """Drain the PTY until EOF, then reap the child and signal exit."""
        try:
            while True:
                try:
                    chunk = os.read(self._master_fd, 65536)
                except OSError:
                    break  # EIO: child closed the tty
                if not chunk:
                    break
                self._append(chunk)
        finally:
            self._reap()
            if self._master_fd is not None:
                try:
                    os.close(self._master_fd)
                except OSError:
                    pass
                self._master_fd = None
            self._exit_event.set()

    def _append(self, chunk: bytes) -> None:
        with self._lock:
            self._buf.extend(chunk)
            if self.output_byte_limit and len(self._buf) > self.output_byte_limit:
                excess = len(self._buf) - self.output_byte_limit
                del self._buf[:excess]  # keep the TAIL, like lapce truncate_tail
                self.truncated = True

    def _reap(self) -> None:
        """Wait for the child and record its real exit code / signal."""
        if self._proc is None:
            return
        rc = self._proc.wait()  # negative => terminated by signal (-rc)
        if rc < 0:
            try:
                self.signal_name = signal.Signals(-rc).name
            except ValueError:
                self.signal_name = str(-rc)
            self.exit_code = None
        else:
            self.exit_code = rc

    async def wait_exit(self) -> tuple[int | None, str | None]:
        """Await the child's exit without blocking the event loop."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._exit_event.wait)
        return self.exit_code, self.signal_name

    def exited(self) -> bool:
        return self._exit_event.is_set()

    def output(self) -> tuple[str, bool]:
        """Return (clean_text, truncated) captured so far."""
        with self._lock:
            raw = bytes(self._buf).decode("utf-8", errors="replace")
        return strip_ansi(raw), self.truncated

    def kill(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()  # SIGKILL
            except ProcessLookupError:
                pass

    def release(self) -> None:
        """Drop resources. The reader thread is a daemon and self-terminates."""
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None


class TerminalManager:
    """Owns the live ClientTerminals keyed by terminal_id."""

    def __init__(self):
        self._terminals: dict[str, ClientTerminal] = {}

    def create(
        self,
        command: str,
        cwd: str | None,
        env: dict[str, str] | None,
        output_byte_limit: int | None,
    ) -> str:
        term = ClientTerminal(command, cwd, env, output_byte_limit)
        term.start()
        terminal_id = str(uuid.uuid4())
        self._terminals[terminal_id] = term
        return terminal_id

    def get(self, terminal_id: str) -> ClientTerminal | None:
        return self._terminals.get(terminal_id)

    def release(self, terminal_id: str) -> None:
        term = self._terminals.pop(terminal_id, None)
        if term is not None:
            term.release()
