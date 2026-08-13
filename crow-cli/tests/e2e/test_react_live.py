"""
Live react-loop smoke test (end-to-end, real provider, real sqlite).

Drives the FULL react_loop — session creation, send_request against the real
provider, stream processing, persistence, final_history — with zero fakes.
Nondeterministic by nature, so asserts are deliberately loose. Opt-in e2e
tier: live calls cost money and take time.
"""

import logging

import pytest

from crow_cli.agent.configure import Config
from crow_cli.agent.react import react_loop
from crow_cli.agent.session import make_agent_session

from tests.e2e.test_session_update_transmission import get_llm_client
from tests.integration.test_react_loop_cancel_integrity import (
    FakeConn,
    drive_react_loop,
)

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_live_react_loop_single_turn(tmp_path):
    """One real turn through the loop: user message in, persisted assistant
    answer and a final_history event out."""
    client, model_id = get_llm_client()
    if client is None:
        pytest.skip("No LLM provider configured")

    config = Config.load()
    # Never touch the real db — isolate this run in a throwaway sqlite file
    config.db_uri = f"sqlite:///{tmp_path / 'e2e.db'}"

    session = await make_agent_session(
        config,
        tools=[],
        model_id=model_id,
        cwd=str(tmp_path),
    )
    await session.add_message(
        {
            "role": "user",
            "content": "Reply with exactly one short sentence. No tools needed.",
        }
    )

    conn = FakeConn()
    gen = react_loop(
        conn=conn,
        config=config,
        client_capabilities=None,
        turn_id="turn-e2e",
        mcp_clients={},
        llm=client,
        tools=[],
        sessions={session.agent_id: session},
        agent_id=session.agent_id,
        state_accumulators={},
        logger=logger,
        hooks=[],
    )
    events, stop = await drive_react_loop(gen)
    assert stop == "done", events

    finals = [e for e in events if e["type"] == "final_history"]
    assert len(finals) == 1
    messages = finals[0]["messages"]
    assert messages[-1]["role"] == "assistant"
    assert str(messages[-1].get("content") or "").strip(), "empty final answer"

    # Token events actually streamed to the client
    assert any(e["type"] == "content" for e in events)

    await session.close()
