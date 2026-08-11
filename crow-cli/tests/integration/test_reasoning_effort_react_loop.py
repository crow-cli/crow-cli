"""
reasoning_effort through the WHOLE react loop (integration — real sqlite).

Unit tests cover parse + send_request in isolation. Here we drive a complete
turn end-to-end and assert the exact params the loop hands the LLM client:
when config.reasoning_effort is set the request carries reasoning_effort and
OMITS temperature; when unset it carries temperature as before.
"""

import logging

from crow_cli.agent.configure import Config
from crow_cli.agent.react import react_loop
from crow_cli.agent.session import AgentSession

from tests.integration.test_react_loop_cancel_integrity import (
    SESSION_ID,
    AGENT_ID,
    DB_NAME,
    FakeConn,
    FakeLLM,
    content_chunk,
    make_test_session,
    usage_chunk,
)

logger = logging.getLogger(__name__)


async def run_full_turn(tmp_path, reasoning_effort: str | None) -> dict:
    """Run one react-loop turn to natural completion; return the LLM create
    kwargs captured on the wire, after reloading the session from the db."""
    config, session = await make_test_session(tmp_path)
    config.reasoning_effort = reasoning_effort

    chunks = [
        content_chunk("Here is a plain answer, no tools needed."),
        usage_chunk(),
    ]
    llm = FakeLLM(chunks)
    conn = FakeConn()
    acc = {"thinking": [], "content": [], "tool_calls": {}}

    gen = react_loop(
        conn=conn,
        config=config,
        client_capabilities=None,
        turn_id="turn-re",
        mcp_clients={},
        llm=llm,
        tools=[],
        sessions={AGENT_ID: session},
        agent_id=AGENT_ID,
        state_accumulators={SESSION_ID: acc},
        logger=logger,
        hooks=[],
    )

    events = [event async for event in gen]
    assert any(e.get("type") == "final_history" for e in events)

    # The assistant reply really landed in the db
    await session.close()
    loaded = await AgentSession.load(AGENT_ID, memory_path=config.memory_path)
    assert any(
        m.get("role") == "assistant" and "plain answer" in str(m.get("content"))
        for m in loaded.messages
    )

    return llm.create_kwargs


async def test_react_loop_sends_reasoning_effort_not_temperature(tmp_path):
    kwargs = await run_full_turn(tmp_path, reasoning_effort="high")
    assert kwargs["reasoning_effort"] == "high"
    assert "temperature" not in kwargs


async def test_react_loop_sends_temperature_when_unset(tmp_path):
    kwargs = await run_full_turn(tmp_path, reasoning_effort=None)
    assert "reasoning_effort" not in kwargs
    assert kwargs["temperature"] == Config.TEMPERATURE
