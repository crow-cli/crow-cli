"""``--include-tools`` over a real wire.

The unit tier proves what ``register_tools`` asks for; this tier proves what a
client on the other end of a socket actually gets. Every server here is a real
subprocess running THIS tree's ``crow-cli`` console script, so flag parsing,
the selective import and the fastmcp allowlist are all exercised as shipped —
including the import pruning, which is only observable across a process
boundary (in one process an earlier test has already imported every module).
"""

import asyncio
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from fastmcp import Client as MCPClient
from fastmcp.client.transports import MCPConfigTransport, StreamableHttpTransport

from crow_cli.mcp import tool_names

# Under `uv --project . run pytest` this is the project venv's console script,
# i.e. THIS tree's code. Not the installed one, not $PATH's.
CROW_CLI = Path(sys.executable).parent / "crow-cli"
REPO_ROOT = Path(__file__).resolve().parents[2]
ALL = sorted(tool_names())


def run_cli(args: list[str], timeout: float = 60.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(CROW_CLI), *args], capture_output=True, text=True, timeout=timeout
    )


def stdio_client(args: list[str]) -> MCPClient:
    cfg = {
        "mcpServers": {
            "crow": {
                "transport": "stdio",
                "command": str(CROW_CLI),
                "args": ["mcp", *args],
            }
        }
    }
    return MCPClient(MCPConfigTransport(cfg, name_as_prefix=False))


async def served(args: list[str]) -> list[str]:
    async with stdio_client(args) as client:
        return sorted(t.name for t in await client.list_tools())


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
    raise TimeoutError(f"crow-cli mcp never came up on :{port}")


class TestListTools:
    def test_prints_the_registry_sorted_one_per_line(self):
        proc = run_cli(["mcp", "--list-tools"])
        assert proc.returncode == 0
        assert proc.stdout.splitlines() == ALL
        assert proc.stderr == ""

    def test_imports_no_tool_group_to_answer(self):
        # --list-tools must not pay the tool-group import bill (vision pulls
        # opencv). Wall time would prove it too but flakily; sys.modules
        # proves it exactly. Run the real CLI entry point in a subprocess and
        # ask the interpreter what it loaded on the way out.
        probe = (
            "import sys\n"
            "sys.argv = ['crow-cli', 'mcp', '--list-tools']\n"
            "from crow_cli.cli.main import main\n"
            "try:\n"
            "    main()\n"
            "except SystemExit:\n"
            "    pass\n"
            "loaded = sorted(m for m in sys.modules if m.startswith('crow_cli.mcp.'))\n"
            "print('LOADED:' + ','.join(loaded), file=sys.stderr)\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        assert proc.returncode == 0
        assert proc.stdout.splitlines() == ALL
        loaded = [
            line[len("LOADED:") :].split(",")
            for line in proc.stderr.splitlines()
            if line.startswith("LOADED:")
        ][0]
        groups = {m.split(".")[2] for m in loaded if len(m.split(".")) > 2}
        assert groups == {"server"}, f"--list-tools imported tool groups: {groups}"


class TestBadSelection:
    def test_unknown_tool_is_refused_at_the_door(self):
        proc = run_cli(["mcp", "--include-tools", "read,bogus,nope"])
        assert proc.returncode == 2
        # stdout is the JSON-RPC stream on stdio: the complaint must not be on
        # it, or every client would see a protocol violation instead of an
        # error at spawn time.
        assert proc.stdout == ""
        assert "bogus" in proc.stderr and "nope" in proc.stderr
        assert "read" not in proc.stderr.split("available:")[0]
        for name in ALL:
            assert name in proc.stderr

    def test_an_empty_selection_is_refused(self):
        proc = run_cli(["mcp", "--include-tools", " , "])
        assert proc.returncode == 2
        assert proc.stdout == ""
        assert "resolved to no tool names" in proc.stderr

    def test_no_server_is_spawned_for_a_bad_selection(self):
        # Refusal at parse time, not a server that starts and then serves
        # nothing: a client connecting to it would hang on list_tools, not
        # fail.
        proc = run_cli(["mcp", "--include-tools", "bogus"], timeout=15)
        assert proc.returncode == 2


class TestStdioSlices:
    async def test_no_flag_is_everything(self):
        assert await served([]) == ALL

    async def test_a_comma_list_is_that_slice(self):
        assert await served(["--include-tools", "read,write,edit"]) == [
            "edit",
            "read",
            "write",
        ]

    async def test_repeated_flags_across_a_shared_module(self):
        # memory.main owns three tools; asking for one must serve one.
        assert await served(
            ["--include-tools", "query_memory", "--include-tools", "task"]
        ) == ["query_memory", "task"]

    async def test_a_deselected_tool_is_refused_over_the_wire(self):
        async with stdio_client(["--include-tools", "read"]) as client:
            assert sorted(t.name for t in await client.list_tools()) == ["read"]
            # Not merely absent from the listing: a client that guesses the
            # name is refused by the server.
            with pytest.raises(Exception, match="terminal"):
                await client.call_tool("terminal", {"command": "echo pwned"})

    async def test_a_selected_tool_actually_works(self, tmp_path):
        target = tmp_path / "served.txt"
        target.write_text("served over stdio\n")
        async with stdio_client(["--include-tools", "read"]) as client:
            result = await client.call_tool("read", {"file_path": str(target)})
        text = result.content[0].text
        assert "served over stdio" in text


class TestHttpSlice:
    async def test_http_serves_the_selection(self, free_tcp_port):
        proc = await asyncio.create_subprocess_exec(
            str(CROW_CLI),
            "mcp",
            "--transport",
            "http",
            "--port",
            str(free_tcp_port),
            "--include-tools",
            "read,web_search",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await wait_port(free_tcp_port)
            url = f"http://127.0.0.1:{free_tcp_port}/mcp"
            async with MCPClient(StreamableHttpTransport(url)) as client:
                assert sorted(t.name for t in await client.list_tools()) == [
                    "read",
                    "web_search",
                ]
        finally:
            proc.terminate()
            await proc.wait()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
