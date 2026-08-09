"""Tests for the Crow ACP client's client-side terminal.

The client implements the ACP ``terminal/*`` methods so the agent's terminal
tool runs in a real PTY owned by the client (emulating the IDE's client-side
terminals) instead of crow-mcp's standalone shell. The headline behavior these
tests lock in: **correct exit codes** (the standalone terminal mis-reported
every exit code as 0), a real tty environment, and clean (ANSI-stripped) text
handed back to the model.
"""

import os

import pytest
from rich.console import Console

from crow_cli.client.main import CrowClient
from crow_cli.client.terminal import ClientTerminal, TerminalManager, strip_ansi


async def _run(command, cwd=None, limit=None):
    """Run a command in a ClientTerminal; return (exit_code, signal, out, truncated)."""
    term = ClientTerminal(command, cwd=cwd, output_byte_limit=limit)
    term.start()
    code, sig = await term.wait_exit()
    out, truncated = term.output()
    term.release()
    return code, sig, out, truncated


class TestStripAnsi:
    def test_strips_color_csi(self):
        assert strip_ansi("\x1b[31mred\x1b[0m text") == "red text"

    def test_strips_cursor_and_clear(self):
        assert strip_ansi("\x1b[2J\x1b[Hhello\x1b[10;5H") == "hello"

    def test_strips_osc_title(self):
        assert strip_ansi("\x1b]0;window title\x07body") == "body"

    def test_strips_carriage_return_overwrite(self):
        # progress-style overwrite collapses the way a grid would
        assert strip_ansi("1%\r100%\rdone") == "1%100%done"

    def test_plain_text_passthrough(self):
        assert strip_ansi("just text\nline two") == "just text\nline two"


class TestClientTerminal:
    async def test_echo_exit_zero(self):
        code, sig, out, _ = await _run("echo hello")
        assert code == 0
        assert sig is None
        assert "hello" in out

    async def test_failing_command_reports_nonzero_exit(self):
        """Regression: the standalone terminal reported 0 for `false`."""
        code, sig, _, _ = await _run("false")
        assert code == 1
        assert sig is None

    async def test_explicit_exit_code(self):
        code, _, _, _ = await _run("bash -c 'exit 3'")
        assert code == 3

    async def test_stderr_is_captured(self):
        code, _, out, _ = await _run("bash -c 'echo oops >&2'")
        assert code == 0
        assert "oops" in out

    async def test_command_error_text_captured(self):
        code, _, out, _ = await _run("ls /definitely/not/here")
        assert code != 0
        assert "No such file or directory" in out

    async def test_runs_in_a_real_tty(self):
        """Faithful to the IDE terminals: the child's stdout is a tty."""
        code, _, out, _ = await _run("bash -c '[ -t 1 ] && echo TTY || echo NOTTY'")
        assert code == 0
        assert "TTY" in out

    async def test_term_env_matches_zed(self):
        _, _, out, _ = await _run("echo $TERM/$COLORTERM")
        assert "xterm-256color/truecolor" in out

    async def test_ansi_stripped_from_output(self):
        _, _, out, _ = await _run("printf '\\033[31mred\\033[0m text'")
        assert "red text" in out
        assert "\x1b" not in out

    async def test_output_truncated_keeps_tail(self):
        _, _, out, truncated = await _run("seq 1 100000", limit=2000)
        assert truncated is True
        assert out.rstrip().endswith("100000")  # tail preserved (lapce-style)

    async def test_small_output_not_truncated(self):
        _, _, out, truncated = await _run("echo short", limit=2000)
        assert truncated is False
        assert "short" in out

    async def test_cwd_respected(self, tmp_path):
        _, _, out, _ = await _run("pwd", cwd=str(tmp_path))
        assert tmp_path.name in out

    async def test_kill_sets_signal(self):
        term = ClientTerminal("sleep 30")
        term.start()
        term.kill()
        code, sig = await term.wait_exit()
        term.release()
        assert code is None
        assert sig is not None  # SIGKILL


class TestTerminalManager:
    async def test_create_get_release_lifecycle(self):
        mgr = TerminalManager()
        tid = mgr.create("echo managed", cwd=None, env=None, output_byte_limit=None)
        term = mgr.get(tid)
        assert term is not None
        await term.wait_exit()
        out, _ = term.output()
        assert "managed" in out
        mgr.release(tid)
        assert mgr.get(tid) is None


class TestCrowClientTerminalMethods:
    """Exercise the actual ACP-facing terminal/* methods on CrowClient."""

    def _client(self):
        return CrowClient(console=Console())

    async def test_create_wait_output_release(self, tmp_path):
        client = self._client()
        created = await client.create_terminal(
            command="echo hi", session_id="s", cwd=str(tmp_path)
        )
        tid = created.terminal_id
        assert tid

        exited = await client.wait_for_terminal_exit(session_id="s", terminal_id=tid)
        assert exited.exit_code == 0

        output = await client.terminal_output(session_id="s", terminal_id=tid)
        assert "hi" in output.output
        assert output.truncated is False

        await client.release_terminal(session_id="s", terminal_id=tid)
        assert client._terminals.get(tid) is None

    async def test_failing_command_exit_code(self):
        client = self._client()
        created = await client.create_terminal(command="false", session_id="s")
        exited = await client.wait_for_terminal_exit(
            session_id="s", terminal_id=created.terminal_id
        )
        assert exited.exit_code == 1
        await client.release_terminal(session_id="s", terminal_id=created.terminal_id)

    async def test_output_reports_exit_status_after_exit(self):
        client = self._client()
        created = await client.create_terminal(command="echo done", session_id="s")
        await client.wait_for_terminal_exit(session_id="s", terminal_id=created.terminal_id)
        output = await client.terminal_output(session_id="s", terminal_id=created.terminal_id)
        assert output.exit_status is not None
        assert output.exit_status.exit_code == 0
        await client.release_terminal(session_id="s", terminal_id=created.terminal_id)

    async def test_kill_terminal(self):
        client = self._client()
        created = await client.create_terminal(command="sleep 30", session_id="s")
        await client.kill_terminal(session_id="s", terminal_id=created.terminal_id)
        exited = await client.wait_for_terminal_exit(
            session_id="s", terminal_id=created.terminal_id
        )
        assert exited.exit_code is None
        assert exited.signal is not None
        await client.release_terminal(session_id="s", terminal_id=created.terminal_id)

    async def test_unknown_terminal_id_is_safe(self):
        client = self._client()
        output = await client.terminal_output(session_id="s", terminal_id="nope")
        assert output.output == ""
        exited = await client.wait_for_terminal_exit(session_id="s", terminal_id="nope")
        assert exited.exit_code is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
