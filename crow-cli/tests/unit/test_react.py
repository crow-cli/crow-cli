"""
react.py unit tests — the crown jewel's inner ring.

Covers the pure helpers, the send_request retry matrix (real openai
exception types, scripted transport), process_response chunk logging and
cancel-time state, and execute_tool_calls error paths. The wire-level loop
behaviors live in tests/integration/test_react_loop_*.py.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from types import SimpleNamespace

import httpx
import pytest
from mcp.types import TextContent
from openai import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)
from openai._exceptions import APITimeoutError

from crow_cli.agent.react import (
    TOOL_CALL_CANCELLED_MESSAGE,
    _is_transient_provider_400,
    cancelled_tool_results,
    execute_tool_calls,
    process_response,
    send_request,
    session_from_agent_id,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Chunk fakes (same shape as the integration helpers; kept local so the unit
# tier has no dependency on the integration module).
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
    """chat.completions.create plays a script: Exception instances raise,
    lists of chunks return as a stream. Counts attempts."""

    def __init__(self, script: list):
        self.script = list(script)
        self.attempts = 0
        self.create_kwargs = None
        outer = self

        class Completions:
            async def create(self, **kwargs):
                outer.attempts += 1
                outer.create_kwargs = kwargs
                action = outer.script.pop(0)
                if isinstance(action, BaseException):
                    raise action
                return fake_stream(action)

        class Chat:
            completions = Completions()

        self.chat = Chat()


def fake_session(messages=None):
    return SimpleNamespace(
        messages=messages or [{"role": "user", "content": "hi"}],
        model_identifier="test-model",
    )


def _http_req():
    return httpx.Request("POST", "https://provider.test/chat/completions")


def _api_error(status: int, body) -> APIError:
    """Real openai status exceptions (BadRequestError, ...) carry the
    status_code attribute the retry logic keys on."""
    req = _http_req()
    resp = httpx.Response(status, request=req)
    cls = {
        400: BadRequestError,
        401: AuthenticationError,
        429: RateLimitError,
        500: InternalServerError,
    }[status]
    return cls("provider error", response=resp, body=body)


async def _send(llm, **kw):
    defaults = dict(
        session=fake_session(),
        tools=[],
        max_tokens=64,
        max_retries=3,
        retry_delay=0,
        config=None,
    )
    defaults.update(kw)
    return await send_request(llm, **defaults)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def test_session_from_agent_id():
    assert session_from_agent_id("s-1-1") == "s"
    assert session_from_agent_id("cool-name-3-1") == "cool-name"
    assert session_from_agent_id("cool-name-3-2") == "cool-name"


def test_cancelled_tool_results_one_per_call():
    results = cancelled_tool_results([{"id": "a"}, {"id": "b"}])
    assert [r["tool_call_id"] for r in results] == ["a", "b"]
    assert all(r["role"] == "tool" for r in results)
    assert all(r["content"] == TOOL_CALL_CANCELLED_MESSAGE for r in results)


def test_cancelled_tool_results_empty():
    assert cancelled_tool_results([]) == []


# ---------------------------------------------------------------------------
# transient-400 detection
# ---------------------------------------------------------------------------


def test_transient_400_marker_detected():
    e = _api_error(400, {"error": {"message": "Download multimodal file timed out"}})
    assert _is_transient_provider_400(e) is True


def test_plain_400_not_transient():
    e = _api_error(400, {"error": {"message": "invalid model name"}})
    assert _is_transient_provider_400(e) is False


def test_500_with_marker_is_not_a_transient_400():
    e = _api_error(500, {"error": {"message": "ingest timed out"}})
    assert _is_transient_provider_400(e) is False


def test_unserializable_body_does_not_crash():
    e = _api_error(400, object())
    assert _is_transient_provider_400(e) is False


# ---------------------------------------------------------------------------
# send_request retry matrix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_retried_then_succeeds():
    req = _http_req()
    llm = ScriptedLLM(
        [APITimeoutError(request=req), APITimeoutError(request=req), [content_chunk("ok")]]
    )
    await _send(llm)
    assert llm.attempts == 3


@pytest.mark.asyncio
async def test_rate_limit_retried_then_succeeds():
    llm = ScriptedLLM([_api_error(429, None), [content_chunk("ok")]])
    await _send(llm)
    assert llm.attempts == 2


@pytest.mark.asyncio
async def test_connection_error_retried_then_succeeds():
    llm = ScriptedLLM(
        [APIConnectionError(request=_http_req()), [content_chunk("ok")]]
    )
    await _send(llm)
    assert llm.attempts == 2


@pytest.mark.asyncio
async def test_5xx_exhausts_retries_and_raises():
    llm = ScriptedLLM([_api_error(500, None)] * 3)
    with pytest.raises(APIError):
        await _send(llm)
    assert llm.attempts == 3


@pytest.mark.asyncio
async def test_non_retryable_401_raises_immediately():
    llm = ScriptedLLM([_api_error(401, {"error": "bad key"}), [content_chunk("never")]])
    with pytest.raises(APIError):
        await _send(llm)
    assert llm.attempts == 1


@pytest.mark.asyncio
async def test_transient_400_retried_then_succeeds():
    t400 = _api_error(400, {"error": {"message": "Download multimodal file timed out"}})
    llm = ScriptedLLM([t400, t400, [content_chunk("ok")]])
    await _send(llm)
    assert llm.attempts == 3


@pytest.mark.asyncio
async def test_plain_400_raises_immediately():
    llm = ScriptedLLM([_api_error(400, {"error": {"message": "bad request"}})])
    with pytest.raises(APIError):
        await _send(llm)
    assert llm.attempts == 1


@pytest.mark.asyncio
async def test_cancellation_is_not_retried():
    llm = ScriptedLLM([asyncio.CancelledError(), [content_chunk("never")]])
    with pytest.raises(asyncio.CancelledError):
        await _send(llm)
    assert llm.attempts == 1


@pytest.mark.asyncio
async def test_request_carries_stream_and_usage_options():
    llm = ScriptedLLM([[content_chunk("ok")]])
    await _send(llm)
    kw = llm.create_kwargs
    assert kw["stream"] is True
    assert kw["stream_options"] == {"include_usage": True}
    assert kw["parallel_tool_calls"] is True
    # config=None fallback: plain temperature, no reasoning_effort
    assert kw["temperature"] == 0.6
    assert "reasoning_effort" not in kw


# ---------------------------------------------------------------------------
# process_response: chunk log + cancel-time state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_response_writes_chunk_log(tmp_path):
    chunks = [content_chunk("a"), content_chunk("b"), usage_chunk()]
    log_path = tmp_path / "chunks.jsonl"
    acc = {}
    finals = []
    async for msg_type, token in process_response(
        fake_stream(chunks), acc, chunk_log_path=str(log_path)
    ):
        if msg_type == "final":
            finals.append(token)
    lines = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert [l["chunk_index"] for l in lines] == [1, 2, 3]
    assert all("chunk" in l and "msg_types" in l for l in lines)
    # every logged chunk must be JSON-serializable by construction here
    json.dumps(lines)
    thinking, content, tool_call_inputs, usage = finals[0]
    assert "".join(content) == "ab"
    assert usage["total_tokens"] == 100


@pytest.mark.asyncio
async def test_process_response_cancel_keeps_partial_state():
    acc = {}

    async def consume():
        async for _ in process_response(
            fake_stream([content_chunk("par")], hang_after=True), acc
        ):
            pass

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert "".join(acc["content"]) == "par"
    assert acc["tool_calls"] == {}


# ---------------------------------------------------------------------------
# execute_tool_calls error paths
# ---------------------------------------------------------------------------


class RecordingConn:
    def __init__(self):
        self.updates = []

    async def session_update(self, session_id, update):
        self.updates.append(update)


def _tool_call(id: str, name: str, arguments: str) -> dict:
    return {"id": id, "type": "function", "function": {"name": name, "arguments": arguments}}


@pytest.mark.asyncio
async def test_malformed_tool_args_produce_error_result_and_repair_in_place():
    calls = [_tool_call("c1", "search", "[1, 2]")]  # valid JSON, not an object
    results = await execute_tool_calls(
        conn=RecordingConn(),
        client_capabilities=None,
        turn_id="t",
        config=None,
        mcp_clients={},
        sessions={},
        agent_id="s-1-1",
        tool_call_inputs=calls,
        logger=logger,
        hooks=[],
    )
    assert len(results) == 1
    assert results[0]["tool_call_id"] == "c1"
    assert "malformed arguments" in results[0]["content"]
    # history is detoxified: the stored call now carries valid JSON
    assert calls[0]["function"]["arguments"] == "{}"


class ExplodingMCP:
    async def call_tool(self, name, args):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_tool_exception_yields_error_result_and_failed_progress():
    conn = RecordingConn()
    results = await execute_tool_calls(
        conn=conn,
        client_capabilities=None,
        turn_id="t",
        config=None,
        mcp_clients={"s": ExplodingMCP()},
        sessions={},
        agent_id="s-1-1",
        tool_call_inputs=[_tool_call("c1", "search", '{"q": "x"}')],
        logger=logger,
        hooks=[],
    )
    assert len(results) == 1
    assert "Error" in results[0]["content"]
    assert any(getattr(u, "status", None) == "failed" for u in conn.updates)


class OneThenHangMCP:
    """First call returns a real result, second hangs until cancelled."""

    def __init__(self):
        self.calls = []

    async def call_tool(self, name, args):
        self.calls.append(name)
        if len(self.calls) == 1:
            return SimpleNamespace(
                content=[TextContent(type="text", text="ok-1")], isError=False
            )
        await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_cancel_keeps_finished_results_and_fills_placeholders():
    results: list[dict] = []
    task = asyncio.create_task(
        execute_tool_calls(
            conn=RecordingConn(),
            client_capabilities=None,
            turn_id="t",
            config=None,
            mcp_clients={"s": OneThenHangMCP()},
            sessions={},
            agent_id="s-1-1",
            tool_call_inputs=[
                _tool_call("c1", "search", '{"q": "a"}'),
                _tool_call("c2", "search", '{"q": "b"}'),
            ],
            logger=logger,
            hooks=[],
            tool_results=results,
        )
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    by_id = {r["tool_call_id"]: r for r in results}
    assert set(by_id) == {"c1", "c2"}
    assert "ok-1" in str(by_id["c1"]["content"])
    assert by_id["c2"]["content"] == TOOL_CALL_CANCELLED_MESSAGE
