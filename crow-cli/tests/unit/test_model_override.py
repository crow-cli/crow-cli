"""-m/--model override on AcpAgent (run -m and acp -m)."""

import pytest
import yaml

from crow_cli.config import Config
from crow_cli.agent.main import AcpAgent


@pytest.fixture
def two_model_config(test_config_dir):
    """Config with two models so override-vs-first is distinguishable."""
    config_file = test_config_dir / "config.yaml"
    data = yaml.safe_load(config_file.read_text())
    data["models"]["second-model"] = {
        "provider": "test-provider",
        "model": "second-model-id",
    }
    # sort_keys=False: model ORDER is the feature under test (first = default)
    config_file.write_text(yaml.dump(data, sort_keys=False))
    return Config.load(test_config_dir)


def test_no_override_uses_first_model(two_model_config):
    agent = AcpAgent(config=two_model_config)
    assert agent._model_override is None
    assert agent._default_model_value() == "test-provider:test-model-id"
    assert agent._default_model_identifier() == "test-model-id"


def test_override_selects_named_model(two_model_config):
    agent = AcpAgent(config=two_model_config, model="second-model")
    assert agent._default_model_value() == "test-provider:second-model-id"
    assert agent._default_model_identifier() == "second-model-id"


def test_override_unknown_model_fails_fast(two_model_config):
    with pytest.raises(ValueError, match="not found in config.yaml"):
        AcpAgent(config=two_model_config, model="does-not-exist")
