"""``crow-cli acp2 --http`` — Streamable HTTP (integration — real CrowAgentV2, real hypercorn).

Mirrors v1's ``test_acp_http.py``: serves the real v2 agent on a free port and
drives the SDK's HTTP client through ``initialize``, ``session/new`` and
``session/close``, proving the ``AgentProtocolRouter`` negotiates v2 and routes
the v2 session lifecycle over SSE. No LLM calls: ``session/new`` only resolves
the model, it does not dial a provider.
"""

from __future__ import annotations

import asyncio
import socket
from pathlib import Path
from typing import Any

import pytest
import yaml

from acp.experimental import v2
from acp.http.client import create_http_stream

from crow_cli.agent2.main import serve_http
from crow_cli.config import Config


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _wait_port(port: int, timeout: float = 15.0) -> None:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.1)
    raise TimeoutError(f"server never came up on :{port}")


class _Client:
    """The client half. Only what the v2 runtime calls back into."""

    def __init__(self) -> None:
        self.updates: asyncio.Queue = asyncio.Queue()

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        await self.updates.put((session_id, update))


def _config(tmp_path: Path) -> Config:
    """A hermetic config dir with one model, so ``session/new`` can resolve it."""
    (tmp_path / ".env").write_text("API_KEY=not-a-real-key\n")
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "providers": {
                    "p": {
                        "api_key": "${API_KEY}",
                        "base_url": "https://acp2.invalid/v1",
                    }
                },
                "models": {"m": {"provider": "p", "model": "m-id"}},
            },
            sort_keys=False,
        )
    )
    config = Config.load(config_dir=tmp_path)
    config.db_uri = f"sqlite:///{tmp_path / 'crow.db'}"
    return config


@pytest.mark.asyncio
async def test_v2_initialize_new_session_close_over_http(tmp_path):
    port = _free_port()
    config = _config(tmp_path)

    server = asyncio.create_task(serve_http(config, "m", "127.0.0.1", port))
    try:
        await _wait_port(port)
        transport = create_http_stream(f"http://127.0.0.1:{port}/acp")
        client = _Client()
        conn = v2.connect_to_agent(client, transport)
        try:
            init = await asyncio.wait_for(
                conn.initialize(
                    protocol_version=v2.PROTOCOL_VERSION,
                    info=v2.schema.Implementation(name="acp2-http", version="1.0.0"),
                ),
                timeout=20,
            )
            assert init.protocol_version == v2.PROTOCOL_VERSION
            assert init.info.name == "crow-cli"

            new = await asyncio.wait_for(
                conn.new_session(cwd=str(tmp_path), mcp_servers=[]),
                timeout=20,
            )
            assert new.session_id

            picker = {o.config_id: o for o in (new.config_options or [])}["model"]
            assert picker.current_value == "p:m-id"

            # The first server->client notification is the available-commands
            # update, proving the router routes v2 session/update over SSE.
            sid, _update = await asyncio.wait_for(client.updates.get(), timeout=5)
            assert sid == new.session_id

            await asyncio.wait_for(conn.close_session(session_id=new.session_id), timeout=20)
        finally:
            await conn.close()
            await transport.close()
    finally:
        server.cancel()
        with pytest.raises(asyncio.CancelledError):
            await server
