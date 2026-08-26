"""Phase 4 (postgres sprint): PostgreSQL compose + init wiring.

Real code paths: run_init writes compose.yaml/.env/config.yaml from the
COMPOSE_YAML template; Config.load + apply_config_overrides resolve the
${POSTGRES_*} refs in db_uri — no mocks.
"""

import os

import yaml

from crow_cli.cli.init_cmd import run_init
from crow_cli.config import Config, apply_config_overrides
from crow_cli.config.default.defaults import COMPOSE_YAML

_CLEAN_PREFIXES = ("LLM_", "YES_INSTALL_", "RUSTFS_", "SEARXNG_", "POSTGRES_")


def test_compose_template_parses_with_postgres():
    d = yaml.safe_load(COMPOSE_YAML)
    assert "postgres" in d["services"]
    assert "postgres_data" in d["volumes"]
    # credentials are env refs, never hardcoded
    env = d["services"]["postgres"]["environment"]
    assert "POSTGRES_USER=${POSTGRES_USER}" in env
    assert "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" in env
    assert "POSTGRES_DB=${POSTGRES_DB}" in env
    # healthcheck runs inside the container against its own env
    hc = d["services"]["postgres"]["healthcheck"]["test"]
    assert hc[0] == "CMD-SHELL" and "pg_isready" in hc[1]


def test_run_init_yes_mode_renders_postgres(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith(_CLEAN_PREFIXES):
            monkeypatch.delenv(key, raising=False)

    run_init(config_dir=tmp_path, yes=True)

    compose = yaml.safe_load((tmp_path / "compose.yaml").read_text())
    assert "postgres" in compose["services"]
    assert "postgres_data" in compose["volumes"]
    assert "rustfs" in compose["services"]  # yes-mode installs the full stack

    env_text = (tmp_path / ".env").read_text()
    assert "POSTGRES_PORT=5432" in env_text
    assert "POSTGRES_USER=crow" in env_text
    assert "POSTGRES_DB=crow" in env_text
    password = next(
        line.split("=", 1)[1]
        for line in env_text.splitlines()
        if line.startswith("POSTGRES_PASSWORD=")
    )
    assert len(password) == 32  # secrets.token_hex(16)
    # secrets never land in compose
    assert password not in (tmp_path / "compose.yaml").read_text()

    # config.yaml carries the postgres db_uri with env refs
    cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert cfg["db_uri"] == (
        "postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}"
        "@localhost:${POSTGRES_PORT}/${POSTGRES_DB}"
    )


def test_run_init_skip_postgres_keeps_sqlite(tmp_path, monkeypatch):
    """Interactive wizard with PostgreSQL declined → sqlite, no service."""
    for key in list(os.environ):
        if key.startswith(_CLEAN_PREFIXES):
            monkeypatch.delenv(key, raising=False)

    # provider loop: one provider with an empty key, then stop; searxng
    # port; rustfs keys (interactive mode prompts for them)
    prompt_answers = iter(
        ["testprov", "http://localhost:1234", "2946", "rustfsadmin", "rustfsadmin"]
    )
    monkeypatch.setattr(
        "rich.prompt.Prompt.ask", staticmethod(lambda *a, **k: next(prompt_answers))
    )
    monkeypatch.setattr("getpass.getpass", lambda *a, **k: "")

    def confirm(question, *a, **k):
        if "PostgreSQL" in question:
            return False
        if "another provider" in question:
            return False
        return True  # searxng, rustfs, looks-good

    monkeypatch.setattr("rich.prompt.Confirm.ask", staticmethod(confirm))

    run_init(config_dir=tmp_path, yes=False)

    compose = yaml.safe_load((tmp_path / "compose.yaml").read_text())
    assert "postgres" not in compose["services"]
    cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert cfg["db_uri"].startswith("sqlite:///")
    assert "POSTGRES_PASSWORD" not in (tmp_path / ".env").read_text()


def test_db_uri_env_refs_resolve_on_load(test_config_dir, monkeypatch):
    """config.yaml db_uri with ${POSTGRES_*} refs resolves via .env at
    Config.load — the same mechanism the init wizard relies on."""
    monkeypatch.setenv("POSTGRES_USER", "crow")
    monkeypatch.setenv("POSTGRES_PASSWORD", "s3cret")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "crow")

    config_file = test_config_dir / "config.yaml"
    data = yaml.safe_load(config_file.read_text())
    data["db_uri"] = (
        "postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}"
        "@localhost:${POSTGRES_PORT}/${POSTGRES_DB}"
    )
    config_file.write_text(yaml.dump(data))

    cfg = Config.load(test_config_dir)
    assert cfg.db_uri == "postgresql+psycopg://crow:s3cret@localhost:5432/crow"


def test_apply_config_overrides_resolves_db_uri(test_config_dir, monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "crow")
    monkeypatch.setenv("POSTGRES_PASSWORD", "s3cret")
    monkeypatch.setenv("POSTGRES_PORT", "15432")
    monkeypatch.setenv("POSTGRES_DB", "crowdb")

    cfg = Config.load(test_config_dir)
    override = test_config_dir / "override.yaml"
    override.write_text(
        "db_uri: postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}"
        "@localhost:${POSTGRES_PORT}/${POSTGRES_DB}\n"
    )
    cfg = apply_config_overrides(cfg, override)
    assert cfg.db_uri == "postgresql+psycopg://crow:s3cret@localhost:15432/crowdb"
