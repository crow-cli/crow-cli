"""Config parsing + wiring: memory db location, skills_dir, prompt path."""

from pathlib import Path

import pytest
import yaml

from crow_cli.config import SKILLS_DIR, Config
from crow_cli.config import config as config_module
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


def test_an_explicit_path_never_reads_the_config_it_does_not_need(tmp_path, monkeypatch):
    """``MemoryClient(path=...)`` opens its database and stops there.

    ``Config.load(None)`` reads the developer's own
    ``~/.agents/crow/config.yaml``, dotenvs the real ``.env`` into this
    process's environment and attaches a handler to the real log file — and
    eight of ``MemoryClient``'s thirteen construction sites are
    ``agent/session.py`` helpers that pass ``memory_path`` and nothing else,
    so all of that used to happen once per session operation.

    No mock is needed to pin it, because ``Config.load`` already refuses a
    removed global key outright: point the default config dir at a document
    that cannot load, and anything that reads it cannot get past
    construction. ``DEFAULT_CONFIG_DIR`` is a module global resolved at call
    time, which is what makes it redirectable.
    """
    broken = tmp_path / "broken"
    (broken / "logs").mkdir(parents=True)
    (broken / "config.yaml").write_text("TEMPERATURE: 0.5\n")
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_DIR", broken)

    target = tmp_path / "explicit.db"
    client = MemoryClient(path=f"sqlite:///{target}")
    assert client.db_uri == f"sqlite:///{target}"
    assert target.exists()
    assert client.images_dir == tmp_path / "images"

    # The image store is the one thing left that needs a config, and it is
    # lazy on purpose: a session carrying no image blob never dials the S3
    # endpoint the config would have named. Asking for it here does load.
    with pytest.raises(ValueError, match="TEMPERATURE"):
        client.image_store

    # And with no path there is nothing to be lazy about.
    with pytest.raises(ValueError, match="TEMPERATURE"):
        MemoryClient()


def test_redis_url_falls_through_to_the_compose_port(test_config_dir, monkeypatch):
    """No key in config.yaml: the env, then the port compose publishes on.

    ``REDIS_PORT`` is the knob compose.yaml publishes the bus on and ``.env`` is
    loaded before this runs, so one value moves the container and the client.
    """
    monkeypatch.delenv("CROW_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_PORT", raising=False)
    assert Config.load(test_config_dir).redis_url == "redis://localhost:6379/0"

    monkeypatch.setenv("REDIS_PORT", "6390")
    assert Config.load(test_config_dir).redis_url == "redis://localhost:6390/0"

    monkeypatch.setenv("CROW_REDIS_URL", "redis://from-env:6379/3")
    assert Config.load(test_config_dir).redis_url == "redis://from-env:6379/3"


def test_redis_url_from_config_wins_over_the_environment(test_config_dir, monkeypatch):
    monkeypatch.setenv("CROW_REDIS_URL", "redis://from-env:6379/3")
    monkeypatch.setenv("REDIS_PORT", "6390")
    _add_keys(test_config_dir, redis_url="redis://from-config:6379/1")
    assert Config.load(test_config_dir).redis_url == "redis://from-config:6379/1"


def test_an_explicit_empty_redis_url_turns_the_wake_bus_off(test_config_dir, monkeypatch):
    """``redis_url: ""`` means no bus, and used to be unreachable.

    An empty url is the documented off switch: it is what makes
    ``WakeWatcher.start`` a no-op ("mailbox polling only") and ``publish_wake``
    return False instead of dialling a broker nobody is running. The or-chain
    this replaced could not express it — ``"" or default`` is the default — so
    the one setting that disables the bus was the one setting the loader
    ignored, and an operator who cleared it got a client that kept trying
    localhost:6379 and a ``crow-cli timers`` that refused to start on a url the
    config had just supplied.
    """
    monkeypatch.setenv("CROW_REDIS_URL", "redis://from-env:6379/3")
    monkeypatch.setenv("REDIS_PORT", "6390")
    _add_keys(test_config_dir, redis_url="")
    assert Config.load(test_config_dir).redis_url == ""


def test_an_unset_env_var_in_redis_url_also_turns_it_off(test_config_dir, monkeypatch):
    """The realistic way an operator clears it: a variable that is not set.

    ``resolve_env_vars`` runs over the whole document before the presence check,
    so ``${CROW_REDIS_URL}`` with the variable unset expands to empty and means
    the same thing as an empty literal — with the warning the loader already
    emits for every unset variable it expanded.
    """
    monkeypatch.delenv("CROW_REDIS_URL", raising=False)
    monkeypatch.setenv("REDIS_PORT", "6390")
    _add_keys(test_config_dir, redis_url="${CROW_REDIS_URL}")
    assert Config.load(test_config_dir).redis_url == ""
