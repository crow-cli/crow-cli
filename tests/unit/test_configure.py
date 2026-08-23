"""Config parsing + wiring: memory db location, skills_dir, prompt path."""

from pathlib import Path

import yaml

from crow_cli.config import SKILLS_DIR, Config
from crow_cli.agent.memory import MemoryClient


def _add_keys(config_dir, **keys):
    config_file = config_dir / "config.yaml"
    data = yaml.safe_load(config_file.read_text())
    data.update(keys)
    config_file.write_text(yaml.dump(data))








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


def test_memory_client_creates_sqlite_in_config_dir(test_config_dir):
    client = MemoryClient(config_dir=test_config_dir)
    assert (test_config_dir / "crow.db").exists()
    assert client.images_dir == test_config_dir / "images"


def test_db_uri_from_config(test_config_dir):
    target = test_config_dir / "custom.db"
    _add_keys(test_config_dir, db_uri=f"sqlite:///{target}")
    client = MemoryClient(config_dir=test_config_dir)
    assert target.exists()
    assert client.images_dir == test_config_dir / "images"


def test_legacy_memory_path_becomes_sqlite_uri(test_config_dir):
    target = test_config_dir / "legacy.db"
    _add_keys(test_config_dir, memory_path=str(target))
    cfg = Config.load(test_config_dir)
    assert cfg.db_uri == f"sqlite:///{target}"
    MemoryClient(config_dir=test_config_dir)
    assert target.exists()
