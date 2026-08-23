"""
Per-model compaction threshold: config parsing + resolution.

The global MAX_COMPACT_TOKENS stays the rate for subscription API models;
a model with max_compact_tokens set (typically a local one) overrides it.
Resolution must be LIVE from the session's current model — models can be
switched mid-session — so the resolver is called per check, never cached.
The react-loop wiring is covered in tests/integration/test_react_loop_tool_round.py.
"""

from pathlib import Path

import pytest
import yaml

from crow_cli.config import (
    Config,
    LLMConfig,
    LLModel,
    LLMProvider,
    max_compact_tokens_for,
)


def _set_model(config_dir, **model_keys):
    config_file = config_dir / "config.yaml"
    data = yaml.safe_load(config_file.read_text())
    data["models"]["test-model"].update(model_keys)
    config_file.write_text(yaml.dump(data))


# ---------------------------------------------------------------------------
# Config.load wiring
# ---------------------------------------------------------------------------


def test_max_compact_tokens_defaults_to_none(test_config_dir):
    cfg = Config.load(test_config_dir)
    assert cfg.llm.models["test-model"].max_compact_tokens is None


def test_config_load_parses_per_model_max_compact_tokens(test_config_dir):
    _set_model(test_config_dir, max_compact_tokens=24000)
    cfg = Config.load(test_config_dir)
    model = cfg.llm.models["test-model"]
    assert model.max_compact_tokens == 24000
    assert isinstance(model.max_compact_tokens, int)


@pytest.mark.parametrize("bad", ["lots", True, [1]])
def test_config_load_invalid_max_compact_tokens_fails_fast(test_config_dir, bad):
    _set_model(test_config_dir, max_compact_tokens=bad)
    with pytest.raises(ValueError, match=r"test-model.*max_compact_tokens"):
        Config.load(test_config_dir)


# ---------------------------------------------------------------------------
# max_compact_tokens_for — per-model resolution with global fallback
# ---------------------------------------------------------------------------


def _config_with(model: LLModel, global_threshold: int = 180000) -> Config:
    return Config(
        config_dir=Path("/tmp/crow-compact-threshold-test"),
        llm=LLMConfig(
            providers={"p": LLMProvider(name="p")},
            models={model.name: model},
        ),
        MAX_COMPACT_TOKENS=global_threshold,
    )


def test_local_model_overrides_global_threshold():
    cfg = _config_with(
        LLModel(
            name="local", provider_name="p", model_id="local-id",
            max_compact_tokens=24000,
        )
    )
    assert max_compact_tokens_for(cfg, "local-id") == 24000


def test_subscription_model_keeps_global_threshold():
    cfg = _config_with(
        LLModel(name="api", provider_name="p", model_id="api-id")
    )
    assert max_compact_tokens_for(cfg, "api-id") == 180000


def test_unknown_model_keeps_global_threshold():
    cfg = _config_with(LLModel(name="api", provider_name="p", model_id="api-id"))
    assert max_compact_tokens_for(cfg, "not-configured") == 180000


def test_resolution_follows_the_current_model_not_session_init():
    """Mid-session model switch: same config, different current model,
    different threshold — so callers must resolve per check."""
    cfg = _config_with(
        LLModel(
            name="local", provider_name="p", model_id="local-id",
            max_compact_tokens=24000,
        )
    )
    cfg.llm.models["api"] = LLModel(name="api", provider_name="p", model_id="api-id")
    assert max_compact_tokens_for(cfg, "local-id") == 24000
    assert max_compact_tokens_for(cfg, "api-id") == 180000
