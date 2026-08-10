"""Config parsing + wiring: crow-memory retry budget, skills_dir, prompt path."""

from pathlib import Path

import yaml

from crow_cli.agent.configure import SKILLS_DIR, Config
from crow_cli.agent.memory import MemoryClient


def _add_keys(config_dir, **keys):
    config_file = config_dir / "config.yaml"
    data = yaml.safe_load(config_file.read_text())
    data.update(keys)
    config_file.write_text(yaml.dump(data))


def test_memory_retry_defaults(test_config_dir):
    cfg = Config.load(test_config_dir)
    assert cfg.memory_max_retries == 12
    assert cfg.memory_retry_base_delay == 0.5
    assert cfg.memory_retry_max_delay == 30.0


def test_memory_retry_overrides(test_config_dir):
    _add_keys(
        test_config_dir,
        memory_max_retries=0,  # robust mode: retry forever
        memory_retry_base_delay=2.5,
        memory_retry_max_delay=60.0,
    )
    cfg = Config.load(test_config_dir)
    assert cfg.memory_max_retries == 0
    assert cfg.memory_retry_base_delay == 2.5
    assert cfg.memory_retry_max_delay == 60.0


def test_skills_dir_default(test_config_dir):
    cfg = Config.load(test_config_dir)
    assert cfg.skills_dir == str(SKILLS_DIR)


def test_skills_dir_override(test_config_dir):
    _add_keys(test_config_dir, skills_dir="~/custom-skills")
    cfg = Config.load(test_config_dir)
    assert cfg.skills_dir == str(Path.home() / "custom-skills")


def test_system_prompt_path_expanded(test_config_dir):
    _add_keys(test_config_dir, system_prompt_path="~/.agents/crow/prompts/system_prompt.jinja2")
    cfg = Config.load(test_config_dir)
    assert cfg.system_prompt_path == Path.home() / ".agents" / "crow" / "prompts" / "system_prompt.jinja2"


def test_memory_client_wires_config_into_sdk(test_config_dir):
    _add_keys(
        test_config_dir,
        memory_max_retries=7,
        memory_retry_base_delay=1.5,
        memory_retry_max_delay=45.0,
    )
    client = MemoryClient(config_dir=test_config_dir)
    assert client._sdk._max_retries == 7
    assert client._sdk._base_delay == 1.5
    assert client._sdk._max_delay == 45.0
