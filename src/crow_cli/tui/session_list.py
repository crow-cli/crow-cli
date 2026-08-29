"""Standalone ACP `session/list` over stdio NDJSON.

Spawns the agent, performs the `initialize` handshake, issues `session/list`,
and tears the connection down. Runs its own `jsonrpc.API` instance so it
never interferes with the app's live agent connection.
"""

import asyncio
import json
import os
from pathlib import Path

import crow_cli.tui as tui
from crow_cli.tui import jsonrpc
from crow_cli.tui.acp import protocol
from crow_cli.tui.acp.agent import PROTOCOL_VERSION
from crow_cli.tui.agent_schema import Agent as AgentData

LIST_API = jsonrpc.API()


@LIST_API.method()
def initialize(
    protocolVersion: int,
    clientCapabilities: protocol.ClientCapabilities,
    clientInfo: protocol.Implementation,
) -> protocol.InitializeResponse:
    """https://agentclientprotocol.com/protocol/v1/initialization"""
    ...


@LIST_API.method(name="session/list")
def session_list(
    cwd: str | None = None, cursor: str | None = None
) -> protocol.ListSessionsResponse:
    """https://agentclientprotocol.com/protocol/v1/session-list"""
    ...


class SessionListError(Exception):
    """The session/list exchange failed."""


async def list_sessions(
    agent_data: AgentData,
    cwd: str | Path,
    *,
    timeout: float = 30.0,
) -> list[protocol.SessionInfo]:
    """Return the sessions for `cwd` reported by the agent over ACP.

    Args:
        agent_data: The agent to spawn (run_command matrix).
        cwd: Working directory to list sessions for (exact match agent-side).
        timeout: Seconds before the whole exchange is abandoned.

    Raises:
        SessionListError: If the agent cannot be spawned, does not support
            session/list, or does not answer.
    """
    command = tui.get_os_matrix(agent_data["run_command"])
    if command is None:
        raise SessionListError("No run command for this OS")

    cwd_path = str(Path(cwd).resolve().absolute())
    PIPE = asyncio.subprocess.PIPE
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdin=PIPE,
            stdout=PIPE,
            stderr=PIPE,
            env=os.environ.copy(),
            cwd=cwd_path,
            limit=10 * 1024 * 1024,
        )
    except OSError as error:
        raise SessionListError(f"Failed to start agent: {error}")

    assert process.stdin is not None
    assert process.stdout is not None

    def send(request: jsonrpc.Request) -> None:
        if process.stdin is not None:
            process.stdin.write(b"%s\n" % request.body_json)

    async def read_loop() -> None:
        while line := await process.stdout.readline():
            if not line.strip():
                continue
            try:
                data = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(data, dict) and ("result" in data or "error" in data):
                LIST_API.process_response(data)

    loop_task = asyncio.create_task(read_loop())

    async def transact() -> list[protocol.SessionInfo]:
        with LIST_API.request(send):
            init_call = initialize(
                PROTOCOL_VERSION,
                {
                    "fs": {
                        "readTextFile": True,
                        "writeTextFile": True,
                    },
                    "terminal": True,
                },
                {
                    "name": tui.NAME,
                    "title": tui.TITLE,
                    "version": tui.get_version(),
                },
            )
        init_response = await init_call.wait()
        if init_response is None:
            raise SessionListError("No initialize response from agent")

        session_capabilities = init_response.get("agentCapabilities", {}).get(
            "sessionCapabilities", {}
        )
        if "list" not in session_capabilities:
            raise SessionListError("Agent does not support session/list")

        with LIST_API.request(send):
            list_call = session_list(cwd=cwd_path)
        list_response = await list_call.wait()
        if list_response is None:
            raise SessionListError("No session/list response from agent")
        return list_response.get("sessions", [])

    try:
        async with asyncio.timeout(timeout):
            return await transact()
    except TimeoutError:
        raise SessionListError("Timed out waiting for the agent")
    finally:
        loop_task.cancel()
        try:
            process.terminate()
        except OSError:
            pass
