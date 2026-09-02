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

from crow_cli.config import LLModel, LLMProvider
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

    Script entries are plain strings — the text the model "says" — and are
    served the way the caller asked for it: as a stream of content chunks when
    ``stream=True`` (react_loop's send_request AND compact()'s summarization
    call), as a single completion object otherwise.
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
                    if kwargs.get("stream"):
                        return fake_stream([content_chunk(entry)])
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


class MetaCapturingMCP:
    """Captures call_tool kwargs — the task channel rides the call meta."""

    def __init__(self):
        self.calls: list[tuple[str, dict, dict | None]] = []

    async def call_tool(self, name, args, meta=None):
        from mcp.types import TextContent

        self.calls.append((name, args, meta))
        return SimpleNamespace(
            content=[TextContent(type="text", text="launched task-1")],
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


async def test_task_tool_call_injects_session_meta(tmp_path):
    """The react loop intercepts tool_name == 'task' (execute_acp_task):
    the LLM's args pass through unchanged, and the calling session's wire
    id rides the call meta — attribution injected by the harness, never
    the model, never the environment."""
    config, session = await make_test_session(tmp_path)
    await session.add_message({"role": "user", "content": "launch a subagent"})

    turn1 = [
        tool_call_chunk(
            0,
            id="call_task",
            name="task",
            args='{"updates": [{"action": "prompt", "prompt": "do it"}]}',
        ),
        usage_chunk(30),
    ]
    turn2 = [content_chunk("Launched."), usage_chunk(10)]
    llm = MultiTurnLLM([turn1, turn2])
    mcp = MetaCapturingMCP()
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

    # The task tool got the LLM's args untouched + the owner in the meta
    assert len(mcp.calls) == 1
    name, args, meta = mcp.calls[0]
    assert name == "task"
    assert args == {"updates": [{"action": "prompt", "prompt": "do it"}]}
    assert meta == {"session_id": SESSION_ID}


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
    'compaction' event, a streamed summarization call, a NEW agent
    (idx+1) holding summary + continuation, and the old agent untouched."""
    config, session = await make_test_session(tmp_path)
    await session.add_message({"role": "user", "content": "do the big job"})

    llm = MultiTurnLLM(
        [
            [content_chunk("working on it "), usage_chunk(100)],  # turn 1: over 50
            "SUMMARY of the big job",  # compact() summarization (streamed)
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

    # One request per turn plus the compaction summarization — which, like every
    # other LLM call, must be streamed (a local model needs minutes to produce a
    # whole summary; unstreamed it trips the client's read timeout).
    assert len(llm.create_kwargs) == 3
    assert llm.create_kwargs[1].get("stream") is True

    # The loop announced compaction
    assert any(e["type"] == "compaction" for e in events)

    # New agent (idx 2) holds the summary prompt and the final answer
    new_id = f"{SESSION_ID}-2-1"  # v5: next agent_idx, same fork_idx
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


async def test_per_model_compact_threshold_overrides_global(tmp_path):
    """A model with max_compact_tokens compacts at its OWN threshold, not
    the global MAX_COMPACT_TOKENS (which stays the subscription-API rate),
    and the usage_update meter measures against the per-model value too."""
    config, session = await make_test_session(tmp_path)
    await session.add_message({"role": "user", "content": "do the big job"})

    # Global stays high; the session's model ("test-model") carries a low
    # ceiling of its own — the local-model case.
    config.MAX_COMPACT_TOKENS = 1000
    config.llm.providers["p"] = LLMProvider(name="p")
    config.llm.models["local"] = LLModel(
        name="local",
        provider_name="p",
        model_id="test-model",
        max_compact_tokens=50,
    )

    llm = MultiTurnLLM(
        [
            [content_chunk("working on it "), usage_chunk(100)],  # >50, <1000
            "SUMMARY of the big job",  # compact() summarization (streamed)
            [content_chunk("done now"), usage_chunk(10)],
        ]
    )
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

    # Compaction fired at the per-model threshold even though usage (100)
    # is far below the global one (1000) — and announced the right number.
    compactions = [e for e in events if e["type"] == "compaction"]
    assert len(compactions) == 1
    assert "50" in compactions[0]["token"]

    # Context meter measures against the per-model threshold
    updates = [u for u in conn.updates if isinstance(u, UsageUpdate)]
    assert updates[0].used == 100
    assert updates[0].size == 50

    # The new agent holds the summary, as in the global-threshold case
    new_id = f"{SESSION_ID}-2-1"  # v5: next agent_idx, same fork_idx
    loaded_new = await AgentSession.load(new_id, memory_path=config.db_uri)
    new_text = " ".join(str(m.get("content")) for m in loaded_new.messages)
    assert "SUMMARY of the big job" in new_text
    assert "done now" in new_text

    # final_history came from the NEW session
    finals = [e for e in events if e["type"] == "final_history"]
    assert len(finals) == 1
    assert "done now" in " ".join(
        str(m.get("content")) for m in finals[0]["messages"]
    )

    await session.close()


# ---------------------------------------------------------------------------
# Task deliveries — the loop CONSULTS STATE at its breakpoints
# ---------------------------------------------------------------------------


async def test_prompt_start_drains_idle_mailbox(tmp_path):
    """A delivery that landed while the session was QUIESCENT is injected
    BEFORE the first model call — the prompt starts already knowing its
    task finished (the resume path — queued replies enter only via a user
    prompt; nothing self-wakes)."""
    from crow_cli.memory import get_engine, pending_deliveries
    from crow_cli.memory.writes import finish_task, launch_task

    config, session = await make_test_session(tmp_path)
    await session.add_message(
        {"role": "user", "content": "check on the background task"}
    )

    engine = get_engine(config.db_uri)
    launch_task(engine, task_id="task-1", owner_session=SESSION_ID)
    finish_task(
        engine,
        "task-1",
        result="42",
        content="[task-1: subagent shy-fox finished]\n42",
    )

    llm = MultiTurnLLM(
        [[content_chunk("My background task returned 42."), usage_chunk(10)]]
    )
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

    # The model's FIRST request already carried the delivery as a user
    # message — injected before any model call.
    first_user_texts = [
        str(m.get("content"))
        for m in llm.create_kwargs[0]["messages"]
        if m["role"] == "user"
    ]
    assert any("task-1" in t for t in first_user_texts), first_user_texts

    # The client saw the injection as a user_message_chunk.
    assert any(
        getattr(u, "session_update", None) == "user_message_chunk"
        for u in conn.updates
    )

    # Mailbox drained; the delivery persists in history.
    assert pending_deliveries(engine, SESSION_ID) == []
    assert any(
        m["role"] == "user" and "task-1" in str(m.get("content"))
        for m in session.messages
    )
    await session.close()


class DeliveryLandingMCP:
    """Executing the tool lands a LOW-priority delivery — a fast child
    finishing while the parent's batch is still running."""

    def __init__(self, db_uri: str):
        self.db_uri = db_uri

    async def call_tool(self, name, args):
        from mcp.types import TextContent

        from crow_cli.memory import get_engine
        from crow_cli.memory.writes import finish_task, launch_task

        engine = get_engine(self.db_uri)
        launch_task(engine, task_id="task-1", owner_session=SESSION_ID)
        finish_task(
            engine,
            "task-1",
            result="done",
            content="[task-1: subagent shy-fox finished]\ndone",
        )
        return SimpleNamespace(
            content=[TextContent(type="text", text="work done")], isError=False
        )


async def test_low_delivery_held_to_end_of_turn(tmp_path):
    """A low-priority completion lands mid-turn: the between-batch
    consult takes HIGHS ONLY so it is held, the model's next no-tool
    answer reaches the end-turn consult, which injects it and keeps the
    turn going for one reaction round."""
    from crow_cli.memory import get_engine, pending_deliveries

    config, session = await make_test_session(tmp_path)
    await session.add_message(
        {"role": "user", "content": "work while the child runs"}
    )

    turn1 = [
        tool_call_chunk(0, id="call_work", name="work", args="{}"),
        usage_chunk(30),
    ]
    turn2 = [content_chunk("Still working."), usage_chunk(10)]
    turn3 = [content_chunk("Child finished; wrapping up."), usage_chunk(10)]
    llm = MultiTurnLLM([turn1, turn2, turn3])
    mcp = DeliveryLandingMCP(config.db_uri)
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

    # Three model rounds: tool batch -> held delivery -> reaction.
    assert len(llm.create_kwargs) == 3

    # The held delivery was NOT visible to turn 2 (lows wait for
    # end-turn), but IS in turn 3's request as a user message.
    second_user_texts = [
        str(m.get("content"))
        for m in llm.create_kwargs[1]["messages"]
        if m["role"] == "user"
    ]
    assert not any("task-1" in t for t in second_user_texts)
    third_user_texts = [
        str(m.get("content"))
        for m in llm.create_kwargs[2]["messages"]
        if m["role"] == "user"
    ]
    assert any("task-1" in t for t in third_user_texts), third_user_texts

    # Drained exactly once.
    engine = get_engine(config.db_uri)
    assert pending_deliveries(engine, SESSION_ID) == []
    await session.close()
