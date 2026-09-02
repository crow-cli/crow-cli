# /// script
# requires-python = ">=3.10,<3.15"
# dependencies = [
#     "agent-client-protocol",
# ]
# ///
"""Load-blast ACP agent: reproduces cancel-under-streaming-load.

A real ACP agent (python-sdk, stdio) whose `session/prompt` floods the client
with `session/update` notifications as fast as the transport allows. Used to
reproduce and verify cancellation while the client's message pump is saturated.

Modelled on python-sdk's `examples/echo_agent.py`, with the production agent's
capability advertisement (`load_session=True`).

Tuning (environment):
    CROW_MOCK_CHUNKS        number of agent_message_chunk updates (default 20000)
    CROW_MOCK_CHUNK_CHARS   characters per chunk (default 40)
    CROW_MOCK_TOKENS_PER_SEC  pace the stream to a realistic fast endpoint; 0 =
                            flat out (default 0). One chunk is treated as a token.
    CROW_MOCK_DELAY_MS      fixed sleep between chunks, ms (default 0)
    CROW_MOCK_IGNORE_CANCEL ignore session/cancel and stream to the end
    CROW_MOCK_LOG           append diagnostics (chunk counts, cancel arrival) here

Run standalone: `python mock_acp_agent.py` (it speaks ACP on stdio).
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any
from uuid import uuid4

from acp import (
    Agent,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
    run_agent,
    text_block,
    update_agent_message,
)
from acp.interfaces import Client
from acp.schema import (
    AgentCapabilities,
    HttpMcpServer,
    McpServerStdio,
    SseMcpServer,
)


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _diag(line: str) -> None:
    """Append a diagnostics line, if CROW_MOCK_LOG is set."""
    path = os.environ.get("CROW_MOCK_LOG")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"{time.monotonic():.6f} {line}\n")
    except OSError:
        pass


class LoadBlastAgent(Agent):
    """Streams a configurable torrent of agent_message_chunk updates."""

    _conn: Client

    def __init__(self) -> None:
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._streamed = 0

    def on_connect(self, conn: Client) -> None:
        self._conn = conn

    def _event(self, session_id: str) -> asyncio.Event:
        return self._cancel_events.setdefault(session_id, asyncio.Event())

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: Any = None,
        client_info: Any = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        _diag("initialize")
        return InitializeResponse(
            protocol_version=protocol_version,
            agent_capabilities=AgentCapabilities(load_session=True),
        )

    async def new_session(
        self,
        cwd: str,
        additional_directories: list[str] | None = None,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        **kwargs: Any,
    ) -> NewSessionResponse:
        _diag(f"new_session cwd={cwd}")
        return NewSessionResponse(session_id=uuid4().hex)

    async def load_session(
        self,
        cwd: str,
        session_id: str,
        additional_directories: list[str] | None = None,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        **kwargs: Any,
    ) -> Any:
        _diag(f"load_session session_id={session_id}")
        return None

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        """session/cancel lands here (notification, routed by the SDK)."""
        _diag(f"cancel RECEIVED after {self._streamed} chunks")
        self._event(session_id).set()

    async def prompt(self, session_id: str, prompt: list[Any], **kwargs: Any) -> PromptResponse:
        chunks = _env_int("CROW_MOCK_CHUNKS", 20_000)
        chunk_chars = _env_int("CROW_MOCK_CHUNK_CHARS", 40)
        delay_s = _env_int("CROW_MOCK_DELAY_MS", 0) / 1000.0
        tokens_per_sec = _env_int("CROW_MOCK_TOKENS_PER_SEC", 0)
        ignore_cancel = os.environ.get("CROW_MOCK_IGNORE_CANCEL") == "1"

        cancelled = self._event(session_id)
        cancelled.clear()
        self._streamed = 0
        body = "x" * max(1, chunk_chars)

        _diag(
            f"prompt start chunks={chunks} chars={chunk_chars} "
            f"delay_ms={delay_s * 1000} tokens_per_sec={tokens_per_sec}"
        )
        started = time.monotonic()
        for index in range(chunks):
            if not ignore_cancel and cancelled.is_set():
                elapsed = time.monotonic() - started
                _diag(f"prompt stopped early: {self._streamed} chunks in {elapsed:.3f}s")
                return PromptResponse(stop_reason="cancelled")

            await self._conn.session_update(
                session_id=session_id,
                update=update_agent_message(text_block(body)),
            )
            self._streamed += 1

            # Pace against wall-clock so the stream holds its rate rather than
            # drifting with per-chunk overhead.
            if tokens_per_sec:
                due = started + (index + 1) / tokens_per_sec
                remaining = due - time.monotonic()
                if remaining > 0:
                    await asyncio.sleep(remaining)
            elif delay_s:
                await asyncio.sleep(delay_s)

        _diag(f"prompt completed: {self._streamed} chunks")
        return PromptResponse(stop_reason="end_turn")


async def main() -> None:
    await run_agent(LoadBlastAgent())


if __name__ == "__main__":
    asyncio.run(main())
