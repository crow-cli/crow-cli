"""
Per-model sampling config: pydantic enum validation + request param swap.

Reasoning models (gpt-5, o3, ...) REJECT temperature and take
reasoning_effort instead. Each model in config.yaml carries its own
temperature (default 0.6) and optional reasoning_effort; when the latter is
set crow sends it and OMITS temperature entirely. Values are validated at
config-load time against OpenAI's enumerable set so a typo fails fast, not
mid-turn. The old global TEMPERATURE / reasoning_effort keys are rejected.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from crow_cli.agent.configure import (
    REASONING_EFFORT_VALUES,
    Config,
    LLMConfig,
    LLModel,
    LLMProvider,
    build_sampling_params,
    parse_reasoning_effort,
    sampling_params_for,
)
from crow_cli.agent.react import send_request

# Qwen3.8-27B recommended Instruct (non-thinking) mode sampling — the real
# values this pass-through exists for.
QWEN_INSTRUCT = dict(
    top_p=0.80,
    top_k=20,
    min_p=0.0,
    presence_penalty=1.5,
    repetition_penalty=1.0,
)


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

    def test_optional_params_split_standard_vs_extra_body(self):
        # top_p / presence_penalty are OpenAI kwargs; top_k / min_p /
        # repetition_penalty are not and must ride in extra_body.
        assert build_sampling_params(None, 0.7, **QWEN_INSTRUCT) == {
            "temperature": 0.7,
            "top_p": 0.80,
            "presence_penalty": 1.5,
            "extra_body": {
                "top_k": 20,
                "min_p": 0.0,
                "repetition_penalty": 1.0,
            },
        }

    def test_unset_optional_params_omitted_entirely(self):
        params = build_sampling_params(None, 0.7, top_p=0.95)
        assert params == {"temperature": 0.7, "top_p": 0.95}
        assert "extra_body" not in params

    def test_explicit_zero_values_are_sent(self):
        # 0 / 0.0 are falsy but valid — None alone means "omit".
        params = build_sampling_params(None, 1.0, min_p=0.0, presence_penalty=0.0)
        assert params["presence_penalty"] == 0.0
        assert params["extra_body"] == {"min_p": 0.0}

    def test_reasoning_effort_omits_all_other_sampling_params(self):
        assert (
            build_sampling_params("high", 0.6, **QWEN_INSTRUCT)
            == {"reasoning_effort": "high"}
        )


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
# Config.load wiring — per-model
# ---------------------------------------------------------------------------


def _set_model(config_dir, **model_keys):
    config_file = config_dir / "config.yaml"
    data = yaml.safe_load(config_file.read_text())
    data["models"]["test-model"].update(model_keys)
    config_file.write_text(yaml.dump(data))


def test_config_load_per_model_defaults(test_config_dir):
    cfg = Config.load(test_config_dir)
    model = cfg.llm.models["test-model"]
    assert model.temperature == 0.6
    assert model.reasoning_effort is None
    assert model.modality == ["text", "image"]


def test_config_load_parses_per_model_temperature(test_config_dir):
    _set_model(test_config_dir, temperature=0.3)
    cfg = Config.load(test_config_dir)
    assert cfg.llm.models["test-model"].temperature == 0.3


def test_config_load_parses_per_model_reasoning_effort(test_config_dir):
    _set_model(test_config_dir, reasoning_effort="high")
    cfg = Config.load(test_config_dir)
    assert cfg.llm.models["test-model"].reasoning_effort == "high"


def test_config_load_parses_modality_text(test_config_dir):
    _set_model(test_config_dir, modality="text")
    cfg = Config.load(test_config_dir)
    assert cfg.llm.models["test-model"].modality == ["text"]


def test_config_load_invalid_reasoning_effort_fails_fast(test_config_dir):
    _set_model(test_config_dir, reasoning_effort="ultra")
    with pytest.raises(ValueError, match="reasoning_effort"):
        Config.load(test_config_dir)


def test_config_load_parses_modality_list(test_config_dir):
    _set_model(test_config_dir, modality=["text", "image", "video"])
    cfg = Config.load(test_config_dir)
    assert cfg.llm.models["test-model"].modality == ["text", "image", "video"]


def test_config_load_invalid_modality_fails_fast(test_config_dir):
    _set_model(test_config_dir, modality="hologram")
    with pytest.raises(ValueError, match="modality"):
        Config.load(test_config_dir)


def test_config_load_optional_sampling_params_default_none(test_config_dir):
    cfg = Config.load(test_config_dir)
    model = cfg.llm.models["test-model"]
    assert model.top_p is None
    assert model.top_k is None
    assert model.min_p is None
    assert model.presence_penalty is None
    assert model.repetition_penalty is None


def test_config_load_parses_optional_sampling_params(test_config_dir):
    _set_model(test_config_dir, temperature=0.7, **QWEN_INSTRUCT)
    cfg = Config.load(test_config_dir)
    model = cfg.llm.models["test-model"]
    assert model.top_p == 0.80
    assert model.top_k == 20
    assert isinstance(model.top_k, int)
    assert model.min_p == 0.0  # explicit zero survives
    assert model.presence_penalty == 1.5
    assert model.repetition_penalty == 1.0


@pytest.mark.parametrize("bad", ["abc", True, [0.9]])
def test_config_load_invalid_optional_param_fails_fast(test_config_dir, bad):
    _set_model(test_config_dir, top_p=bad)
    with pytest.raises(ValueError, match=r"test-model.*top_p"):
        Config.load(test_config_dir)


@pytest.mark.parametrize("stale", ["TEMPERATURE", "reasoning_effort"])
def test_config_load_rejects_global_sampling_keys(test_config_dir, stale):
    config_file = test_config_dir / "config.yaml"
    data = yaml.safe_load(config_file.read_text())
    data[stale] = 0.6 if stale == "TEMPERATURE" else "high"
    config_file.write_text(yaml.dump(data))
    with pytest.raises(ValueError, match="per model"):
        Config.load(test_config_dir)


# ---------------------------------------------------------------------------
# sampling_params_for — per-model resolution
# ---------------------------------------------------------------------------


def _config_with(model: LLModel) -> Config:
    return Config(
        config_dir=Path("/tmp/crow-sampling-test"),
        llm=LLMConfig(
            providers={"p": LLMProvider(name="p")},
            models={model.name: model},
        ),
    )


def test_sampling_params_for_reasoning_model():
    cfg = _config_with(
        LLModel(name="r", provider_name="p", model_id="r-id", reasoning_effort="xhigh")
    )
    assert sampling_params_for(cfg, "r-id") == {"reasoning_effort": "xhigh"}


def test_sampling_params_for_temperature_model():
    cfg = _config_with(
        LLModel(name="t", provider_name="p", model_id="t-id", temperature=0.2)
    )
    assert sampling_params_for(cfg, "t-id") == {"temperature": 0.2}


def test_sampling_params_for_unknown_model_gets_defaults():
    cfg = _config_with(LLModel(name="t", provider_name="p", model_id="t-id"))
    assert sampling_params_for(cfg, "not-configured") == {"temperature": 0.6}


def test_sampling_params_for_forwards_optional_params():
    cfg = _config_with(
        LLModel(
            name="qwen",
            provider_name="p",
            model_id="qwen-id",
            temperature=0.7,
            **QWEN_INSTRUCT,
        )
    )
    assert sampling_params_for(cfg, "qwen-id") == {
        "temperature": 0.7,
        "top_p": 0.80,
        "presence_penalty": 1.5,
        "extra_body": {"top_k": 20, "min_p": 0.0, "repetition_penalty": 1.0},
    }


def test_sampling_params_for_reasoning_model_drops_optional_params():
    cfg = _config_with(
        LLModel(
            name="r",
            provider_name="p",
            model_id="r-id",
            reasoning_effort="high",
            **QWEN_INSTRUCT,
        )
    )
    assert sampling_params_for(cfg, "r-id") == {"reasoning_effort": "high"}


# ---------------------------------------------------------------------------
# send_request: the routed model's params REPLACE the fallback on the wire
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


def _session(model_identifier="test-model"):
    return SimpleNamespace(
        messages=[{"role": "user", "content": "hi"}],
        model_identifier=model_identifier,
    )


@pytest.mark.asyncio
async def test_send_request_fallback_reasoning_effort_replaces_temperature():
    llm = FakeLLM()
    await send_request(
        llm, _session(), tools=[], max_tokens=100, reasoning_effort="high"
    )
    assert llm.captured["reasoning_effort"] == "high"
    assert "temperature" not in llm.captured


@pytest.mark.asyncio
async def test_send_request_fallback_temperature_when_reasoning_effort_unset():
    llm = FakeLLM()
    await send_request(llm, _session(), tools=[], max_tokens=100, temperature=0.3)
    assert llm.captured["temperature"] == 0.3
    assert "reasoning_effort" not in llm.captured


@pytest.mark.asyncio
async def test_send_request_uses_per_model_reasoning_effort():
    cfg = _config_with(
        LLModel(
            name="test-model",
            provider_name="p",
            model_id="test-model",
            reasoning_effort="medium",
            temperature=0.6,
        )
    )
    llm = FakeLLM()
    await send_request(llm, _session(), tools=[], max_tokens=100, config=cfg)
    assert llm.captured["reasoning_effort"] == "medium"
    assert "temperature" not in llm.captured


@pytest.mark.asyncio
async def test_send_request_uses_per_model_temperature():
    cfg = _config_with(
        LLModel(
            name="test-model",
            provider_name="p",
            model_id="test-model",
            temperature=0.25,
        )
    )
    llm = FakeLLM()
    await send_request(llm, _session(), tools=[], max_tokens=100, config=cfg)
    assert llm.captured["temperature"] == 0.25
    assert "reasoning_effort" not in llm.captured


@pytest.mark.asyncio
async def test_send_request_passes_optional_params_through():
    cfg = _config_with(
        LLModel(
            name="test-model",
            provider_name="p",
            model_id="test-model",
            temperature=0.7,
            **QWEN_INSTRUCT,
        )
    )
    llm = FakeLLM()
    await send_request(llm, _session(), tools=[], max_tokens=100, config=cfg)
    # Standard OpenAI fields go as top-level kwargs...
    assert llm.captured["temperature"] == 0.7
    assert llm.captured["top_p"] == 0.80
    assert llm.captured["presence_penalty"] == 1.5
    # ...non-standard ones via extra_body for compatible servers.
    assert llm.captured["extra_body"] == {
        "top_k": 20,
        "min_p": 0.0,
        "repetition_penalty": 1.0,
    }
    assert "top_k" not in llm.captured
    assert "min_p" not in llm.captured
    assert "repetition_penalty" not in llm.captured


@pytest.mark.asyncio
async def test_send_request_no_extra_body_when_params_unset():
    cfg = _config_with(
        LLModel(name="test-model", provider_name="p", model_id="test-model")
    )
    llm = FakeLLM()
    await send_request(llm, _session(), tools=[], max_tokens=100, config=cfg)
    assert "extra_body" not in llm.captured
    assert "top_p" not in llm.captured


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
