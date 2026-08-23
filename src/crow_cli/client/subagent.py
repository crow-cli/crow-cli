"""Headless ACP client that drives one subagent subprocess.

The client-side half of the task system: pure ACP orchestration — spawn
a child crow agent, handshake, session/new, session/prompt,
session/cancel, teardown. No sqlite, no tool knowledge: the MCP-side
`task` tool owns state and lifecycle, this is the driver it uses.

Split rationale: ACP is the client<->agent contract, so the machinery
that talks to an agent lives in the client package; MCP is the
agent<->tool contract, so the tool + state coupling lives in the mcp
package. The two couple through sqlite, never in-process.
"""

import asyncio
import contextlib
import sys
from pathlib import Path
from typing import Any

from acp import PROTOCOL_VERSION, RequestError, connect_to_agent, text_block
from acp.interfaces import Client
from acp.schema import ClientCapabilities, Implementation, PromptResponse


async def spawn_agent_process(
    cwd: str,
    config_dir: Path | None = None,
    model: str | None = None,
    config_file: Path | None = None,
) -> asyncio.subprocess.Process:
    """Spawn a crow agent subprocess (frozen builds: the `acp` subcommand).

    The child loads its OWN config in its own process — config dir/file
    are forwarded so the whole stack (db_uri, providers) routes the same.
    """
    is_frozen = getattr(sys, "frozen", False)
    dir_args = ["--config-dir", str(config_dir)] if config_dir else []
    if config_file:
        dir_args += ["--config-file", str(config_file)]
    model_args = ["--model", model] if model else []
    if is_frozen:
        argv = [sys.executable, "acp", *dir_args, *model_args]
    else:
        argv = [sys.executable, "-m", "crow_cli.agent.main", *dir_args, *model_args]
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    if proc.stdin is None or proc.stdout is None:
        raise RuntimeError("agent subprocess does not expose stdio pipes")
    return proc


class HeadlessClient(Client):
    """The client face shown to a subagent: swallow updates, no fs/pty.

    The child's transcript is fully observable through the shared sqlite
    (query_session on its session id) — nothing needs forwarding, and
    terminal=False at handshake makes its terminal tool fall through to
    its own MCP supply.
    """

    def __init__(self) -> None:
        self.updates: list[Any] = []

    async def request_permission(self, *a: Any, **k: Any) -> Any:
        raise RequestError.method_not_found("session/request_permission")

    async def session_update(self, session_id: str, update: Any, **k: Any) -> None:
        self.updates.append(update)

    async def write_text_file(self, *a: Any, **k: Any) -> Any:
        raise RequestError.method_not_found("fs/write_text_file")

    async def read_text_file(self, *a: Any, **k: Any) -> Any:
        raise RequestError.method_not_found("fs/read_text_file")


class SubagentDriver:
    """Drives ONE subagent over ACP: spawn -> handshake -> sessions."""

    def __init__(self) -> None:
        self.proc: asyncio.subprocess.Process | None = None
        self.conn: Any = None
        self.client = HeadlessClient()

    async def start(
        self,
        cwd: str,
        model: str | None = None,
        config_dir: Path | None = None,
    ) -> None:
        self.proc = await spawn_agent_process(cwd, config_dir=config_dir, model=model)
        self.conn = connect_to_agent(
            self.client,
            self.proc.stdin,
            self.proc.stdout,
            # session/fork is UNSTABLE — both ends opt in or the router
            # answers method_not_found.
            use_unstable_protocol=True,
        )
        await self.conn.initialize(
            protocol_version=PROTOCOL_VERSION,
            # terminal=False: the child's terminal tool falls through to
            # its MCP supply (agent-owned execution), not to us.
            client_capabilities=ClientCapabilities(terminal=False),
            client_info=Implementation(
                name="crow-task", title="Crow Task", version="0.1.0"
            ),
        )

    async def new_session(self, cwd: str, mcp_servers: list | None = None) -> str:
        ns = await self.conn.new_session(cwd=cwd, mcp_servers=mcp_servers or [])
        return ns.session_id

    async def load_session(
        self, session_id: str, cwd: str, mcp_servers: list | None = None
    ) -> None:
        """Re-attach to an existing session (re-prompt after its turn
        ended). The agent restores state from sqlite; no history is
        emitted back to us."""
        await self.conn.load_session(
            cwd=cwd, session_id=session_id, mcp_servers=mcp_servers or []
        )

    async def prompt(self, session_id: str, text: str) -> PromptResponse:
        return await self.conn.prompt(
            session_id=session_id, prompt=[text_block(text)]
        )

    async def cancel(self, session_id: str) -> None:
        await self.conn.cancel(session_id=session_id)

    async def close(self) -> None:
        with contextlib.suppress(Exception):
            if self.conn is not None:
                await self.conn.close()
        if self.proc is not None and self.proc.returncode is None:
            with contextlib.suppress(Exception):
                self.proc.terminate()
                await asyncio.wait_for(self.proc.wait(), timeout=5)
            if self.proc.returncode is None:
                with contextlib.suppress(Exception):
                    self.proc.kill()
