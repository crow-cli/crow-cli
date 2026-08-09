"""
Test client that spawns agent-client and tells it to run `date` with terminal.

Implements real terminal and FS capabilities so the child agent's tool calls
actually round-trip through agent-client to this test client.
"""

import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from acp import spawn_agent_process, text_block
from acp.interfaces import Client
from acp.schema import (
    CreateTerminalResponse,
    EnvVariable,
    KillTerminalCommandResponse,
    ReadTextFileResponse,
    ReleaseTerminalResponse,
    RequestPermissionResponse,
    TerminalOutputResponse,
    WaitForTerminalExitResponse,
    WriteTextFileResponse,
)


class RealClient(Client):
    """Test client that actually runs terminals and reads/writes files."""

    def __init__(self):
        self._terminals: dict[str, asyncio.subprocess.Process] = {}
        self._terminal_output: dict[str, str] = {}
        self._terminal_exit_code: dict[str, int | None] = {}
        self._terminal_signal: dict[str, int | None] = {}
        self._permission_auto_allow = True

    # -- Terminal methods --

    async def create_terminal(
        self,
        command: str,
        session_id: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: list[EnvVariable] | None = None,
        output_byte_limit: int | None = None,
        **kwargs: Any,
    ) -> CreateTerminalResponse:
        terminal_id = str(uuid.uuid4())
        print(
            f"[create_terminal] cmd={command} args={args} terminal_id={terminal_id}",
            flush=True,
        )

        full_cmd = [command] + (args or [])
        proc_env = os.environ.copy()
        if env:
            for e in env:
                proc_env[e.name] = e.value

        proc = await asyncio.create_subprocess_exec(
            *full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=proc_env,
        )
        self._terminals[terminal_id] = proc
        self._terminal_output[terminal_id] = ""
        self._terminal_exit_code[terminal_id] = None
        self._terminal_signal[terminal_id] = None

        return CreateTerminalResponse(terminal_id=terminal_id)

    async def terminal_output(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> TerminalOutputResponse:
        proc = self._terminals.get(terminal_id)
        if not proc:
            return TerminalOutputResponse(output="", truncated=False)

        # Read any available output without blocking forever
        if proc.stdout:
            try:
                # Use wait_for with short timeout so we don't block
                chunk = await asyncio.wait_for(proc.stdout.read(8192), timeout=0.5)
                if chunk:
                    decoded = chunk.decode("utf-8", errors="replace")
                    self._terminal_output[terminal_id] += decoded
                    print(f"[terminal_output] read {len(decoded)} bytes", flush=True)
            except asyncio.TimeoutError:
                pass  # No output available right now
            except Exception as e:
                print(f"[terminal_output] read error: {e}", flush=True)

        return TerminalOutputResponse(
            output=self._terminal_output[terminal_id], truncated=False
        )

    async def wait_for_terminal_exit(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> WaitForTerminalExitResponse:
        proc = self._terminals.get(terminal_id)
        if not proc:
            return WaitForTerminalExitResponse(exit_code=1, signal=None)

        # Drain remaining output first
        if proc.stdout:
            try:
                while True:
                    chunk = await asyncio.wait_for(proc.stdout.read(8192), timeout=0.5)
                    if not chunk:
                        break
                    decoded = chunk.decode("utf-8", errors="replace")
                    self._terminal_output[terminal_id] += decoded
            except asyncio.TimeoutError:
                pass

        # Wait for process to exit
        await proc.wait()
        self._terminal_exit_code[terminal_id] = proc.returncode
        print(
            f"[wait_for_exit] terminal={terminal_id} exit_code={proc.returncode}",
            flush=True,
        )

        return WaitForTerminalExitResponse(exit_code=proc.returncode, signal=None)

    async def kill_terminal(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> KillTerminalCommandResponse | None:
        proc = self._terminals.get(terminal_id)
        if proc and proc.returncode is None:
            proc.kill()
            await proc.wait()
            print(f"[kill_terminal] terminal={terminal_id}", flush=True)
        return KillTerminalCommandResponse()

    async def release_terminal(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> ReleaseTerminalResponse | None:
        self._terminals.pop(terminal_id, None)
        self._terminal_output.pop(terminal_id, None)
        self._terminal_exit_code.pop(terminal_id, None)
        self._terminal_signal.pop(terminal_id, None)
        print(f"[release_terminal] terminal={terminal_id}", flush=True)
        return ReleaseTerminalResponse()

    # -- File system methods --

    async def read_text_file(
        self,
        path: str,
        session_id: str,
        limit: int | None = None,
        line: int | None = None,
        **kwargs: Any,
    ) -> ReadTextFileResponse:
        print(f"[read_text_file] path={path} limit={limit} line={line}", flush=True)
        content = Path(path).read_text()
        if limit:
            content = content[:limit]
        if line:
            lines = content.split("\n")
            if 0 < line <= len(lines):
                content = lines[line - 1]
        return ReadTextFileResponse(content=content)

    async def write_text_file(
        self, content: str, path: str, session_id: str, **kwargs: Any
    ) -> WriteTextFileResponse | None:
        print(f"[write_text_file] path={path} len={len(content)}", flush=True)
        Path(path).write_text(content)
        return WriteTextFileResponse()

    # -- Permission --

    async def request_permission(self, options, session_id, tool_call, **kwargs: Any):
        print(
            f"[request_permission] tool={tool_call.title if tool_call else 'unknown'}",
            flush=True,
        )
        if self._permission_auto_allow:
            return RequestPermissionResponse(outcome={"outcome": "auto_allow"})
        return RequestPermissionResponse(outcome={"outcome": "cancelled"})

    # -- Session updates --

    async def session_update(self, session_id, update, **kwargs: Any):
        update_type = getattr(update, "session_update", "unknown")
        if update_type == "agent_message_chunk":
            text = getattr(update, "content", None)
            if text and hasattr(text, "text"):
                print(text.text, end="", flush=True)
        elif update_type == "tool_call":
            print(
                f"\n[TOOL_CALL] {getattr(update, 'title', '')} ({getattr(update, 'status', '')})",
                flush=True,
            )
        elif update_type == "tool_call_update":
            status = getattr(update, "status", "")
            print(f"[TOOL_UPDATE] status={status}", flush=True)
        else:
            print(f"[UPDATE] type={update_type}", flush=True)


async def main():
    agent_path = (
        "/home/thomas/src/crow-ai/crow-cli/sandbox/agent-client/agent_client.py"
    )
    agent_dir = "/home/thomas/src/crow-ai/crow-cli/sandbox/agent-client"
    print(f"Testing agent-client: {agent_path}", flush=True)

    client = RealClient()

    async with spawn_agent_process(
        client,
        "uv",
        "--project",
        agent_dir,
        "run",
        agent_path,
        cwd=agent_dir,
    ) as (conn, proc):
        print(f"✓ spawned (PID: {proc.pid})", flush=True)

        # Initialize WITH capabilities so the child agent knows we support terminal+fs
        print("→ Initializing with terminal+fs capabilities...", flush=True)
        from acp.schema import ClientCapabilities, FileSystemCapability

        init_response = await conn.initialize(
            protocol_version=1,
            client_capabilities=ClientCapabilities(
                terminal=True,
                fs=FileSystemCapability(
                    read_text_file=True,
                    write_text_file=True,
                ),
            ),
        )
        print(f"✓ init: {init_response}", flush=True)

        print("→ Creating session...", flush=True)
        session = await conn.new_session(cwd=agent_dir, mcp_servers=[])
        print(f"✓ session: {session.session_id}", flush=True)

        # Test 1: Run date command (uses terminal/create)
        print("\n=== TEST 1: 'run the date command using terminal' ===", flush=True)
        print("→ Sending prompt...", flush=True)
        response = await conn.prompt(
            session_id=session.session_id,
            prompt=[text_block("run the date command using terminal")],
        )
        print(f"\n✓ response: {response}", flush=True)

        # Test 2: Read a file (uses fs/read_text_file)
        print("\n=== TEST 2: 'read the file README.md' ===", flush=True)
        response = await conn.prompt(
            session_id=session.session_id,
            prompt=[
                text_block(
                    "read the file README.md and tell me the first 200 characters"
                )
            ],
        )
        print(f"\n✓ response: {response}", flush=True)

        print("\n=== ALL TESTS PASSED ===", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
