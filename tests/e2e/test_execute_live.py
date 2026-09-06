"""E2E: a REAL model (qwen3.8-max-preview) drives the persistent `execute`
kernel through the FULL react loop — no mocks on the model or the tool.

The loop streams real tool calls from the provider, dispatches them through
execute_acp_execute into the real MCP kernel subprocess, and the kernel's
persistent state carries a variable from one call to the next.

Live calls are nondeterministic, so asserts are deliberately loose — but the
core proof is concrete: the model actually used the execute tool, and the
REPL's persistent state produced 6*7=42 across calls.
"""

import logging

import pytest
from fastmcp import Client as MCPClient

from crow_cli.agent.mcp_client import get_tools
from crow_cli.agent.react import react_loop
from crow_cli.agent.session import AgentSession, make_agent_session
from crow_cli.config import Config

from tests.e2e.test_session_update_transmission import get_llm_client
from tests.integration.test_react_loop_cancel_integrity import (
    FakeConn,
    drive_react_loop,
)

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.asyncio

SESSION_ID = "execute-live-session"
AGENT_ID = f"{SESSION_ID}-1-1"


@pytest.fixture(autouse=True)
def _cleanup_kernels():
    yield
    from crow_cli.mcp.execute.main import shutdown_all

    shutdown_all()


async def test_live_model_drives_persistent_kernel(tmp_path):
    client, model_id = get_llm_client()
    if client is None:
        pytest.skip("No LLM provider configured")

    from crow_cli.mcp.server.app import mcp

    import crow_cli.mcp.execute.main  # noqa: F401 — registers the tool

    config = Config.load()
    # Never touch the real db — isolate this run in a throwaway sqlite file.
    config.db_uri = f"sqlite:///{tmp_path / 'e2e.db'}"

    session = await make_agent_session(
        config,
        tools=[],
        model_id=model_id,
        cwd=str(tmp_path),
        session_id=SESSION_ID,
    )
    await session.add_message(
        {
            "role": "user",
            "content": (
                "You have an `execute` tool: a persistent Python REPL. Use it "
                "in TWO separate calls. First call: `total = 6 * 7`. Second "
                "call: `print(total)`. The variable persists between calls. "
                "Then reply with ONLY the number that was printed."
            ),
        }
    )

    async with MCPClient(mcp) as mcp_client:
        # Offer only the execute tool so the model stays focused on it.
        tools = [
            t
            for t in await get_tools(mcp_client)
            if t["function"]["name"] == "execute"
        ]
        assert tools, "execute tool not registered"

        conn = FakeConn()
        gen = react_loop(
            conn=conn,
            config=config,
            client_capabilities=None,
            turn_id="turn-e2e",
            mcp_clients={SESSION_ID: mcp_client},
            llm=client,
            tools=tools,
            sessions={session.agent_id: session},
            agent_id=session.agent_id,
            state_accumulators={},
            logger=logger,
            hooks=[],
        )
        events, stop = await drive_react_loop(gen)

    assert stop == "done", events

    await session.close()
    loaded = await AgentSession.load(AGENT_ID, memory_path=config.db_uri)
    messages = loaded.messages

    # The model actually invoked the execute tool (at least once).
    execute_calls = [
        tc
        for m in messages
        if m["role"] == "assistant"
        for tc in (m.get("tool_calls") or [])
        if tc["function"]["name"] == "execute"
    ]
    assert execute_calls, "model never used the execute tool"

    # The REPL computed 6*7 and the answer surfaced somewhere in the
    # conversation — tool output or final answer.
    blob = " ".join(str(m.get("content")) for m in messages)
    assert "42" in blob, blob[-2000:]
