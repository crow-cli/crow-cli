"""Integration: the react loop routes tool_name == 'execute' through
execute_acp_execute into the REAL MCP execute tool (a persistent IPython
kernel subprocess).

Scripted LLM (deterministic tool calls) + real kernel + real sqlite
persistence. Proves, without a live model:
- the dispatch branch (react.py) sends 'execute' to execute_acp_execute;
- the _meta injection (session id + cwd) keys the kernel per session;
- kernel STATE persists across two separate tool rounds — the second call
  reads a variable the first call set.
"""

import logging

import pytest
from fastmcp import Client

from crow_cli.agent.react import react_loop
from crow_cli.agent.session import AgentSession

from tests.integration.test_react_loop_cancel_integrity import (
    AGENT_ID,
    SESSION_ID,
    FakeConn,
    content_chunk,
    drive_react_loop,
    make_test_session,
    tool_call_chunk,
    usage_chunk,
)
from tests.integration.test_react_loop_tool_round import MultiTurnLLM

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _cleanup_kernels():
    """Never leak a kernel subprocess; never bleed state across tests."""
    yield
    from crow_cli.mcp.execute.main import shutdown_all

    shutdown_all()


async def test_execute_dispatch_persists_state_across_rounds(tmp_path):
    from crow_cli.mcp.server.app import mcp

    import crow_cli.mcp.execute.main  # noqa: F401 — registers the tool

    config, session = await make_test_session(tmp_path)
    await session.add_message(
        {"role": "user", "content": "compute 6*7 and show it"}
    )

    # Round 1 sets a variable; round 2 reads it back — only possible if the
    # SAME kernel survived between rounds. Round 3 is the final answer.
    turn1 = [
        tool_call_chunk(
            0, id="call_e1", name="execute", args='{"code": "total = 6 * 7"}'
        ),
        usage_chunk(30),
    ]
    turn2 = [
        tool_call_chunk(
            0, id="call_e2", name="execute", args='{"code": "print(total)"}'
        ),
        usage_chunk(30),
    ]
    turn3 = [content_chunk("The total is 42."), usage_chunk(10)]
    llm = MultiTurnLLM([turn1, turn2, turn3])
    conn = FakeConn()

    async with Client(mcp) as mcp_client:
        gen = react_loop(
            conn=conn,
            config=config,
            client_capabilities=None,
            turn_id="turn-1",
            mcp_clients={SESSION_ID: mcp_client},
            llm=llm,
            tools=[],
            sessions={AGENT_ID: session},
            agent_id=AGENT_ID,
            state_accumulators={},
            logger=logger,
            hooks=[],
        )
        events, stop = await drive_react_loop(gen)

    assert stop == "done", events

    # Reload from the REAL db — exactly what the next turn would see.
    await session.close()
    loaded = await AgentSession.load(AGENT_ID, memory_path=config.db_uri)
    messages = loaded.messages

    # Both execute calls were dispatched and answered.
    tool_msgs = [m for m in messages if m["role"] == "tool"]
    assert len(tool_msgs) == 2, [m.get("role") for m in messages]

    # The first call (assignment) produced no value; the second read the
    # persisted variable. print(total) -> "42".
    assert "42" in str(tool_msgs[1]["content"]), tool_msgs[1]

    # Final answer landed.
    assert "42" in str(messages[-1]["content"])


async def test_execute_meta_injects_session_and_cwd(tmp_path):
    """execute_acp_execute rides the session id AND cwd on the call meta —
    injected by the harness, never the model — so the kernel is keyed per
    session and starts in the session's working directory."""
    from crow_cli.mcp.server.app import mcp

    import crow_cli.mcp.execute.main  # noqa: F401

    from crow_cli.agent.tools import execute_acp_execute

    config, session = await make_test_session(tmp_path)

    captured = {}

    class SpyMCP:
        async def call_tool(self, name, args, meta=None):
            from mcp.types import TextContent
            from types import SimpleNamespace

            captured["name"] = name
            captured["args"] = args
            captured["meta"] = meta
            return SimpleNamespace(
                content=[TextContent(type="text", text="7")], isError=False
            )

    from crow_cli.agent.context import TurnCtx

    ctx = TurnCtx(
        conn=FakeConn(),
        config=config,
        session=session,
        turn_id="turn-meta",
        logger=logger,
    )
    await execute_acp_execute(
        ctx, {SESSION_ID: SpyMCP()}, "call_x", {"code": "1 + 6"}
    )

    assert captured["name"] == "execute"
    assert captured["args"] == {"code": "1 + 6"}
    assert captured["meta"] == {
        "cwd": str(tmp_path),
        "session_id": SESSION_ID,
        "tool_call_id": "turn-meta/call_x",
        "db_uri": config.db_uri,
    }
    await session.close()
