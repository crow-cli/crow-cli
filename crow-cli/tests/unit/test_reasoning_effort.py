"""
reasoning_effort config: pydantic enum validation + request param swap.

Reasoning models (gpt-5, o3, ...) REJECT temperature and take
reasoning_effort instead. When config.yaml sets reasoning_effort, crow must
send it and OMIT temperature entirely. Values are validated at config-load
time against OpenAI's enumerable set so a typo fails fast, not mid-turn.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from crow_cli.agent.configure import (
    REASONING_EFFORT_VALUES,
    Config,
    build_sampling_params,
    parse_reasoning_effort,
)
from crow_cli.agent.react import send_request


# ---------------------------------------------------------------------------
# build_sampling_params — the one sampling rule shared by react loop + compact
# ---------------------------------------------------------------------------


class TestBuildSamplingParams:
    def test_reasoning_effort_set_omits_temperature(self):
        assert build_sampling_params("high", 0.6) == {"reasoning_effort": "high"}

    def test_reasoning_effort_none_string_is_still_set(self):
        # "none" is a real OpenAI effort level, not "unset"
        assert build_sampling_params("none", 0.6) == {"reasoning_effort": "none"}

    def test_unset_falls_back_to_temperature(self):
        assert build_sampling_params(None, 0.4) == {"temperature": 0.4}


# ---------------------------------------------------------------------------
# pydantic enum validation
# ---------------------------------------------------------------------------


class TestParseReasoningEffort:
    @pytest.mark.parametrize("value", REASONING_EFFORT_VALUES)
    def test_every_enumerable_value_accepted(self, value):
        assert parse_reasoning_effort(value) == value

    def test_case_and_whitespace_normalized(self):
        assert parse_reasoning_effort("  HIGH ") == "high"

    def test_invalid_value_raises_naming_the_enum(self):
        with pytest.raises(ValueError) as excinfo:
            parse_reasoning_effort("ultra")
        msg = str(excinfo.value)
        assert "ultra" in msg
        for value in REASONING_EFFORT_VALUES:
            assert value in msg

    def test_enum_matches_openai_api_reference(self):
        # developers.openai.com chat completions: "Currently supported values
        # are none, minimal, low, medium, high, xhigh, and max."
        assert REASONING_EFFORT_VALUES == (
            "none",
            "minimal",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        )


# ---------------------------------------------------------------------------
# Config.load wiring
# ---------------------------------------------------------------------------


def _add_keys(config_dir, **keys):
    config_file = config_dir / "config.yaml"
    data = yaml.safe_load(config_file.read_text())
    data.update(keys)
    config_file.write_text(yaml.dump(data))


def test_config_load_parses_reasoning_effort(test_config_dir):
    _add_keys(test_config_dir, reasoning_effort="high")
    cfg = Config.load(test_config_dir)
    assert cfg.reasoning_effort == "high"


def test_config_load_defaults_to_none(test_config_dir):
    cfg = Config.load(test_config_dir)
    assert cfg.reasoning_effort is None


def test_config_load_invalid_reasoning_effort_fails_fast(test_config_dir):
    _add_keys(test_config_dir, reasoning_effort="ultra")
    with pytest.raises(ValueError, match="reasoning_effort"):
        Config.load(test_config_dir)


# ---------------------------------------------------------------------------
# send_request: reasoning_effort REPLACES temperature on the wire
# ---------------------------------------------------------------------------


class FakeLLM:
    def __init__(self):
        self.captured = None
        outer = self

        class Completions:
            async def create(self, **kwargs):
                outer.captured = kwargs
                return object()

        class Chat:
            completions = Completions()

        self.chat = Chat()


def _session():
    return SimpleNamespace(
        messages=[{"role": "user", "content": "hi"}],
        model_identifier="test-model",
    )


@pytest.mark.asyncio
async def test_send_request_reasoning_effort_replaces_temperature():
    llm = FakeLLM()
    await send_request(
        llm, _session(), tools=[], max_tokens=100, reasoning_effort="high"
    )
    assert llm.captured["reasoning_effort"] == "high"
    assert "temperature" not in llm.captured


@pytest.mark.asyncio
async def test_send_request_temperature_when_reasoning_effort_unset():
    llm = FakeLLM()
    await send_request(llm, _session(), tools=[], max_tokens=100, temperature=0.3)
    assert llm.captured["temperature"] == 0.3
    assert "reasoning_effort" not in llm.captured


@pytest.mark.asyncio
async def test_request_log_payload_swaps_too(tmp_path):
    llm = FakeLLM()
    log_path = str(tmp_path / "request.json")
    await send_request(
        llm,
        _session(),
        tools=[],
        max_tokens=100,
        reasoning_effort="low",
        request_log_path=log_path,
    )
    payload = json.loads(Path(log_path).read_text())
    assert payload["reasoning_effort"] == "low"
    assert "temperature" not in payload
