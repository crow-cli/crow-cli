"""``crow-cli mcp2`` over a real wire.

Every server here is a real subprocess running THIS tree's console script, so
flag parsing, the import ordering inside the CLI command and fastmcp's stdio
handshake are all exercised as shipped. The in-process half — registration, the
prelude, ``serve()``'s transport wiring — is ``tests/mcp/test_mcp2_server.py``.

Two things are only visible across a process boundary and are the reason this
file exists separately:

* ``--list-tools`` must not import the tool it lists. In one process an earlier
  test has already imported everything, so pruning is unobservable.
* The kernel is keyed by ACP session id, which is what lets one HTTP server
  host many sessions. Over stdio that is latent; over HTTP it is the design.
"""

import asyncio
import base64
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport

from crow_cli.mcp2 import tool_names

# Under `uv --project . run pytest` this is the project venv's console script,
# i.e. THIS tree's code. Not the installed one, not $PATH's.
CROW_CLI = Path(sys.executable).parent / "crow-cli"
ALL = tool_names()


def run_cli(args: list[str], timeout: float = 60.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(CROW_CLI), *args], capture_output=True, text=True, timeout=timeout
    )


def stdio_client(args: list[str] = ()) -> Client:
    return Client(StdioTransport(command=str(CROW_CLI), args=["mcp2", *args]))


async def cell(client: Client, code: str, **meta) -> dict:
    """One execute call, decoded. execute answers a JSON document, not text."""
    result = await client.call_tool("execute", {"code": code}, meta=meta or None)
    assert not result.is_error, result.content[0].text
    return json.loads(result.content[0].text)


async def wait_port(port: int, timeout: float = 30.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            await asyncio.sleep(0.1)
            continue
        writer.close()
        await writer.wait_closed()
        return
    raise TimeoutError(f"crow-cli mcp2 never came up on :{port}")


class TestListTools:
    def test_prints_the_registry_one_per_line(self):
        proc = run_cli(["mcp2", "--list-tools"])
        assert proc.returncode == 0
        assert proc.stdout.splitlines() == ALL
        assert proc.stderr == ""

    def test_imports_no_tool_module_to_answer(self):
        # --list-tools must not pay for jupyter_client and ipykernel. Wall time
        # would prove it flakily; sys.modules proves it exactly. Run the real
        # CLI entry point in a subprocess and ask the interpreter what it
        # loaded on the way out. This is what pins the import ORDER inside
        # cli.main.run_mcp2: crow_cli.mcp2.main imports the execute tool at
        # module scope, so importing it before the --list-tools branch would
        # show up right here.
        probe = (
            "import sys\n"
            "sys.argv = ['crow-cli', 'mcp2', '--list-tools']\n"
            "from crow_cli.cli.main import main\n"
            "try:\n"
            "    main()\n"
            "except SystemExit:\n"
            "    pass\n"
            "loaded = sorted(m for m in sys.modules if m.startswith('crow_cli.mcp2'))\n"
            "print('LOADED:' + ','.join(loaded), file=sys.stderr)\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True
        )
        assert proc.returncode == 0
        assert proc.stdout.splitlines() == ALL
        loaded = [
            line[len("LOADED:"):].split(",")
            for line in proc.stderr.splitlines()
            if line.startswith("LOADED:")
        ][0]
        assert loaded == ["crow_cli.mcp2"], f"--list-tools imported: {loaded}"

    def test_the_module_entry_point_agrees_with_the_console_script(self):
        # `python -m crow_cli.mcp2.main` is how a source checkout spawns the
        # server without an installed console script.
        proc = subprocess.run(
            [sys.executable, "-m", "crow_cli.mcp2.main", "--list-tools"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0
        assert proc.stdout.splitlines() == ALL

    def test_a_bad_transport_is_refused_at_the_door(self):
        # One line on stderr, an exit code, and NOTHING on stdout — which is
        # the part that is easy to get wrong, because serve()'s HTTP branch
        # prints its url before it blocks. A typo used to advertise a server
        # that never started and then fail with fastmcp's own ValueError.
        proc = run_cli(["mcp2", "--transport", "carrier-pigeon"], timeout=30)
        assert proc.returncode == 2
        assert proc.stdout == ""
        assert "carrier-pigeon" in proc.stderr
        assert "Traceback" not in proc.stderr


class TestStdio:
    async def test_it_serves_exactly_the_registry(self):
        async with stdio_client() as client:
            assert sorted(t.name for t in await client.list_tools()) == ALL

    async def test_a_cell_runs_and_comes_back_in_two_voices(self):
        # The whole reason mcp2's execute is not v1's: one payload, two
        # audiences. `output` is what the model reads (ANSI stripped), and
        # `raw_bytes_b64` is what the client renders (ANSI intact) — the agent
        # lifts the latter into TerminalUpdate.output and never shows it to
        # the model.
        async with stdio_client() as client:
            out = await cell(client, 'print("\\x1b[31mred\\x1b[0m")')
        assert out["exit_code"] == 0
        assert out["timed_out"] is False
        assert out["output"] == "red\n"
        assert base64.b64decode(out["raw_bytes_b64"]) == b"\x1b[31mred\x1b[0m\n"

    async def test_the_kernel_persists_across_calls(self):
        # "One persistent REPL per session" is the product; a fresh process per
        # call would still pass every other test in this file.
        async with stdio_client() as client:
            await cell(client, "answer = 6 * 7", session_id="persist")
            out = await cell(client, "print(answer)", session_id="persist")
        assert out["output"] == "42\n"

    async def test_two_session_ids_get_two_kernels(self):
        async with stdio_client() as client:
            await cell(client, "mine = 1", session_id="sess-a")
            out = await cell(client, "print('mine' in dir())", session_id="sess-b")
        assert out["output"] == "False\n"

    async def test_a_bare_caller_is_keyed_by_cwd(self):
        # No _meta at all: the server has nothing to key on but its own cwd,
        # and the cell still runs rather than erroring out.
        async with stdio_client() as client:
            result = await client.call_tool("execute", {"code": "print(1 + 1)"})
        assert not result.is_error
        assert json.loads(result.content[0].text)["output"] == "2\n"


class TestHttp:
    async def test_http_serves_the_same_surface(self, free_tcp_port):
        proc = await asyncio.create_subprocess_exec(
            str(CROW_CLI),
            "mcp2",
            "--transport",
            "http",
            "--port",
            str(free_tcp_port),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await wait_port(free_tcp_port)
            url = f"http://127.0.0.1:{free_tcp_port}/mcp"
            async with Client(StreamableHttpTransport(url)) as client:
                assert sorted(t.name for t in await client.list_tools()) == ALL
                out = await cell(client, "print('over http')", session_id="http-1")
            assert out["output"] == "over http\n"
        finally:
            proc.terminate()
            await proc.wait()

    async def test_one_http_server_hosts_two_sessions(self, free_tcp_port):
        # The reason the kernel is keyed by session id rather than by process:
        # a long-lived host, many clients, each with its own REPL.
        proc = await asyncio.create_subprocess_exec(
            str(CROW_CLI),
            "mcp2",
            "--transport",
            "http",
            "--port",
            str(free_tcp_port),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await wait_port(free_tcp_port)
            url = f"http://127.0.0.1:{free_tcp_port}/mcp"
            async with Client(StreamableHttpTransport(url)) as one:
                await cell(one, "who = 'one'", session_id="host-a")
            async with Client(StreamableHttpTransport(url)) as two:
                out = await cell(two, "print('who' in dir())", session_id="host-b")
                back = await cell(two, "print(who)", session_id="host-a")
            assert out["output"] == "False\n"
            assert back["output"] == "one\n"
        finally:
            proc.terminate()
            await proc.wait()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
