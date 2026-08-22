"""Native delegate tool — Milestone B (park/wake, non-blocking delegation).

launch_delegate provisions a REAL subagent AgentSession against a real tmp
sqlite db and launches it as a background task; scripted LLMs stand in for
the provider. Verifies launch-ack semantics, background completion, the
react loop's park/wake cycle (zero-token park, synthetic-message injection,
heartbeats), the drain path (completion lands before the park), parallel
delegates, and the cancel tree.
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
    launch_delegate,
    synthetic_completion_message,
)
from crow_cli.agent.session import AgentSession, lookup_or_create_prompt
from crow_cli.agent.tasks import TaskInfo, TaskRegistry
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


def tool_call_chunk(index: int, call_id: str, name: str, arguments: str) -> MockChunk:
    call = SimpleNamespace(
        index=index,
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )
    return MockChunk(choices=[MockChoice(delta=MockDelta(tool_calls=[call]))])


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
    """chat.completions.create plays a script of chunk-lists.

    With repeat_last=True an exhausted script replays its final entry —
    useful when the number of park/wake cycles is timing-dependent.
    """

    def __init__(self, script: list, repeat_last: bool = False):
        self.script = list(script)
        self.repeat_last = repeat_last
        self._last = None
        outer = self

        class Completions:
            async def create(self, **kwargs):
                if outer.script:
                    outer._last = outer.script.pop(0)
                    entry = outer._last
                elif outer.repeat_last and outer._last is not None:
                    entry = outer._last
                else:
                    raise AssertionError("ScriptedLLM exhausted")
                return fake_stream(list(entry))

        class Chat:
            completions = Completions()

        self.chat = Chat()


class FakeConn:
    def __init__(self):
        self.updates = []

    async def session_update(self, session_id, update):
        self.updates.append((session_id, update))

    def tool_updates(self, tool_call_id):
        return [
            u
            for _, u in self.updates
            if getattr(u, "tool_call_id", None) == tool_call_id
        ]


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


def _patch_subagent_llm(monkeypatch, llm):
    monkeypatch.setattr(delegate_mod, "configure_llm", lambda **kw: llm)
    return llm


def _delegate_call(prompt="do the thing", call_id="call-1"):
    return tool_call_chunk(
        0, call_id, "delegate", '{"prompt": "%s"}' % prompt
    )


# ---------------------------------------------------------------------------
# _last_assistant_text / synthetic_completion_message
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


def test_synthetic_completion_message_shapes():
    done = TaskInfo("task-1", "delegate", "s", "c", sub_session="sub-1",
                    status="done", result="the answer")
    failed = TaskInfo("task-2", "delegate", "s", "c", sub_session="sub-2",
                      status="failed", result="boom")
    cancelled = TaskInfo("task-3", "delegate", "s", "c", sub_session="sub-3",
                         status="cancelled")
    assert synthetic_completion_message(done) == (
        "[task-1: delegate sub-1 finished]\nthe answer"
    )
    assert synthetic_completion_message(failed) == (
        "[task-2: delegate sub-2 failed]\nboom"
    )
    assert synthetic_completion_message(cancelled) == "[task-3: delegate sub-3 cancelled]"


# ---------------------------------------------------------------------------
# launch_delegate — non-blocking semantics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_launch_returns_ack_immediately(delegate_env, monkeypatch):
    """The tool result is the launch ack; the subagent runs in the
    background and lands on the wake queue when done."""
    config, parent = delegate_env
    release = asyncio.Event()

    async def create(**kwargs):
        await release.wait()
        return fake_stream([content_chunk("SUBAGENT-ANSWER"), usage_chunk(100)])

    _patch_subagent_llm(
        monkeypatch,
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
    )
    registry = TaskRegistry()
    conn = FakeConn()

    result = await launch_delegate(
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

    # Non-blocking: the ack returns while the subagent is still running.
    assert result.startswith("Launched task-1:")
    (info,) = registry.pending("parent-sess")
    assert info.status == "running"
    assert info.handle is not None

    # The launch call's client surface completed; the per-task surface is
    # in_progress and stays alive until the subagent finishes.
    assert [getattr(u, "status", None) for u in conn.tool_updates("t1/call-1")] == [
        "completed"
    ]
    assert [getattr(u, "status", None) for u in conn.tool_updates("t1/task-1")] == [
        "in_progress"
    ]

    release.set()
    await info.handle
    assert registry.pending() == []
    assert registry.get(info.task_id).status == "done"
    assert registry.get(info.task_id).result == "SUBAGENT-ANSWER"
    # completion landed on the wake queue
    assert registry.wake_queue("parent-sess").get_nowait() is registry.get(info.task_id)
    # per-task surface flipped to completed
    assert [getattr(u, "status", None) for u in conn.tool_updates("t1/task-1")] == [
        "in_progress",
        "completed",
    ]


@pytest.mark.asyncio
async def test_delegate_subagent_persisted(delegate_env, monkeypatch):
    """The subagent is a real session in the shared db — query_session food."""
    config, parent = delegate_env
    _patch_subagent_llm(
        monkeypatch,
        ScriptedLLM([[content_chunk("persisted-answer"), usage_chunk(100)]]),
    )
    registry = TaskRegistry()

    result = await launch_delegate(
        conn=FakeConn(),
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

    sub_session_id = result.split("subagent ")[1].split(" is now")[0]
    (info,) = list(registry._tasks.values())
    await info.handle

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
    # the async contract is part of what the model sees
    assert "NON-BLOCKING" in DELEGATE_TOOL["function"]["description"]


@pytest.mark.asyncio
async def test_delegate_requires_prompt(delegate_env):
    config, parent = delegate_env
    result = await launch_delegate(
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


# ---------------------------------------------------------------------------
# react loop park/wake — the Milestone B cycle
# ---------------------------------------------------------------------------


def _react_kwargs(config, parent, conn, llm, registry):
    from crow_cli.agent import react as react_mod

    return dict(
        conn=conn,
        config=config,
        client_capabilities=None,
        turn_id="t1",
        mcp_clients={},
        llm=llm,
        tools=[DELEGATE_TOOL],
        sessions={parent.agent_id: parent},
        agent_id=parent.agent_id,
        state_accumulators={},
        logger=logger,
        registry=registry,
        react_mod=react_mod,
    )


async def _run_react(kwargs):
    react_mod = kwargs.pop("react_mod")
    chunks = []

    async def consume():
        async for chunk in react_mod.react_loop(**kwargs):
            chunks.append(chunk)

    return asyncio.create_task(consume()), chunks


async def _wait_for(predicate, timeout=5.0):
    for _ in range(int(timeout / 0.01)):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("timed out waiting for condition")


@pytest.mark.asyncio
async def test_park_wake_full_cycle(delegate_env, monkeypatch):
    """Model done + task pending -> zero-token PARK (heartbeats prove it);
    completion wakes the loop, lands as a synthetic plain message, and the
    model produces its real final answer. No end_turn before the wake."""
    config, parent = delegate_env
    from crow_cli.agent import react as react_mod

    monkeypatch.setattr(react_mod, "PARK_HEARTBEAT_S", 0.05)
    await parent.add_message({"role": "user", "content": "delegate the thing"})

    release = asyncio.Event()

    async def create(**kwargs):
        await release.wait()
        return fake_stream([content_chunk("SUBAGENT-ANSWER"), usage_chunk(100)])

    _patch_subagent_llm(
        monkeypatch,
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
    )

    parent_llm = ScriptedLLM(
        [
            # turn 1: launch the delegate
            [_delegate_call(), usage_chunk(100)],
            # turn 2: nothing left to do -> model "ends" while task pending
            [content_chunk("I will wait for the subagent."), usage_chunk(100)],
            # turn 3 (after the injected completion): the real final answer
            [content_chunk("FINAL-ANSWER"), usage_chunk(100)],
        ]
    )

    registry = TaskRegistry()
    conn = FakeConn()
    task, chunks = await _run_react(
        _react_kwargs(config, parent, conn, parent_llm, registry)
    )

    # Park proof: the per-task surface gets in_progress at launch, then
    # heartbeat re-emissions while the loop waits with zero tokens.
    await _wait_for(lambda: len(conn.tool_updates("t1/task-1")) >= 2)
    assert all(
        getattr(u, "status", None) == "in_progress"
        for u in conn.tool_updates("t1/task-1")
    )
    # No final_history before the completion lands.
    assert not any(c.get("type") == "final_history" for c in chunks)

    release.set()
    await asyncio.wait_for(task, timeout=10)

    final = [c for c in chunks if c.get("type") == "final_history"]
    assert len(final) == 1
    messages = final[0]["messages"]

    # The completion was injected as a PLAIN user message...
    synthetic = [
        m
        for m in messages
        if m["role"] == "user"
        and isinstance(m["content"], str)
        and m["content"].startswith("[task-1: delegate ")
    ]
    assert len(synthetic) == 1
    assert "finished]" in synthetic[0]["content"]
    assert "SUBAGENT-ANSWER" in synthetic[0]["content"]
    # ...and NEVER as role=tool (the launch call's one result was the ack).
    tool_msgs = [m for m in messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["content"].startswith("Launched task-1:")
    # The model reacted to the injection with the final answer.
    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["content"] == "FINAL-ANSWER"
    # The injection was surfaced to the client (best-effort user chunk).
    assert any(
        getattr(u, "session_update", None) == "user_message_chunk"
        for _, u in conn.updates
    )
    # Registry settled; per-task surface completed.
    assert registry.pending() == []
    assert conn.tool_updates("t1/task-1")[-1].status == "completed"


@pytest.mark.asyncio
async def test_completion_lands_before_park_drain_path(delegate_env, monkeypatch):
    """A fast subagent finishes while the parent is still thinking: its
    completion sits on the queue and is DRAINED at model-done — injected
    without any blocking park (no heartbeats)."""
    config, parent = delegate_env
    from crow_cli.agent import react as react_mod

    monkeypatch.setattr(react_mod, "PARK_HEARTBEAT_S", 0.05)
    await parent.add_message({"role": "user", "content": "delegate the thing"})

    _patch_subagent_llm(
        monkeypatch,
        ScriptedLLM([[content_chunk("FAST-ANSWER"), usage_chunk(100)]]),
    )
    parent_llm = ScriptedLLM(
        [
            [_delegate_call(), usage_chunk(100)],
            [content_chunk("Done delegating."), usage_chunk(100)],
            [content_chunk("FINAL"), usage_chunk(100)],
        ],
        repeat_last=True,
    )

    registry = TaskRegistry()
    conn = FakeConn()
    task, chunks = await _run_react(
        _react_kwargs(config, parent, conn, parent_llm, registry)
    )
    await asyncio.wait_for(task, timeout=10)

    messages = chunks[-1]["messages"]
    synthetic = [
        m
        for m in messages
        if m["role"] == "user"
        and isinstance(m["content"], str)
        and m["content"].startswith("[task-1: delegate ")
    ]
    assert len(synthetic) == 1
    assert "FAST-ANSWER" in synthetic[0]["content"]
    # No heartbeat ever fired: only the launch's in_progress on the surface.
    assert [getattr(u, "status", None) for u in conn.tool_updates("t1/task-1")] == [
        "in_progress",
        "completed",
    ]
    assert messages[-1]["content"] == "FINAL"


@pytest.mark.asyncio
async def test_parallel_delegates_both_injected(delegate_env, monkeypatch):
    """Two delegates launched in ONE assistant message; both completions
    are injected and the parent reacts to both."""
    config, parent = delegate_env
    from crow_cli.agent import react as react_mod

    monkeypatch.setattr(react_mod, "PARK_HEARTBEAT_S", 0.05)
    await parent.add_message({"role": "user", "content": "delegate two things"})

    async def create(**kwargs):
        text = ""
        for m in kwargs.get("messages", []):
            if m.get("role") == "user" and isinstance(m.get("content"), str):
                text = m["content"]
        answer = "ANSWER-A" if "task-a" in text else "ANSWER-B"
        return fake_stream([content_chunk(answer), usage_chunk(100)])

    _patch_subagent_llm(
        monkeypatch,
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
    )

    two_calls = [
        tool_call_chunk(0, "call-1", "delegate", '{"prompt": "task-a"}'),
        tool_call_chunk(1, "call-2", "delegate", '{"prompt": "task-b"}'),
    ]
    parent_llm = ScriptedLLM(
        [
            [*two_calls, usage_chunk(100)],
            [content_chunk("waiting on both"), usage_chunk(100)],
            [content_chunk("FINAL-BOTH"), usage_chunk(100)],
        ],
        repeat_last=True,
    )

    registry = TaskRegistry()
    conn = FakeConn()
    task, chunks = await _run_react(
        _react_kwargs(config, parent, conn, parent_llm, registry)
    )
    await asyncio.wait_for(task, timeout=10)

    messages = chunks[-1]["messages"]
    synthetic = [
        m["content"]
        for m in messages
        if m["role"] == "user"
        and isinstance(m["content"], str)
        and m["content"].startswith("[task-")
    ]
    assert len(synthetic) == 2
    joined = "\n".join(synthetic)
    assert "ANSWER-A" in joined and "ANSWER-B" in joined
    assert messages[-1]["content"] == "FINAL-BOTH"
    assert registry.pending() == []


@pytest.mark.asyncio
async def test_cancel_during_park_kills_stack(delegate_env, monkeypatch):
    """Cancelling the parked parent cancels the delegate (cancel tree); the
    subagent's partial state is persisted and the registry says cancelled."""
    config, parent = delegate_env
    from crow_cli.agent import react as react_mod

    monkeypatch.setattr(react_mod, "PARK_HEARTBEAT_S", 0.05)
    await parent.add_message({"role": "user", "content": "delegate a long thing"})

    async def create(**kwargs):
        # one chunk, then hang forever — the subagent is mid-flight
        return fake_stream([content_chunk("partial ")], hang_after=True)

    _patch_subagent_llm(
        monkeypatch,
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
    )
    parent_llm = ScriptedLLM(
        [
            [_delegate_call(prompt="long task"), usage_chunk(100)],
            [content_chunk("I will wait."), usage_chunk(100)],
        ],
        repeat_last=True,
    )

    registry = TaskRegistry()
    conn = FakeConn()
    task, chunks = await _run_react(
        _react_kwargs(config, parent, conn, parent_llm, registry)
    )

    # wait for the park (heartbeat #2 on the per-task surface)
    await _wait_for(lambda: len(conn.tool_updates("t1/task-1")) >= 2)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    (info,) = list(registry._tasks.values())
    assert info.status == "cancelled"
    assert registry.pending() == []
    # the client saw the delegate surface fail on cancel
    assert conn.tool_updates("t1/task-1")[-1].status == "failed"
    # no end_turn ever
    assert not any(c.get("type") == "final_history" for c in chunks)

    # the subagent persisted its cancelled partial state
    sub = await AgentSession.load(
        f"{info.sub_session}-1-1", memory_path=config.db_uri
    )
    roles = [m["role"] for m in sub.messages]
    assert roles[:2] == ["system", "user"]
    assert sub.messages[1]["content"] == "long task"
    assistant = [m for m in sub.messages if m["role"] == "assistant"]
    assert assistant and assistant[-1]["content"] == "partial "
    await sub.close()


@pytest.mark.asyncio
async def test_cancel_during_tool_batch_cancels_launched_delegates(
    delegate_env, monkeypatch
):
    """Cancel landing mid-batch (second delegate still provisioning): the
    FIRST delegate already launched in the background — it dies with the
    prompt task via the cancel tree in the mid-tool-execution handler."""
    config, parent = delegate_env
    from crow_cli.agent import react as react_mod

    await parent.add_message({"role": "user", "content": "delegate"})

    async def create(**kwargs):
        return fake_stream([content_chunk("partial ")], hang_after=True)

    _patch_subagent_llm(
        monkeypatch,
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
    )

    # Hang the SECOND delegate's provisioning so the cancel lands while the
    # batch is still in execute_tool_calls (first one already launched).
    real_make = delegate_mod.make_agent_session
    launches = {"n": 0}

    async def slow_make(*args, **kwargs):
        launches["n"] += 1
        if launches["n"] == 2:
            await asyncio.Event().wait()
        return await real_make(*args, **kwargs)

    monkeypatch.setattr(delegate_mod, "make_agent_session", slow_make)

    two_calls = [
        tool_call_chunk(0, "call-1", "delegate", '{"prompt": "first"}'),
        tool_call_chunk(1, "call-2", "delegate", '{"prompt": "second"}'),
    ]
    parent_llm = ScriptedLLM([[*two_calls, usage_chunk(100)]], repeat_last=True)

    registry = TaskRegistry()
    task, chunks = await _run_react(
        _react_kwargs(config, parent, FakeConn(), parent_llm, registry)
    )
    # Wait until exactly one delegate has launched (the first), then cancel.
    await _wait_for(lambda: len(registry.pending()) == 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    (info,) = list(registry._tasks.values())
    assert info.status == "cancelled"
    assert registry.pending() == []


# ---------------------------------------------------------------------------
# execute_tool_calls wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parallel_delegate_calls_run_concurrently(monkeypatch, delegate_env):
    """Two delegate calls in ONE assistant message overlap in time
    (asyncio.gather in execute_tool_calls)."""
    config, parent = delegate_env
    from crow_cli.agent import react as react_mod

    running = 0
    max_running = 0

    async def fake_launch_delegate(**kwargs):
        nonlocal running, max_running
        running += 1
        max_running = max(max_running, running)
        await asyncio.sleep(0.05)
        running -= 1
        return "Launched task-N: subagent sub is now working on the prompt."

    monkeypatch.setattr(react_mod, "launch_delegate", fake_launch_delegate)
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
    assert all(r["content"].startswith("Launched task-N:") for r in results)


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
