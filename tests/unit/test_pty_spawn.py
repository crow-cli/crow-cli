"""The pty shim: one interface over stdlib pty and ConPTY.

``ClientTerminal`` no longer knows which platform it is on — it reads output,
asks for the exit status, kills and closes. These lock that interface down on
the POSIX implementation, plus the two properties the Windows branch depends on:
importing the module must not import ``winpty``, and ``winpty`` must not be
imported anywhere but the Windows branch.
"""

import os
import signal
import subprocess
import sys
import types

from crow_cli.client import pty_spawn
from crow_cli.client.pty_spawn import spawn


def _drain(child, size=65536):
    out = bytearray()
    while True:
        chunk = child.read(size)
        if not chunk:
            return bytes(out)
        out.extend(chunk)


class TestPosixPtyChild:
    def test_output_arrives_and_the_exit_code_is_real(self):
        child = spawn("echo hello; exit 3")
        try:
            assert b"hello" in _drain(child)
            assert child.status() == (3, None)
        finally:
            child.close()

    def test_the_child_sees_a_tty(self):
        child = spawn("test -t 0 && echo tty || echo pipe")
        try:
            assert b"tty" in _drain(child)
            assert child.status() == (0, None)
        finally:
            child.close()

    def test_a_signalled_child_reports_the_signal_not_an_exit_code(self):
        child = spawn("kill -9 $$")
        try:
            _drain(child)
            assert child.status() == (None, "SIGKILL")
        finally:
            child.close()

    def test_kill_terminates_a_running_child(self):
        child = spawn("sleep 30")
        child.kill()
        assert child.status() == (None, "SIGKILL")
        child.close()

    def test_close_is_idempotent(self):
        child = spawn("echo once")
        _drain(child)
        child.status()
        child.close()
        child.close()


class TestPlatformSelection:
    def test_the_windows_branch_is_not_taken_here(self):
        assert pty_spawn.WINDOWS is False
        assert isinstance(spawn("true"), pty_spawn._PosixChild)

    def test_the_windows_branch_uses_cmd_and_has_no_signals(self, monkeypatch):
        """pywinpty ships only win_amd64/win_arm64 wheels, so the branch is
        reached here through a stand-in for the surface read off its source:
        spawn(argv, cwd, env, dimensions), read()->str|EOFError, wait(),
        kill(sig), close(force)."""
        seen = {}

        class FakeProc:
            pid = 4242

            def read(self, size):
                raise EOFError("Pty is closed")

            def wait(self):
                return 0

            def kill(self, sig):
                seen["kill"] = sig

            def close(self, force=False):
                seen["close"] = force

        class FakePtyProcess:
            @classmethod
            def spawn(cls, argv, cwd=None, env=None, dimensions=(24, 80)):
                seen.update(argv=argv, cwd=cwd, dimensions=dimensions)
                return FakeProc()

        monkeypatch.setitem(
            sys.modules, "winpty", types.SimpleNamespace(PtyProcess=FakePtyProcess)
        )
        monkeypatch.setattr(pty_spawn, "WINDOWS", True)

        child = spawn("dir", cwd="C:/work", env={"PATH": "C:/x"})

        assert seen["argv"][:2] == [os.environ.get("COMSPEC", "cmd.exe"), "/c"]
        assert seen["argv"][2] == "dir"
        assert seen["cwd"] == "C:/work"
        assert child.read(10) == b""  # EOFError is EOF, not a failure
        assert child.status() == (0, None)  # Windows has no signals
        child.kill()
        child.close()
        assert seen["kill"] == signal.SIGTERM  # TerminateProcess on Windows
        assert seen["close"] is True

    def test_importing_the_shim_does_not_import_winpty(self):
        """pywinpty is a win32-only dependency; on Linux it is not installed."""
        out = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys, crow_cli.client.pty_spawn;"
                " assert 'winpty' not in sys.modules",
            ],
            capture_output=True,
            text=True,
        )
        assert out.returncode == 0, out.stderr
