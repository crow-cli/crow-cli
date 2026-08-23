"""Modality-aware model routing + transient-400 retry (hermetic).

Covers the carried v1 TODO item: retry transient provider 400s
(multimodal ingest timeouts) + per-model modality fallback with auto-strip
on downgrade. No LLM, no network.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
from openai import BadRequestError, AuthenticationError

from crow_cli.config import Config, LLMConfig, LLMProvider, LLModel
from crow_cli.agent.model_routing import (
    modalities_in_messages,
    route_model,
    strip_unsupported_blocks,
)
from crow_cli.agent.react import _is_transient_provider_400, send_request


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

IMG_BLOCK = {
    "type": "image_url",
    "image_url": {"url": "data:image/png;base64,AAAA"},
}
TEXT_BLOCK = {"type": "text", "text": "hello"}


def make_config(models: dict[str, LLModel]) -> Config:
    return Config(
        config_dir=Path("/tmp/crow-routing-test"),
        llm=LLMConfig(
            providers={"p1": LLMProvider(name="p1"), "p2": LLMProvider(name="p2")},
            models=models,
        ),
    )


MODELS = {
    "text-only": LLModel(
        name="text-only",
        provider_name="p1",
        model_id="text-only-id",
        modality=["text"],
        fallbacks=["vision-model"],
    ),
    "vision-model": LLModel(
        name="vision-model",
        provider_name="p1",
        model_id="vision-id",
        modality=["text", "image"],
    ),
    "other-provider-vision": LLModel(
        name="other-provider-vision",
        provider_name="p2",
        model_id="other-vision-id",
        modality=["text", "image"],
    ),
    "default-modality": LLModel(
        name="default-modality", provider_name="p1", model_id="default-id"
    ),
}


# ---------------------------------------------------------------------------
# modalities_in_messages
# ---------------------------------------------------------------------------


def test_modalities_none_for_text_only():
    msgs = [{"role": "user", "content": "plain string"}]
    assert modalities_in_messages(msgs) == set()


def test_modalities_detects_image():
    msgs = [
        {"role": "user", "content": [TEXT_BLOCK, IMG_BLOCK]},
    ]
    assert modalities_in_messages(msgs) == {"image"}


# ---------------------------------------------------------------------------
# route_model
# ---------------------------------------------------------------------------


def test_route_no_modalities_unchanged():
    cfg = make_config(MODELS)
    assert route_model(cfg, "text-only-id", set()) == ("text-only-id", set())


def test_route_default_modality_is_permissive():
    # modality defaults to ["text", "image"] = assume vision-capable until proven otherwise
    cfg = make_config(MODELS)
    assert route_model(cfg, "default-id", {"image"}) == ("default-id", set())


def test_route_capable_model_unchanged():
    cfg = make_config(MODELS)
    assert route_model(cfg, "vision-id", {"image"}) == ("vision-id", set())


def test_route_falls_back_to_capable_same_provider():
    cfg = make_config(MODELS)
    model_id, to_strip = route_model(cfg, "text-only-id", {"image"})
    assert model_id == "vision-id"
    assert to_strip == set()


def test_route_skips_other_provider_fallback_and_strips():
    models = dict(MODELS)
    models["text-only"] = LLModel(
        name="text-only",
        provider_name="p1",
        model_id="text-only-id",
        modality=["text"],
        fallbacks=["other-provider-vision"],  # p2 — client is bound to p1
    )
    cfg = make_config(models)
    model_id, to_strip = route_model(cfg, "text-only-id", {"image"})
    assert model_id == "text-only-id"
    assert to_strip == {"image"}


def test_route_no_fallback_strips():
    models = dict(MODELS)
    models["text-only"] = LLModel(
        name="text-only",
        provider_name="p1",
        model_id="text-only-id",
        modality=["text"],
    )
    cfg = make_config(models)
    assert route_model(cfg, "text-only-id", {"image"}) == (
        "text-only-id",
        {"image"},
    )


def test_route_unknown_model_id_is_permissive():
    cfg = make_config(MODELS)
    assert route_model(cfg, "not-in-config", {"image"}) == ("not-in-config", set())


# ---------------------------------------------------------------------------
# strip_unsupported_blocks
# ---------------------------------------------------------------------------


def test_strip_replaces_images_in_place():
    msgs = [
        {"role": "user", "content": [TEXT_BLOCK, IMG_BLOCK, TEXT_BLOCK]},
        {"role": "assistant", "content": "string content untouched"},
    ]
    out = strip_unsupported_blocks(msgs, {"image"})
    assert out[0]["content"][0] == TEXT_BLOCK
    assert out[0]["content"][1]["type"] == "text"
    assert "image omitted" in out[0]["content"][1]["text"]
    assert out[0]["content"][2] == TEXT_BLOCK
    assert out[1]["content"] == "string content untouched"
    # original untouched
    assert msgs[0]["content"][1] == IMG_BLOCK


def test_strip_empty_modalities_is_identity():
    msgs = [{"role": "user", "content": [IMG_BLOCK]}]
    assert strip_unsupported_blocks(msgs, set()) is msgs


# ---------------------------------------------------------------------------
# transient 400 detection
# ---------------------------------------------------------------------------


def _http_response(status: int) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("POST", "http://test/v1/chat"))


def test_dashscope_ingest_timeout_is_transient():
    body = {
        "error": {
            "code": "invalid_parameter_error",
            "message": "Download multimodal file timed out",
        }
    }
    e = BadRequestError(str(body), response=_http_response(400), body=body)
    assert _is_transient_provider_400(e) is True


def test_plain_400_is_not_transient():
    e = BadRequestError(
        "unsupported parameter", response=_http_response(400), body={"error": "x"}
    )
    assert _is_transient_provider_400(e) is False


def test_401_is_never_transient():
    e = AuthenticationError("bad key", response=_http_response(401), body=None)
    assert _is_transient_provider_400(e) is False


# ---------------------------------------------------------------------------
# send_request: transient 400 retried, then succeeds
# ---------------------------------------------------------------------------


@dataclass
class FakeSession:
    messages: list = field(default_factory=list)
    model_identifier: str = "text-only-id"


class FakeCompletions:
    def __init__(self, fail_times: int, exc_factory):
        self.fail_times = fail_times
        self.exc_factory = exc_factory
        self.calls = 0
        self.last_model = None
        self.last_messages = None

    async def create(self, **kwargs):
        self.calls += 1
        self.last_model = kwargs.get("model")
        self.last_messages = kwargs.get("messages")
        if self.calls <= self.fail_times:
            raise self.exc_factory()
        return "STREAM-OK"


class FakeLLM:
    def __init__(self, completions):
        self.chat = type("C", (), {"completions": completions})


def test_send_request_retries_transient_400(monkeypatch):
    body = {"error": {"code": "invalid_parameter_error",
                      "message": "Download multimodal file timed out"}}
    completions = FakeCompletions(
        fail_times=2,
        exc_factory=lambda: BadRequestError(str(body), response=_http_response(400), body=body),
    )
    llm = FakeLLM(completions)
    session = FakeSession(messages=[{"role": "user", "content": "hi"}])

    sleeps = []

    async def fake_sleep(d):
        sleeps.append(d)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        send_request(llm, session, tools=[], max_tokens=100, max_retries=3, retry_delay=0.01)
    )
    assert result == "STREAM-OK"
    assert completions.calls == 3
    assert len(sleeps) == 2


def test_send_request_does_not_retry_permanent_400():
    completions = FakeCompletions(
        fail_times=5,
        exc_factory=lambda: BadRequestError(
            "model not found", response=_http_response(400), body={"error": "nope"}
        ),
    )
    llm = FakeLLM(completions)
    session = FakeSession(messages=[{"role": "user", "content": "hi"}])
    with pytest.raises(BadRequestError):
        asyncio.run(
            send_request(llm, session, tools=[], max_tokens=100, max_retries=3, retry_delay=0.01)
        )
    assert completions.calls == 1  # failed fast, no retry


def test_send_request_routes_and_strips():
    """Text-only model + image in history, no capable fallback → image is
    replaced by a placeholder in the outgoing request, history untouched."""
    cfg = make_config(
        {
            "text-only": LLModel(
                name="text-only",
                provider_name="p1",
                model_id="text-only-id",
                modality=["text"],
            )
        }
    )
    completions = FakeCompletions(fail_times=0, exc_factory=lambda: None)
    llm = FakeLLM(completions)
    session = FakeSession(
        messages=[{"role": "user", "content": [TEXT_BLOCK, IMG_BLOCK]}],
        model_identifier="text-only-id",
    )
    asyncio.run(
        send_request(
            llm, session, tools=[], max_tokens=100, config=cfg, max_retries=1
        )
    )
    # history untouched
    assert session.messages[0]["content"][1] == IMG_BLOCK
    # outgoing payload had the image replaced by a placeholder
    sent = completions.last_messages[0]["content"]
    assert sent[0] == TEXT_BLOCK
    assert sent[1]["type"] == "text"
    assert "image omitted" in sent[1]["text"]


def test_send_request_routes_to_fallback_model():
    cfg = make_config(MODELS)
    completions = FakeCompletions(fail_times=0, exc_factory=lambda: None)
    llm = FakeLLM(completions)
    session = FakeSession(
        messages=[{"role": "user", "content": [TEXT_BLOCK, IMG_BLOCK]}],
        model_identifier="text-only-id",
    )
    asyncio.run(
        send_request(
            llm, session, tools=[], max_tokens=100, config=cfg, max_retries=1
        )
    )
    assert completions.last_model == "vision-id"
