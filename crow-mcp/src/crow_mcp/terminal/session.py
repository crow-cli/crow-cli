"""Terminal session controller with command execution logic."""

import re
import time
from logging import getLogger
from typing import Any

from .backend import SubprocessTerminal
from .constants import (
    CMD_OUTPUT_PS1_END,
    CMD_OUTPUT_PS1_BEGIN,
    NO_CHANGE_TIMEOUT_SECONDS,
    POLL_INTERVAL,
    TIMEOUT_MESSAGE_TEMPLATE,
)
from .metadata import CmdOutputMetadata
from .logging_config import setup_terminal_logging

# Initialize logging
setup_terminal_logging()
logger = getLogger(__name__)


class TerminalSession:
    """Terminal session controller that manages command execution."""

    def __init__(
        self,
        work_dir: str,
        username: str | None = None,
        no_change_timeout_seconds: int | None = None,
        shell_path: str | None = None,
    ):
        self.work_dir = work_dir
        self.username = username
        self.no_change_timeout_seconds = (
            no_change_timeout_seconds or NO_CHANGE_TIMEOUT_SECONDS
        )
        self.backend = SubprocessTerminal(
            work_dir=work_dir,
            username=username,
            shell_path=shell_path,
        )
        self._initialized = False
        self._closed = False
        self.prev_output = ""

    def initialize(self) -> None:
        """Initialize the terminal session."""
        if self._initialized:
            return

        self.backend.initialize()
        self._initialized = True
        logger.info(f"Terminal session initialized in {self.work_dir}")

    def close(self) -> None:
        """Close the terminal session."""
        if self._closed:
            return

        self.backend.close()
        self._closed = True
        logger.info("Terminal session closed")

    def is_running(self) -> bool:
        """Check if terminal is active."""
        return self._initialized and not self._closed

    def _is_special_key(self, command: str) -> bool:
        """Check if the command is a special key sequence."""
        cmd = command.strip()
        return cmd.startswith("C-") and len(cmd) == 3

    def _get_command_output(
        self,
        command: str,
        raw_output: str,
        metadata: CmdOutputMetadata,
        continue_prefix: str = "",
    ) -> str:
        """Extract command output from raw terminal output."""
        # Remove previous output if continuing
        if self.prev_output:
            output = raw_output.removeprefix(self.prev_output)
            metadata.prefix = continue_prefix
        else:
            output = raw_output

        self.prev_output = raw_output

        # Remove command echo from output
        output = output.lstrip().removeprefix(command.lstrip()).lstrip()

        return output.rstrip()

    def execute(
        self,
        command: str,
        is_input: bool = False,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Execute a command and return result dict."""

        if not self._initialized:
            raise RuntimeError("Terminal session not initialized")

        if self._closed:
            raise RuntimeError("Terminal session is closed")

        # Handle special keys
        if self._is_special_key(command):
            return self._handle_special_key(command)

        # Handle input to running process
        if is_input:
            return self._handle_input(command)

        # Normal command execution
        return self._execute_command(command, timeout)

    def _handle_special_key(self, command: str) -> dict[str, Any]:
        """Handle special key sequences like C-c, C-z, C-d."""
        key = command.strip().upper()

        if key == "C-C":
            self.backend.interrupt()
            return {
                "output": "Process interrupted (Ctrl+C)",
                "exit_code": 130,
                "working_dir": self._detect_working_dir(),
                "py_interpreter": self._detect_python(),
            }
        elif key == "C-Z":
            self.backend.send_keys("\x1a", enter=False)
            return {
                "output": "Process suspended (Ctrl+Z)",
                "exit_code": 147,
                "working_dir": self._detect_working_dir(),
                "py_interpreter": self._detect_python(),
            }
        elif key == "C-D":
            self.backend.send_keys("\x04", enter=False)
            return {
                "output": "EOF sent (Ctrl+D)",
                "exit_code": 0,
                "working_dir": self._detect_working_dir(),
                "py_interpreter": self._detect_python(),
            }
        else:
            return {
                "output": f"Unknown special key: {command}",
                "exit_code": 1,
                "working_dir": self._detect_working_dir(),
                "py_interpreter": self._detect_python(),
            }

    def _handle_input(self, command: str) -> dict[str, Any]:
        """Handle input to running process."""
        self.backend.send_keys(command, enter=True)
        time.sleep(0.1)

        return {
            "output": f"Input sent: {command}",
            "exit_code": -1,  # Process still running
            "working_dir": self._detect_working_dir(),
            "py_interpreter": self._detect_python(),
        }

    def _execute_command(self, command: str, timeout: float | None) -> dict[str, Any]:
        """Execute a normal command with timeout handling."""

        logger.debug(f"Executing command: {command!r}")

        # Clear buffer and send command
        self.backend.clear_screen()
        self.backend.send_keys(command, enter=True)

        start_time = time.time()
        last_change_time = start_time
        last_output = ""
        poll_count = 0

        # Poll for completion
        while True:
            current_time = time.time()
            elapsed = current_time - start_time
            poll_count += 1

            # Read current output
            output = self.backend.read_screen()

            # Debug: log output every 10 polls or if it changed
            if poll_count % 10 == 0 or output != last_output:
                logger.debug(f"Poll #{poll_count} (elapsed={elapsed:.1f}s): output length={len(output)}")
                if output != last_output:
                    logger.debug(f"Output changed, new content:\n{output[-500:]}")  # Last 500 chars

            # Check for PS1 metadata (command complete)
            ps1_matches = CmdOutputMetadata.matches_ps1_metadata(output)
            if ps1_matches:
                logger.info(f"✅ PS1 metadata found! {len(ps1_matches)} matches after {elapsed:.1f}s")
                logger.debug(f"PS1 content: {ps1_matches[-1].group(1)[:200]}")
                # Command completed
                return self._build_result(command, output, ps1_matches)
            else:
                # Log why PS1 didn't match (every 20 polls)
                if poll_count % 20 == 0:
                    logger.debug(f"No PS1 match. Looking for pattern in output...")
                    if CMD_OUTPUT_PS1_BEGIN.strip() in output:
                        logger.debug(f"Found PS1_BEGIN marker, but no full match")
                    else:
                        logger.debug(f"PS1_BEGIN marker not found in output")

            # Check for hard timeout
            if timeout is not None and elapsed >= timeout:
                logger.warning(f"⏱️ Hard timeout reached ({timeout}s)")
                return {
                    "output": output + f"\n\n[Command timed out after {timeout}s]",
                    "exit_code": -1,
                    "working_dir": self._detect_working_dir(),
                    "py_interpreter": self._detect_python(),
                }

            # Check for soft timeout (no change)
            if output != last_output:
                last_change_time = current_time
                last_output = output
            elif current_time - last_change_time >= self.no_change_timeout_seconds:
                logger.warning(f"⏱️ Soft timeout: no output change for {self.no_change_timeout_seconds}s")
                logger.debug(f"Final output length: {len(output)}, elapsed: {elapsed:.1f}s")
                return {
                    "output": output + f"\n\n{TIMEOUT_MESSAGE_TEMPLATE}",
                    "exit_code": -1,
                    "working_dir": self._detect_working_dir(),
                    "py_interpreter": self._detect_python(),
                }

            # Sleep before next poll
            time.sleep(POLL_INTERVAL)

    def _build_result(
        self,
        command: str,
        raw_output: str,
        ps1_matches: list[re.Match],
    ) -> dict[str, Any]:
        """Build result dict from completed command."""

        # Extract metadata from last PS1 match
        metadata = CmdOutputMetadata.from_ps1_match(ps1_matches[-1])

        # Get clean output
        output = self._get_command_output(command, raw_output, metadata)

        # Remove PS1 metadata from output
        for match in ps1_matches:
            output = output.replace(match.group(0), "")

        return {
            "output": output.strip(),
            "exit_code": metadata.exit_code,
        }

    def _detect_working_dir(self) -> str:
        """Detect current working directory (fallback if PS1 didn't work)."""
        return self.work_dir  # Return initial work_dir as fallback

    def _detect_python(self) -> str | None:
        """Detect Python interpreter path (fallback if PS1 didn't work)."""
        return None  # PS1 should provide this

    @property
    def closed(self) -> bool:
        """Check if session is closed."""
        return self._closed
