"""TRUE end-to-end delegate test: real agent over the wire, real client.

Serves the REAL AcpAgent over Streamable HTTP and drives the SDK's real
ClientSideConnection through initialize -> new_session -> prompt, exactly like
a real client. The client records every session_update that arrives OVER THE
WIRE and we assert the Bug-1 contract: every delegate tool_call_id reaches the
client with a tool_call CREATION event before any tool_call_update (so a client
can never render "tool call not found"), and that the delegate's injected
completion is surfaced to the client.

Runs on every pytest invocation (live LLM calls). Uses the alibaba provider's
qwen3.8-max-preview; the default llamacpp host may be down.
"""

import asyncio
import logging
import socket
from pathlib import Path
from typing import Any

import pytest

from acp import connect_to_agent, text_block
from acp.http import create_http_stream
from acp.interfaces import Client

from crow_cli.agent.main import serve_http
from crow_cli.config import Config

logger = logging.getLogger(__name__)

MODEL = "qwen3.8-max-preview"
DIRECTIVE = (
    "Use the delegate tool RIGHT NOW to delegate this exact task to a subagent: "
    "'Reply with exactly the single word PINEAPPLE'. Do not answer it yourself. "
    "After the delegate's result arrives, reply with exactly GOT-<that word>."
)


class RecordingClient(Client):
    def __init__(self):
        self.updates = []

    async def request_permission(self, *a: Any, **k: Any) -> Any:
        raise NotImplementedError

    async def session_update(self, session_id: str, update: Any) -> None:
        self.updates.append(update)

    async def write_text_file(self, *a: Any, **k: Any) -> None:
        return None

    async def read_text_file(self, *a: Any, **k: Any) -> Any:
        return {"content": ""}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _wait_port(port: int, timeout: float = 15.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            r, w = await asyncio.open_connection("127.0.0.1", port)
            w.close()
            await w.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.1)
    raise TimeoutError("server never came up")


def _provider_available() -> bool:
    try:
        config = Config.load()
        model = config.llm.models.get(MODEL)
        if model is None:
            return False
        return config.llm.providers.get(model.provider_name) is not None
    except Exception:
        return False


@pytest.mark.asyncio
async def test_delegate_end_to_end_over_http(tmp_path):
    if not _provider_available():
        pytest.skip(f"{MODEL} / its provider is not configured")

    config = Config.load()
    config.db_uri = f"sqlite:///{tmp_path / 'e2e.db'}"

    port = _free_port()
    server = asyncio.create_task(serve_http(config, MODEL, "127.0.0.1", port))
    client = RecordingClient()
    try:
        await _wait_port(port)
        transport = create_http_stream(f"http://127.0.0.1:{port}/acp")
        conn = connect_to_agent(client, transport)
        try:
            await conn.initialize(protocol_version=1)
            ns = await conn.new_session(cwd=str(tmp_path), mcp_servers=[])
            resp = await asyncio.wait_for(
                conn.prompt(session_id=ns.session_id, prompt=[text_block(DIRECTIVE)]),
                timeout=240,
            )
            assert resp.stop_reason == "end_turn"
        finally:
            await conn.close()
            await transport.close()
    finally:
        server.cancel()

    tool_events = [
        u
        for u in client.updates
        if getattr(u, "session_update", None) in ("tool_call", "tool_call_update")
    ]
    assert tool_events, "the client saw no tool-call events at all"

    # The model really delegated: a per-task surface (<turn>/task-N) exists.
    ids = []
    for u in tool_events:
        tcid = getattr(u, "tool_call_id", None)
        if tcid and tcid not in ids:
            ids.append(tcid)
    assert any("/task-" in i for i in ids), f"no delegate task surface in {ids}"

    # Wire contract: for EVERY tool_call_id the first event is a tool_call
    # creation and everything after is tool_call_update.
    for tcid in ids:
        evs = [u for u in tool_events if getattr(u, "tool_call_id", None) == tcid]
        assert getattr(evs[0], "session_update", None) == "tool_call", (
            f"{tcid}: first event must be a tool_call creation, got "
            f"{getattr(evs[0], 'session_update', None)!r}"
        )
        assert all(
            getattr(u, "session_update", None) == "tool_call_update" for u in evs[1:]
        ), f"{tcid}: events after creation must be tool_call_update"

    # The delegate's injected completion reached the client.
    injected = [
        u
        for u in client.updates
        if getattr(u, "session_update", None) == "user_message_chunk"
        and "task-" in str(getattr(getattr(u, "content", None), "text", ""))
    ]
    assert injected, "the delegate completion was never surfaced to the client"
