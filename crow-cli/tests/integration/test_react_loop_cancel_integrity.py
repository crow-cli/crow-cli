"""
React-loop cancellation integrity (integration — REAL sqlite persistence).

Invariant under test: after ANY turn — including user-cancelled ones — every
tool_call_id in a persisted assistant message has a matching persisted tool
response. Cancelled turns answer with "Tool call cancelled by user".

No persistence mocking here: sessions are created through make_agent_session,
the react loop runs against a real test sqlite db, and assertions are made by
RELOADING the agent from the db — exactly what the next turn would see.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from types import SimpleNamespace

from mcp.types import TextContent

from crow_cli.config import Config
from crow_cli.agent.react import TOOL_CALL_CANCELLED_MESSAGE, react_loop
from crow_cli.agent.session import AgentSession, make_agent_session

logger = logging.getLogger(__name__)

SESSION_ID = "cancel-integrity-session"
AGENT_ID = f"{SESSION_ID}-1"
DB_NAME = "crow.db"


# ---------------------------------------------------------------------------
# Fake wire layer (LLM stream + ACP conn + MCP client). Persistence is REAL.
# ---------------------------------------------------------------------------


@dataclass
class MockDelta:
    reasoning_content: str | None = None
    content: str | None = None
    tool_calls: list | None = None


@dataclass
class MockChoice:
    delta: MockDelta
    finish_reason: str | None = None


@dataclass
class MockChunk:
    choices: list
    usage: object | None = None


def content_chunk(text: str) -> MockChunk:
    return MockChunk(choices=[MockChoice(delta=MockDelta(content=text))])


def tool_call_chunk(index: int, id=None, name=None, args=None) -> MockChunk:
    fn = SimpleNamespace(name=name, arguments=args)
    call = SimpleNamespace(index=index, id=id, function=fn)
    return MockChunk(choices=[MockChoice(delta=MockDelta(tool_calls=[call]))])


def usage_chunk(total_tokens: int = 100) -> MockChunk:
    usage = SimpleNamespace(
        prompt_tokens=total_tokens // 2,
        completion_tokens=total_tokens // 2,
        total_tokens=total_tokens,
    )
    return MockChunk(choices=[], usage=usage)


async def fake_stream(chunks: list, hang_after: bool = False):
    """Yield scripted chunks; when hang_after, block forever (until cancel)."""
    for chunk in chunks:
        yield chunk
    if hang_after:
        await asyncio.Event().wait()


class FakeLLM:
    def __init__(self, chunks: list, hang_after: bool = False):
        self.chunks = chunks
        self.hang_after = hang_after
        self.create_kwargs = None
        outer = self

        class Completions:
            async def create(self, **kwargs):
                outer.create_kwargs = kwargs
                return fake_stream(outer.chunks, outer.hang_after)

        class Chat:
            completions = Completions()

        self.chat = Chat()


class FakeConn:
    """ACP client surface — records updates, never fails."""

    def __init__(self):
        self.updates = []

    async def session_update(self, session_id, update):
        self.updates.append(update)


class FakeMCPClient:
    """MCP tool executor: returns a real result, or hangs simulating a
    long-running tool (e.g. a terminal command) until the turn is cancelled."""

    def __init__(self, hang_on_call: int = 1):
        self.hang_on_call = hang_on_call
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        if len(self.calls) >= self.hang_on_call:
            await asyncio.sleep(3600)  # long-running process; cancelled by test
        return SimpleNamespace(
            content=[TextContent(type="text", text=f"result-{len(self.calls)}")],
            isError=False,
        )


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


async def make_test_session(tmp_path) -> tuple[Config, AgentSession]:
    config = Config(config_dir=tmp_path)
    config.db_uri = f"sqlite:///{tmp_path / DB_NAME}"
    session = await make_agent_session(
        config,
        tools=[],
        model_id="test-model",
        cwd=str(tmp_path),
        session_id=SESSION_ID,
    )
    return config, session


async def drive_react_loop(gen) -> tuple[list, str]:
    """Consume react_loop; return (events, 'cancelled'|'done')."""
    events = []
    try:
        async for event in gen:
            events.append(event)
    except asyncio.CancelledError:
        return events, "cancelled"
    return events, "done"


async def wait_until(predicate, timeout: float = 5.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while not predicate():
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError("condition not met within timeout")
        await asyncio.sleep(0.01)


def assert_tool_call_response_invariant(messages: list[dict]):
    """THE invariant: every assistant tool_call_id is answered by a tool
    message before any other role speaks; no orphan tool responses."""
    pending: list[str] = []
    for msg in messages:
        role = msg.get("role")
        if role == "assistant":
            assert not pending, f"unanswered tool calls before new assistant msg: {pending}"
            pending = [tc["id"] for tc in msg.get("tool_calls") or []]
        elif role == "tool":
            tool_call_id = msg.get("tool_call_id")
            assert tool_call_id in pending, f"orphan tool response: {tool_call_id}"
            pending.remove(tool_call_id)
        else:
            assert not pending, f"unanswered tool calls before {role} msg: {pending}"
    assert not pending, f"unanswered tool calls at end of history: {pending}"


async def run_cancel_turn(
    tmp_path,
    llm: FakeLLM,
    mcp_clients: dict,
    state_accumulator: dict,
    cancel_when,
) -> AgentSession:
    """Run one react-loop turn, cancel it when cancel_when() is true, then
    RELOAD the session from the real db and return it."""
    config, session = await make_test_session(tmp_path)
    conn = FakeConn()
    gen = react_loop(
        conn=conn,
        config=config,
        client_capabilities=None,
        turn_id="turn-1",
        mcp_clients=mcp_clients,
        llm=llm,
        tools=[],
        sessions={AGENT_ID: session},
        agent_id=AGENT_ID,
        state_accumulators={SESSION_ID: state_accumulator},
        logger=logger,
        hooks=[],
    )
    task = asyncio.create_task(drive_react_loop(gen))
    await wait_until(cancel_when)
    task.cancel()
    events, stop = await task
    assert stop == "cancelled", f"expected cancelled turn, got {stop}: {events}"

    await session.close()
    return await AgentSession.load(AGENT_ID, memory_path=config.db_uri)


def tool_responses(messages: list[dict]) -> list[dict]:
    return [m for m in messages if m.get("role") == "tool"]


def assistant_tool_call_ids(messages: list[dict]) -> list[str]:
    ids = []
    for m in messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            ids.extend(tc["id"] for tc in m["tool_calls"])
    return ids


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_cancel_mid_stream_persists_cancelled_tool_responses(tmp_path):
    """User cancels while the stream is still open, AFTER the model emitted
    two complete tool calls. Both must be persisted WITH cancelled responses."""
    chunks = [
        content_chunk("Let me look into that. "),
        tool_call_chunk(0, id="call_alpha", name="search", args='{"query": '),
        tool_call_chunk(0, args='"cancellation"}'),
        tool_call_chunk(1, id="call_beta", name="web_fetch", args='{"url": "https://x.test"}'),
    ]
    llm = FakeLLM(chunks, hang_after=True)  # stream stays open until cancel
    acc = {"thinking": [], "content": [], "tool_calls": {}}

    loaded = await run_cancel_turn(
        tmp_path,
        llm=llm,
        mcp_clients={},
        state_accumulator=acc,
        cancel_when=lambda: len(acc["tool_calls"]) == 2,
    )

    messages = loaded.messages
    assert_tool_call_response_invariant(messages)
    assert sorted(assistant_tool_call_ids(messages)) == ["call_alpha", "call_beta"]
    responses = tool_responses(messages)
    assert len(responses) == 2
    assert {r["tool_call_id"] for r in responses} == {"call_alpha", "call_beta"}
    assert all(r["content"] == TOOL_CALL_CANCELLED_MESSAGE for r in responses)


async def test_cancel_during_tool_execution_persists_cancelled_responses(tmp_path):
    """Stream finished, tool execution is in flight (long-running MCP call).
    Cancel must persist the assistant tool_calls + cancelled responses."""
    chunks = [
        tool_call_chunk(0, id="call_one", name="slow_tool", args='{"command": "sleep 999"}'),
        tool_call_chunk(1, id="call_two", name="slow_tool", args='{"command": "sleep 998"}'),
        usage_chunk(),
    ]
    llm = FakeLLM(chunks)
    mcp = FakeMCPClient(hang_on_call=1)  # first tool hangs, second never starts
    acc = {"thinking": [], "content": [], "tool_calls": {}}

    loaded = await run_cancel_turn(
        tmp_path,
        llm=llm,
        mcp_clients={SESSION_ID: mcp},
        state_accumulator=acc,
        cancel_when=lambda: len(mcp.calls) == 1,
    )

    messages = loaded.messages
    assert_tool_call_response_invariant(messages)
    assert sorted(assistant_tool_call_ids(messages)) == ["call_one", "call_two"]
    responses = {r["tool_call_id"]: r["content"] for r in tool_responses(messages)}
    assert responses == {
        "call_one": TOOL_CALL_CANCELLED_MESSAGE,
        "call_two": TOOL_CALL_CANCELLED_MESSAGE,
    }


async def test_cancel_during_second_tool_keeps_first_result(tmp_path):
    """First tool completed, cancel lands during the second. The completed
    result must persist as-is; only the interrupted call gets the cancelled
    response."""
    chunks = [
        tool_call_chunk(0, id="call_fast", name="quick_tool", args="{}"),
        tool_call_chunk(1, id="call_slow", name="slow_tool", args="{}"),
        usage_chunk(),
    ]
    llm = FakeLLM(chunks)
    mcp = FakeMCPClient(hang_on_call=2)  # first returns, second hangs
    acc = {"thinking": [], "content": [], "tool_calls": {}}

    loaded = await run_cancel_turn(
        tmp_path,
        llm=llm,
        mcp_clients={SESSION_ID: mcp},
        state_accumulator=acc,
        cancel_when=lambda: len(mcp.calls) == 2,
    )

    messages = loaded.messages
    assert_tool_call_response_invariant(messages)
    responses = {r["tool_call_id"]: r["content"] for r in tool_responses(messages)}
    assert set(responses) == {"call_fast", "call_slow"}
    assert "result-1" in str(responses["call_fast"])
    assert responses["call_slow"] == TOOL_CALL_CANCELLED_MESSAGE
