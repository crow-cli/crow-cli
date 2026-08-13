"""
React-loop tool rounds, usage updates, and compaction (integration — REAL
sqlite persistence).

The cancel-integrity module covers cancelled turns; this module covers the
HAPPY paths through the whole loop:

- a multi-turn tool round trip: streamed tool_call chunks -> MCP execution ->
  follow-up turn, with the full persisted history reloaded from the db;
- usage_update reaching the ACP client (and the loop surviving a dead one);
- compaction wiring when total_tokens crosses MAX_COMPACT_TOKENS.

Shared fakes (FakeConn, FakeLLM, chunk builders, make_test_session, ...) are
imported from test_react_loop_cancel_integrity — one set of wire fakes.
"""

import logging
from types import SimpleNamespace

from acp.schema import UsageUpdate

from crow_cli.agent.react import react_loop
from crow_cli.agent.session import AgentSession

from tests.integration.test_react_loop_cancel_integrity import (
    AGENT_ID,
    SESSION_ID,
    FakeConn,
    assert_tool_call_response_invariant,
    content_chunk,
    drive_react_loop,
    fake_stream,
    make_test_session,
    tool_call_chunk,
    usage_chunk,
)

logger = logging.getLogger(__name__)


class MultiTurnLLM:
    """Pops one scripted response per create() call.

    Entries are either a list of stream chunks (served as an async stream,
    like react_loop's send_request) or a plain string (served as a
    non-streaming completion, like compact()'s summarization call).
    """

    def __init__(self, script: list):
        self.script = list(script)
        self.create_kwargs: list[dict] = []
        outer = self

        class Completions:
            async def create(self, **kwargs):
                outer.create_kwargs.append(kwargs)
                entry = outer.script.pop(0)
                if isinstance(entry, str):
                    return SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                message=SimpleNamespace(content=entry)
                            )
                        ],
                        usage=None,
                    )
                return fake_stream(entry)

        class Chat:
            completions = Completions()

        self.chat = Chat()


async def run_turn(tmp_path, llm, mcp_clients=None, conn=None, max_compact=None):
    """One react_loop turn on a fresh session; returns
    (config, session, conn, events, stop)."""
    config, session = await make_test_session(tmp_path)
    if max_compact is not None:
        config.MAX_COMPACT_TOKENS = max_compact
    conn = conn or FakeConn()
    gen = react_loop(
        conn=conn,
        config=config,
        client_capabilities=None,
        turn_id="turn-1",
        mcp_clients=mcp_clients or {},
        llm=llm,
        tools=[],
        sessions={AGENT_ID: session},
        agent_id=AGENT_ID,
        state_accumulators={},
        logger=logger,
        hooks=[],
    )
    events, stop = await drive_react_loop(gen)
    return config, session, conn, events, stop


class NeverHangMCP:
    """MCP client that always returns immediately."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name, args):
        from mcp.types import TextContent

        self.calls.append((name, args))
        return SimpleNamespace(
            content=[TextContent(type="text", text=f"result-{len(self.calls)}")],
            isError=False,
        )


# ---------------------------------------------------------------------------
# Tool round trip
# ---------------------------------------------------------------------------


async def test_tool_round_trip_persists_full_history(tmp_path):
    """Turn 1 streams a tool call (id+name, then args in fragments), the MCP
    client executes it, turn 2 answers with final content. The reloaded db
    history must be [system, user, assistant(tool_calls), tool, assistant]."""
    config, session = await make_test_session(tmp_path)
    await session.add_message({"role": "user", "content": "search for cancellation"})

    turn1 = [
        content_chunk("Let me search. "),
        tool_call_chunk(0, id="call_search", name="search", args='{"que'),
        tool_call_chunk(0, args='ry": "cancellation"}'),
        usage_chunk(40),
    ]
    turn2 = [content_chunk("The answer is 42."), usage_chunk(20)]
    llm = MultiTurnLLM([turn1, turn2])
    mcp = NeverHangMCP()
    conn = FakeConn()

    gen = react_loop(
        conn=conn,
        config=config,
        client_capabilities=None,
        turn_id="turn-1",
        mcp_clients={SESSION_ID: mcp},
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

    # MCP received the reassembled, parsed arguments
    assert mcp.calls == [("search", {"query": "cancellation"})]

    # Reload from the REAL db — what the next turn would see
    await session.close()
    loaded = await AgentSession.load(AGENT_ID, memory_path=config.db_uri)
    messages = loaded.messages
    assert [m["role"] for m in messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert_tool_call_response_invariant(messages)

    assistant_tc = messages[2]
    assert assistant_tc["tool_calls"][0]["id"] == "call_search"
    assert assistant_tc["tool_calls"][0]["function"]["name"] == "search"

    tool_msg = messages[3]
    assert tool_msg["tool_call_id"] == "call_search"
    assert "result-1" in str(tool_msg["content"])

    assert "The answer is 42." in str(messages[4]["content"])

    # Loop ends with exactly one final_history carrying the full history
    finals = [e for e in events if e["type"] == "final_history"]
    assert len(finals) == 1
    assert len(finals[0]["messages"]) == 5


# ---------------------------------------------------------------------------
# usage_update
# ---------------------------------------------------------------------------


async def test_usage_update_reaches_client(tmp_path):
    """A turn with usage emits a UsageUpdate (used/size) to the ACP client."""
    llm = MultiTurnLLM([[content_chunk("hello"), usage_chunk(123)]])
    config, session, conn, events, stop = await run_turn(tmp_path, llm)
    assert stop == "done"
    await session.close()

    updates = [u for u in conn.updates if isinstance(u, UsageUpdate)]
    assert len(updates) == 1
    assert updates[0].used == 123
    assert updates[0].size == config.MAX_COMPACT_TOKENS


class ThrowingConn(FakeConn):
    """Dead client: every session_update blows up. The react loop must treat
    usage_update as best-effort and still finish the turn."""

    async def session_update(self, session_id, update):
        raise RuntimeError("client gone away")


async def test_loop_survives_dead_client_on_usage_update(tmp_path):
    llm = MultiTurnLLM([[content_chunk("still here"), usage_chunk(500)]])
    config, session, conn, events, stop = await run_turn(
        tmp_path, llm, conn=ThrowingConn()
    )
    assert stop == "done", events
    assert any(e["type"] == "final_history" for e in events)

    await session.close()
    loaded = await AgentSession.load(AGENT_ID, memory_path=config.db_uri)
    assert "still here" in str(loaded.messages[-1]["content"])


# ---------------------------------------------------------------------------
# Compaction wiring
# ---------------------------------------------------------------------------


async def test_compaction_crossing_threshold_creates_new_agent(tmp_path):
    """usage.total_tokens > MAX_COMPACT_TOKENS triggers compaction: a
    'compaction' event, a non-streaming summarization call, a NEW agent
    (idx+1) holding summary + continuation, and the old agent untouched."""
    config, session = await make_test_session(tmp_path)
    await session.add_message({"role": "user", "content": "do the big job"})

    llm = MultiTurnLLM(
        [
            [content_chunk("working on it "), usage_chunk(100)],  # turn 1: over 50
            "SUMMARY of the big job",  # compact() summarization (non-stream)
            [content_chunk("done now"), usage_chunk(10)],  # turn 2: under 50
        ]
    )
    config.MAX_COMPACT_TOKENS = 50
    conn = FakeConn()
    gen = react_loop(
        conn=conn,
        config=config,
        client_capabilities=None,
        turn_id="turn-1",
        mcp_clients={},
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

    # One stream per turn plus the non-streaming summarization
    assert len(llm.create_kwargs) == 3
    assert "stream" not in llm.create_kwargs[1] or not llm.create_kwargs[1].get(
        "stream"
    )

    # The loop announced compaction
    assert any(e["type"] == "compaction" for e in events)

    # New agent (idx 2) holds the summary prompt and the final answer
    new_id = f"{SESSION_ID}-2"
    loaded_new = await AgentSession.load(new_id, memory_path=config.db_uri)
    new_text = " ".join(str(m.get("content")) for m in loaded_new.messages)
    assert "SUMMARY of the big job" in new_text
    assert "done now" in new_text
    assert [m["role"] for m in loaded_new.messages] == [
        "system",
        "user",
        "assistant",
    ]

    # Old agent untouched — still just system + user
    loaded_old = await AgentSession.load(AGENT_ID, memory_path=config.db_uri)
    assert [m["role"] for m in loaded_old.messages] == ["system", "user"]

    # final_history came from the NEW session
    finals = [e for e in events if e["type"] == "final_history"]
    assert len(finals) == 1
    assert "done now" in " ".join(
        str(m.get("content")) for m in finals[0]["messages"]
    )

    await session.close()
