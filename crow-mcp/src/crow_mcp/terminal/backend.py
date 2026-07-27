"""PTY-based terminal backend implementation."""

import fcntl
import os
import pty
import select
import shutil
import signal
import subprocess
import threading
import time
from collections import deque
from logging import getLogger
from typing import Any

from .constants import CMD_OUTPUT_PS1_BEGIN, CMD_OUTPUT_PS1_END, HISTORY_LIMIT
from .metadata import CmdOutputMetadata
from .logging_config import setup_terminal_logging

# Initialize logging
setup_terminal_logging()
logger = getLogger(__name__)

ENTER = b"\n"


def _normalize_eols(raw: bytes) -> bytes:
    """Normalize line endings for PTY."""
    raw = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return ENTER.join(raw.split(b"\n"))


class SubprocessTerminal:
    """PTY-backed terminal backend.

    Creates an interactive bash in a pseudoterminal (PTY) so programs behave
    as if attached to a real terminal.
    """

    def __init__(
        self,
        work_dir: str,
        username: str | None = None,
        shell_path: str | None = None,
    ):
        self.work_dir = work_dir
        self.username = username
        self.shell_path = shell_path
        self.PS1 = CmdOutputMetadata.to_ps1_prompt()
        self.process: subprocess.Popen | None = None
        self._pty_master_fd: int | None = None
        self.output_buffer: deque[str] = deque(maxlen=HISTORY_LIMIT + 50)
        self.output_lock = threading.Lock()
        self.reader_thread: threading.Thread | None = None
        self._current_command_running = False
        self._initialized = False
        self._closed = False

    def initialize(self) -> None:
        """Initialize the PTY terminal session."""
        if self._initialized:
            return

        # Resolve shell path
        resolved_shell_path: str | None
        if self.shell_path:
            resolved_shell_path = self.shell_path
        else:
            resolved_shell_path = shutil.which("bash")
            if resolved_shell_path is None:
                raise RuntimeError(
                    "Could not find bash in PATH. "
                    "Please provide an explicit shell_path parameter."
                )

        # Validate shell
        if not os.path.isfile(resolved_shell_path):
            raise RuntimeError(f"Shell binary not found at: {resolved_shell_path}")
        if not os.access(resolved_shell_path, os.X_OK):
            raise RuntimeError(f"Shell binary is not executable: {resolved_shell_path}")

        logger.info(f"Initializing PTY terminal with shell: {resolved_shell_path}")

        # Create pseudoterminal
        master_fd, slave_fd = pty.openpty()

        # Set up environment
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        # Note: PS1 env var doesn't work for interactive bash - we set it after startup
        if self.work_dir:
            env["PWD"] = self.work_dir

        # Start bash process
        self.process = subprocess.Popen(
            [resolved_shell_path],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=env,
            cwd=self.work_dir,
            preexec_fn=os.setsid,
        )

        # Close slave fd in parent (child has it now)
        os.close(slave_fd)
        self._pty_master_fd = master_fd

        # Set non-blocking mode
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # Start reader thread
        self.reader_thread = threading.Thread(target=self._read_output, daemon=True)
        self.reader_thread.start()

        # Wait for bash to start
        time.sleep(0.3)
        
        # Set PS1 after bash starts (env var doesn't work for interactive shells)
        logger.debug(f"Setting PS1 to: {self.PS1!r}")
        ps1_command = f'PS1="{self.PS1}"\n'
        os.write(self._pty_master_fd, ps1_command.encode("utf-8"))
        time.sleep(0.2)  # Let PS1 take effect
        
        # Clear the buffer (will contain the PS1 command we just sent)
        self.clear_screen()
        
        self._initialized = True
        logger.info("PTY terminal initialized successfully")

    def _read_output(self) -> None:
        """Background thread to continuously read terminal output."""
        while not self._closed:
            try:
                if self._pty_master_fd is None:
                    break

                # Use select to wait for data
                ready, _, _ = select.select([self._pty_master_fd], [], [], 0.1)
                if not ready:
                    continue

                try:
                    data = os.read(self._pty_master_fd, 4096)
                    if data:
                        text = data.decode("utf-8", errors="replace")
                        with self.output_lock:
                            self.output_buffer.append(text)
                except BlockingIOError:
                    pass
                except OSError:
                    break

            except Exception as e:
                logger.error(f"Error in reader thread: {e}", exc_info=True)
                break

    def send_keys(self, text: str, enter: bool = True) -> None:
        """Send text/keys to the terminal."""
        if not self._initialized or self._pty_master_fd is None:
            raise RuntimeError("Terminal not initialized")

        # Normalize line endings
        data = _normalize_eols(text.encode("utf-8"))
        if enter and not text.endswith("\n"):
            data += ENTER

        os.write(self._pty_master_fd, data)

    def read_screen(self) -> str:
        """Read all accumulated terminal output."""
        with self.output_lock:
            return "".join(self.output_buffer)

    def clear_screen(self) -> None:
        """Clear the terminal buffer."""
        with self.output_lock:
            self.output_buffer.clear()

    def interrupt(self) -> bool:
        """Send interrupt signal (Ctrl+C) to the terminal."""
        if self.process and self.process.poll() is None:
            try:
                # Send SIGINT to the process group
                os.killpg(os.getpgid(self.process.pid), signal.SIGINT)
                return True
            except Exception as e:
                logger.error(f"Failed to send interrupt: {e}")
                return False
        return False

    def is_running(self) -> bool:
        """Check if a command is currently running."""
        return self._current_command_running

    def close(self) -> None:
        """Clean up the terminal backend."""
        if self._closed:
            return

        self._closed = True

        if self.process and self.process.poll() is None:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                self.process.wait(timeout=2)
            except Exception as e:
                logger.warning(f"Error terminating process: {e}")
                try:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                except Exception:
                    pass

        if self._pty_master_fd is not None:
            try:
                os.close(self._pty_master_fd)
            except Exception:
                pass
            self._pty_master_fd = None

        if self.reader_thread and self.reader_thread.is_alive():
            self.reader_thread.join(timeout=1)

        logger.info("PTY terminal closed")

    @property
    def initialized(self) -> bool:
        """Check if the terminal is initialized."""
        return self._initialized

    @property
    def closed(self) -> bool:
        """Check if the terminal is closed."""
        return self._closed
