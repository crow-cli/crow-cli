"""Spawn a command in a pty — on POSIX and on Windows.

``pty`` is POSIX stdlib and there is no Windows equivalent module at all; the
real pseudoconsole on Windows is ConPTY, reached here through ``pywinpty``
(the ``winpty`` module, a platform-marked dependency in pyproject.toml).

The two cannot share an implementation. ``pty.openpty()`` hands back a master
file descriptor you ``os.read`` and a slave you hand to ``Popen``; ConPTY hands
back a process whose output arrives on a socket. They share an interface
instead: :class:`PtyChild` — the master side of a pty as the terminal code
needs it, read its output and ask how the child ended.
"""

import os
import signal
import subprocess

WINDOWS = os.name == "nt"


class PtyChild:
    """A command running in a pty. Build one with :func:`spawn`."""

    pid: int

    def read(self, size: int = 65536) -> bytes:
        """Up to ``size`` bytes of output; b"" once the pty is closed."""
        raise NotImplementedError

    def status(self) -> tuple[int | None, str | None]:
        """Block until the child exits. Return ``(exit_code, signal_name)``.

        ``signal_name`` is always ``None`` on Windows: there are no signals
        there, a killed process just carries a non-zero exit code.
        """
        raise NotImplementedError

    def kill(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        """Drop our side of the pty. Idempotent."""
        raise NotImplementedError


def spawn(
    command: str,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    dimensions: tuple[int, int] = (24, 80),
) -> PtyChild:
    """Run ``command`` in a pty, through the platform's shell."""
    if WINDOWS:
        return _WindowsChild(command, cwd, env, dimensions)
    return _PosixChild(command, cwd, env)


class _PosixChild(PtyChild):
    def __init__(self, command: str, cwd: str | None, env: dict[str, str] | None):
        import pty

        master, slave = pty.openpty()
        try:
            self._proc = subprocess.Popen(
                ["bash", "-c", command],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=cwd,
                env=env,
                start_new_session=True,
            )
        finally:
            # The child holds its own reference to the slave; the parent only
            # needs the master to read output.
            os.close(slave)
        self.pid = self._proc.pid
        self._fd: int | None = master

    def read(self, size: int = 65536) -> bytes:
        try:
            return os.read(self._fd, size)
        except OSError:
            return b""  # EIO: every slave closed, the child is gone

    def status(self) -> tuple[int | None, str | None]:
        rc = self._proc.wait()
        if rc >= 0:
            return rc, None
        try:
            return None, signal.Signals(-rc).name
        except ValueError:
            return None, str(-rc)

    def kill(self) -> None:
        try:
            self._proc.kill()  # SIGKILL
        except ProcessLookupError:
            pass

    def close(self) -> None:
        if self._fd is None:
            return
        try:
            os.close(self._fd)
        except OSError:
            pass
        self._fd = None


class _WindowsChild(PtyChild):
    def __init__(
        self,
        command: str,
        cwd: str | None,
        env: dict[str, str] | None,
        dimensions: tuple[int, int],
    ):
        from winpty import PtyProcess

        # ConPTY has no fd pair: it takes the whole command line and owns both
        # ends. cmd.exe is what a Windows client's `command` is written for.
        self._shell = os.environ.get("COMSPEC", "cmd.exe")
        self._proc = PtyProcess.spawn(
            [self._shell, "/c", command],
            cwd=cwd,
            env=env,
            dimensions=dimensions,
        )
        self.pid = self._proc.pid

    def read(self, size: int = 65536) -> bytes:
        try:
            return self._proc.read(size).encode("utf-8", "replace")
        except EOFError:
            return b""

    def status(self) -> tuple[int | None, str | None]:
        return self._proc.wait(), None

    def kill(self) -> None:
        try:
            self._proc.kill(signal.SIGTERM)  # TerminateProcess on Windows
        except OSError:
            pass

    def close(self) -> None:
        self._proc.close(force=True)
