"""
Request-logging unit tests (hermetic — mocked LLM, no network).

Under --debug, ``send_request`` dumps the exact request payload (the
append-only chat history + params) to ``request_log_path`` so immutable-history
analysis can diff consecutive turns. These tests pin that behavior.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from crow_cli.agent.react import send_request


def _mock_llm():
    llm = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=object())
    return llm


@pytest.mark.asyncio
async def test_send_request_dumps_request_payload(tmp_path):
    """With request_log_path, the exact request payload is written as JSON."""
    llm = _mock_llm()
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "hi"},
    ]
    session = SimpleNamespace(messages=messages, model_identifier="test-model")
    log_path = tmp_path / "turn-1-request.json"

    await send_request(
        llm, session, tools=[], max_tokens=50, request_log_path=str(log_path)
    )

    assert log_path.exists()
    payload = json.loads(log_path.read_text())
    assert payload["model"] == "test-model"
    assert payload["messages"] == messages
    assert payload["max_tokens"] == 50
    assert payload["stream_options"] == {"include_usage": True}


@pytest.mark.asyncio
async def test_dumped_messages_match_what_is_sent(tmp_path):
    """The dumped messages must be byte-identical to what goes to the API."""
    llm = _mock_llm()
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "turn 1"},
        {"role": "assistant", "content": "reply 1"},
        {"role": "user", "content": "turn 2"},
    ]
    session = SimpleNamespace(messages=messages, model_identifier="m")
    log_path = tmp_path / "turn-2-request.json"

    await send_request(
        llm, session, tools=[], max_tokens=10, request_log_path=str(log_path)
    )

    payload = json.loads(log_path.read_text())
    sent_kwargs = llm.chat.completions.create.call_args.kwargs
    assert payload["messages"] == sent_kwargs["messages"]
    assert payload["model"] == sent_kwargs["model"]


@pytest.mark.asyncio
async def test_no_dump_without_request_log_path(tmp_path):
    """Without request_log_path (normal path), nothing is written."""
    llm = _mock_llm()
    session = SimpleNamespace(
        messages=[{"role": "user", "content": "hi"}], model_identifier="m"
    )

    await send_request(llm, session, tools=[], max_tokens=10)

    assert list(tmp_path.iterdir()) == []
    # the request still went out
    assert llm.chat.completions.create.await_count == 1
