"""Native delegate tool — Milestone A (blocking delegation).

execute_delegate runs a REAL subagent AgentSession against a real tmp
sqlite db; a scripted LLM stands in for the provider. Verifies launch,
result shape, persistence, registry bookkeeping and cancel propagation.
"""

import asyncio
import logging
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from crow_cli.agent import delegate as delegate_mod
from crow_cli.agent.delegate import (
    DELEGATE_TOOL,
    _last_assistant_text,
    execute_delegate,
)
from crow_cli.agent.session import AgentSession, lookup_or_create_prompt
from crow_cli.agent.tasks import TaskRegistry
from crow_cli.config import Config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Chunk fakes (same shape as test_react.py)
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


def usage_chunk(total_tokens: int = 100) -> MockChunk:
    usage = SimpleNamespace(
        prompt_tokens=total_tokens // 2,
        completion_tokens=total_tokens // 2,
        total_tokens=total_tokens,
    )
    return MockChunk(choices=[], usage=usage)


async def fake_stream(chunks: list, hang_after: bool = False):
    for chunk in chunks:
        yield chunk
    if hang_after:
        await asyncio.Event().wait()


class ScriptedLLM:
    """chat.completions.create plays a script of chunk-lists."""

    def __init__(self, script: list):
        self.script = list(script)
        outer = self

        class Completions:
            async def create(self, **kwargs):
                return fake_stream(outer.script.pop(0))

        class Chat:
            completions = Completions()

        self.chat = Chat()


class FakeConn:
    def __init__(self):
        self.updates = []

    async def session_update(self, session_id, update):
        self.updates.append((session_id, update))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def delegate_env(tmp_path, monkeypatch):
    """Real config redirected to a tmp db; a parent session to delegate from."""
    config = Config.load()
    config.db_uri = f"sqlite:///{tmp_path / 'delegate.db'}"
    config.system_prompt_path = None
    config.system_prompt = "You are a worker."

    prompt_id = await lookup_or_create_prompt(
        "Parent prompt.", name="parent", memory_path=config.db_uri
    )
    parent = await AgentSession.create(
        prompt_id=prompt_id,
        prompt_args={},
        tool_definitions=[],
        request_params={},
        model_identifier="test-model",
        memory_path=config.db_uri,
        cwd="/tmp",
        session_id="parent-sess",
    )
    return config, parent


def _patch_llm(monkeypatch, script):
    llm = ScriptedLLM(script)
    monkeypatch.setattr(delegate_mod, "configure_llm", lambda **kw: llm)
    return llm


# ---------------------------------------------------------------------------
# _last_assistant_text
# ---------------------------------------------------------------------------


def test_last_assistant_text_string():
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "first"},
        {"role": "user", "content": "more"},
        {"role": "assistant", "content": "last"},
    ]
    assert _last_assistant_text(msgs) == "last"


def test_last_assistant_text_blocks():
    msgs = [
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "block answer"}],
        }
    ]
    assert _last_assistant_text(msgs) == "block answer"


def test_last_assistant_text_skips_tool_calls_only():
    msgs = [
        {"role": "assistant", "content": "real answer"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c"}]},
    ]
    assert _last_assistant_text(msgs) == "real answer"


def test_last_assistant_text_none():
    assert "no final answer" in _last_assistant_text([{"role": "user", "content": "x"}])


# ---------------------------------------------------------------------------
# execute_delegate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delegate_returns_subagent_answer(delegate_env, monkeypatch):
    config, parent = delegate_env
    _patch_llm(monkeypatch, [[content_chunk("SUBAGENT-ANSWER"), usage_chunk(100)]])
    registry = TaskRegistry()
    conn = FakeConn()

    result = await execute_delegate(
        conn=conn,
        parent_session=parent,
        turn_id="t1",
        tool_call_id="call-1",
        acp_tool_call_id="t1/call-1",
        args={"prompt": "do the thing"},
        config=config,
        mcp_servers=None,
        registry=registry,
        logger=logger,
    )

    assert "SUBAGENT-ANSWER" in result
    assert "finished" in result
    # registry: launched AND finished
    assert registry.pending() == []
    (task,) = [t for t in registry._tasks.values()]
    assert task.status == "done"
    assert task.owner_session == "parent-sess"
    # client surface: in_progress then completed on the PARENT's tool call
    statuses = [
        getattr(u, "status", None) for _, u in conn.updates
    ]
    assert "in_progress" in statuses and "completed" in statuses
    assert all(getattr(u, "tool_call_id", "") == "t1/call-1" for _, u in conn.updates)


@pytest.mark.asyncio
async def test_delegate_subagent_persisted(delegate_env, monkeypatch):
    """The subagent is a real session in the shared db — query_session food."""
    config, parent = delegate_env
    _patch_llm(monkeypatch, [[content_chunk("persisted-answer"), usage_chunk(100)]])

    result = await execute_delegate(
        conn=FakeConn(),
        parent_session=parent,
        turn_id="t1",
        tool_call_id="call-1",
        acp_tool_call_id="t1/call-1",
        args={"prompt": "do the thing"},
        config=config,
        mcp_servers=None,
        registry=TaskRegistry(),
        logger=logger,
    )

    # "[delegate <session-id> finished]" — load that session's trunk agent
    sub_session_id = result.split("[delegate ")[1].split(" finished]")[0]
    sub = await AgentSession.load(
        f"{sub_session_id}-1-1", memory_path=config.db_uri
    )
    roles = [m["role"] for m in sub.messages]
    assert roles == ["system", "user", "assistant"]
    assert sub.messages[1]["content"] == "do the thing"
    assert sub.messages[2]["content"] == "persisted-answer"
    await sub.close()


@pytest.mark.asyncio
async def test_delegate_tool_schema_exposed(delegate_env):
    """The delegate tool is a native tool: sessions get it even with zero
    MCP servers (client passed none)."""
    config, parent = delegate_env
    assert DELEGATE_TOOL["function"]["name"] == "delegate"
    assert "prompt" in DELEGATE_TOOL["function"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_delegate_requires_prompt(delegate_env):
    config, parent = delegate_env
    result = await execute_delegate(
        conn=FakeConn(),
        parent_session=parent,
        turn_id="t1",
        tool_call_id="c",
        acp_tool_call_id="t1/c",
        args={},
        config=config,
        mcp_servers=None,
        registry=TaskRegistry(),
        logger=logger,
    )
    assert result.startswith("Error:")


@pytest.mark.asyncio
async def test_parallel_delegate_calls_run_concurrently(monkeypatch, delegate_env):
    """Two delegate calls in ONE assistant message overlap in time
    (asyncio.gather in execute_tool_calls)."""
    config, parent = delegate_env
    from crow_cli.agent import react as react_mod

    running = 0
    max_running = 0

    async def fake_execute_delegate(**kwargs):
        nonlocal running, max_running
        running += 1
        max_running = max(max_running, running)
        await asyncio.sleep(0.05)
        running -= 1
        return "[delegate sub finished]\nok"

    monkeypatch.setattr(react_mod, "execute_delegate", fake_execute_delegate)
    tool_call_inputs = [
        {"id": "c1", "function": {"name": "delegate", "arguments": '{"prompt": "a"}'}},
        {"id": "c2", "function": {"name": "delegate", "arguments": '{"prompt": "b"}'}},
    ]
    results = []
    await react_mod.execute_tool_calls(
        conn=FakeConn(),
        client_capabilities=None,
        turn_id="t",
        config=config,
        mcp_clients={},
        sessions={parent.agent_id: parent},
        agent_id=parent.agent_id,
        tool_call_inputs=tool_call_inputs,
        logger=logger,
        hooks=[],
        tool_results=results,
        registry=TaskRegistry(),
    )
    assert max_running == 2  # actually overlapped
    assert {r["tool_call_id"] for r in results} == {"c1", "c2"}
    assert all(r["role"] == "tool" for r in results)


@pytest.mark.asyncio
async def test_delegate_unavailable_without_registry(monkeypatch, delegate_env):
    """A delegate call where no registry is wired gets an error result, not a
    crash (keeps hermetic react tests safe)."""
    config, parent = delegate_env
    from crow_cli.agent import react as react_mod

    tool_call_inputs = [
        {"id": "c1", "function": {"name": "delegate", "arguments": '{"prompt": "a"}'}},
    ]
    results = []
    await react_mod.execute_tool_calls(
        conn=FakeConn(),
        client_capabilities=None,
        turn_id="t",
        config=config,
        mcp_clients={},
        sessions={parent.agent_id: parent},
        agent_id=parent.agent_id,
        tool_call_inputs=tool_call_inputs,
        logger=logger,
        hooks=[],
        tool_results=results,
        registry=None,
    )
    assert len(results) == 1
    assert "not available" in results[0]["content"]


@pytest.mark.asyncio
async def test_delegate_cancel_propagates(delegate_env, monkeypatch):
    """Cancellation of the awaiting task reaches the subagent's react loop;
    the registry records the cancellation (cancel tree, milestone A)."""
    config, parent = delegate_env

    # Stream one chunk, then hang forever — the delegate is mid-flight.
    async def create(**kwargs):
        return fake_stream([content_chunk("partial ")], hang_after=True)

    hanging_llm = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(delegate_mod, "configure_llm", lambda **kw: hanging_llm)
    registry = TaskRegistry()

    task = asyncio.create_task(
        execute_delegate(
            conn=FakeConn(),
            parent_session=parent,
            turn_id="t1",
            tool_call_id="call-1",
            acp_tool_call_id="t1/call-1",
            args={"prompt": "long task"},
            config=config,
            mcp_servers=None,
            registry=registry,
            logger=logger,
        )
    )
    # Wait for the subagent to register, then cancel the whole stack.
    for _ in range(100):
        if registry.pending():
            break
        await asyncio.sleep(0.01)
    assert registry.pending(), "delegate never registered"

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    (info,) = [t for t in registry._tasks.values()]
    assert info.status == "cancelled"
