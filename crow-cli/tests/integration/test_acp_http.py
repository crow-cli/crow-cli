"""ACP over Streamable HTTP (integration — real AcpAgent, real hypercorn).

Serves the real agent on a free port and drives the SDK's HTTP client
through initialize, proving the --http transport wiring end-to-end. No LLM
calls: initialize only (new_session would spawn MCP servers).
"""

import asyncio
import socket
from typing import Any

import pytest

from acp import connect_to_agent
from acp.http import create_http_stream
from acp.interfaces import Client

from crow_cli.config import Config
from crow_cli.agent.main import serve_http


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _wait_port(port: int, timeout: float = 10.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.1)
    raise TimeoutError(f"server never came up on :{port}")


class MinimalClient(Client):
    async def request_permission(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    async def session_update(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def write_text_file(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def read_text_file(self, *args: Any, **kwargs: Any) -> Any:
        return {"content": ""}


@pytest.mark.asyncio
async def test_initialize_over_http(tmp_path):
    port = _free_port()
    config = Config(config_dir=tmp_path)
    config.db_uri = f"sqlite:///{tmp_path / 'crow.db'}"

    server = asyncio.create_task(serve_http(config, None, "127.0.0.1", port))
    try:
        await _wait_port(port)
        transport = create_http_stream(f"http://127.0.0.1:{port}/acp")
        conn = connect_to_agent(MinimalClient(), transport)
        try:
            init = await conn.initialize(protocol_version=1)
            assert init.protocol_version == 1
        finally:
            await conn.close()
            await transport.close()
    finally:
        server.cancel()
        with pytest.raises(asyncio.CancelledError):
            await server
