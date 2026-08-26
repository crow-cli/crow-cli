"""Phase 1 (image-store sprint): RustFS compose + init wiring.

Real code paths: run_init writes compose.yaml/.env/config.yaml from the
COMPOSE_YAML template — no mocks.
"""

import os

import yaml

from crow_cli.cli.init_cmd import run_init
from crow_cli.config.default.defaults import COMPOSE_YAML


def test_compose_template_parses_with_rustfs():
    d = yaml.safe_load(COMPOSE_YAML)
    assert "rustfs" in d["services"]
    assert "volume-permission-helper" in d["services"]
    assert d["networks"] == {"rustfs-network": None}
    for vol in ("rustfs_data_0", "rustfs_data_1", "rustfs_data_2", "rustfs_data_3", "logs"):
        assert vol in d["volumes"]
    # credentials are env refs, never hardcoded
    env = d["services"]["rustfs"]["environment"]
    assert "RUSTFS_ACCESS_KEY=${RUSTFS_ACCESS_KEY}" in env
    assert "RUSTFS_SECRET_KEY=${RUSTFS_SECRET_KEY}" in env
    assert not any("rustfsadmin" in e for e in env)
    # healthcheck survived as a shell script
    hc = d["services"]["rustfs"]["healthcheck"]["test"]
    assert hc[0] == "CMD" and hc[1] == "sh"
    assert "/health" in hc[3]


def test_run_init_yes_mode_renders_rustfs(tmp_path, monkeypatch):
    # keep yes-mode provider sniffing from picking up real LLM_* env vars
    for key in list(os.environ):
        if key.startswith("LLM_") or key.startswith(("YES_INSTALL_", "RUSTFS_", "SEARXNG_")):
            monkeypatch.delenv(key, raising=False)

    run_init(config_dir=tmp_path, yes=True)

    compose = yaml.safe_load((tmp_path / "compose.yaml").read_text())
    assert "rustfs" in compose["services"]
    assert "volume-permission-helper" in compose["services"]
    assert "rustfs-network" in compose["networks"]
    assert "rustfs_data_3" in compose["volumes"]

    # secrets land in .env, not in compose
    env_text = (tmp_path / ".env").read_text()
    assert "RUSTFS_ACCESS_KEY=rustfsadmin" in env_text
    assert "RUSTFS_SECRET_KEY=rustfsadmin" in env_text
    assert "rustfsadmin" not in (tmp_path / "compose.yaml").read_text()

    # config.yaml carries the s3 image_store block with env refs
    cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
    s3 = cfg["image_store"]["s3"]
    assert s3["endpoint"] == "http://localhost:9000"
    assert s3["bucket"] == "crow-images"
    assert s3["access_key"] == "${RUSTFS_ACCESS_KEY}"
    assert s3["secret_key"] == "${RUSTFS_SECRET_KEY}"
