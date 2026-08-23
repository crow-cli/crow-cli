"""EXPERIMENT: subagent completes while the parent is still mid-turn.

The parent is told to (1) delegate a trivially fast task — a subagent
calling `date` via terminal — and then (2) keep itself busy investigating
crow-cli via web search. The subagent finishes in seconds, long before the
parent's web-search turns do. This test records EVERY session_update that
crosses the wire, timestamped, so we can see what the current machinery
does with a completion that arrives mid-turn: does it get enmeshed with
the parent's in-flight work, parked, dropped, injected?

Assertions are deliberately loose — the recorded timeline is the point.
"""

import asyncio
import logging
import socket
import time
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
    "do two things. first delegate a subagent to call date with terminal "
    "(this is a test) and then investigate crow-cli via web search please sir"
)
MCP_SERVERS = [
    {
        "name": "crow-mcp",
        "transport": "stdio",
        "command": "uv",
        "args": [
            "--project",
            "/home/thomas/src/crow-team/crow-cli",
            "run",
            "crow-cli",
            "mcp",
        ],
    }
]


class RecordingClient(Client):
    def __init__(self):
        self.t0 = time.monotonic()
        self.updates: list[tuple[float, Any]] = []

    async def request_permission(self, *a: Any, **k: Any) -> Any:
        raise NotImplementedError

    async def session_update(self, session_id: str, update: Any) -> None:
        self.updates.append((time.monotonic() - self.t0, update))

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


def _describe(update: Any) -> str:
    kind = getattr(update, "session_update", None)
    bits = [f"{kind}"]
    tcid = getattr(update, "tool_call_id", None)
    if tcid:
        bits.append(f"id={tcid}")
    status = getattr(update, "status", None)
    if status:
        bits.append(f"status={getattr(status, 'value', status)}")
    content = getattr(update, "content", None)
    if content is not None:
        text = getattr(content, "text", None)
        if text:
            bits.append(f"text={text[:60]!r}")
    chunk = getattr(update, "chunk", None)
    if chunk is not None:
        text = getattr(chunk, "text", None)
        if text:
            bits.append(f"chunk={text[:40]!r}")
    return " ".join(bits)


@pytest.mark.asyncio
async def test_subagent_finishes_while_parent_mid_turn(tmp_path):
    if not _provider_available():
        pytest.skip(f"{MODEL} / its provider is not configured")

    config = Config.load()
    config.db_uri = f"sqlite:///{tmp_path / 'e2e.db'}"

    port = _free_port()
    server = asyncio.create_task(serve_http(config, MODEL, "127.0.0.1", port))
    client = RecordingClient()
    stop_reason = None
    try:
        await _wait_port(port)
        transport = create_http_stream(f"http://127.0.0.1:{port}/acp")
        conn = connect_to_agent(client, transport)
        try:
            await conn.initialize(protocol_version=1)
            ns = await conn.new_session(cwd=str(tmp_path), mcp_servers=MCP_SERVERS)
            resp = await asyncio.wait_for(
                conn.prompt(session_id=ns.session_id, prompt=[text_block(DIRECTIVE)]),
                timeout=420,
            )
            stop_reason = resp.stop_reason
        finally:
            await conn.close()
            await transport.close()
    finally:
        server.cancel()

    # ------------------------------------------------------------------ dump
    print(f"\n=== TIMELINE ({len(client.updates)} wire events) ===")
    for t, u in client.updates:
        print(f"[{t:7.2f}s] {_describe(u)}")
    print(f"=== stop_reason: {stop_reason} ===")

    tool_ids = []
    for _, u in client.updates:
        if getattr(u, "session_update", None) in ("tool_call", "tool_call_update"):
            tcid = getattr(u, "tool_call_id", None)
            if tcid and tcid not in tool_ids:
                tool_ids.append(tcid)
    print(f"=== tool surfaces seen: {tool_ids} ===")

    # Loose: the turn ended and the model really delegated.
    assert stop_reason == "end_turn", f"turn ended {stop_reason!r}"
    assert any("/task-" in i for i in tool_ids), f"no delegate surface in {tool_ids}"
