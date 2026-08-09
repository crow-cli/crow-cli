"""Unit tests for ollama-mv provisioning (crow_cli.cli.embeddings)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import yaml

from crow_cli.cli import embeddings

# ---------------------------------------------------------------- find_go --


def test_find_go_honors_env(monkeypatch):
    monkeypatch.setenv("GO", "/opt/go/bin/go")
    assert embeddings.find_go() == "/opt/go/bin/go"


def test_find_go_local_install(monkeypatch, tmp_path):
    monkeypatch.delenv("GO", raising=False)
    go = tmp_path / ".local/go/bin/go"
    go.parent.mkdir(parents=True)
    go.touch()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert embeddings.find_go() == str(go)


def test_find_go_path_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("GO", raising=False)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(embeddings.shutil, "which", lambda name: "/usr/bin/go")
    monkeypatch.setattr(
        embeddings.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})()
    )
    assert embeddings.find_go() == "go"


def test_find_go_missing_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("GO", raising=False)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(embeddings.shutil, "which", lambda name: None)
    with pytest.raises(embeddings.ProvisionError, match="no Go toolchain"):
        embeddings.find_go()


# --------------------------------------------------------------- pin check --


def _pin_setup(tmp_path, pin: str) -> tuple[Path, Path]:
    ollama = tmp_path / "ollama"
    ollama.mkdir()
    (ollama / "LLAMA_CPP_VERSION").write_text(pin + "\n")
    llamcpp = tmp_path / "llama.cpp"
    llamcpp.mkdir()
    return ollama, llamcpp


def _patch_describe(monkeypatch, tag: str):
    class Out:
        returncode = 0 if tag else 1
        stdout = tag + "\n" if tag else ""

    monkeypatch.setattr(embeddings.subprocess, "run", lambda *a, **k: Out())


def test_check_pin_mismatch_raises(tmp_path, monkeypatch):
    ollama, llamcpp = _pin_setup(tmp_path, "crow-colqwen2-mv")
    _patch_describe(monkeypatch, "some-other-tag")
    with pytest.raises(embeddings.ProvisionError, match="pins"):
        embeddings._check_pin(ollama, llamcpp)


def test_check_pin_match_ok(tmp_path, monkeypatch):
    ollama, llamcpp = _pin_setup(tmp_path, "crow-colqwen2-mv")
    _patch_describe(monkeypatch, "crow-colqwen2-mv")
    embeddings._check_pin(ollama, llamcpp)  # no raise


# -------------------------------------------------------- vendor checkouts --


def test_vendor_checkouts_prefers_worktree_submodules(monkeypatch, tmp_path):
    wt = tmp_path / "wt"
    for sub in ("ollama", "llama.cpp"):
        (wt / "vendor" / sub / ".git").mkdir(parents=True)
    monkeypatch.setattr("crow_cli.cli.daemon.worktree_root", lambda: wt)
    ollama, llamcpp = embeddings._vendor_checkouts(tmp_path / "cfg")
    assert ollama == wt / "vendor" / "ollama"
    assert llamcpp == wt / "vendor" / "llama.cpp"


def test_vendor_checkouts_clones_on_fresh_machine(monkeypatch, tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    monkeypatch.setattr("crow_cli.cli.daemon.worktree_root", lambda: wt)
    cfg = tmp_path / "cfg"
    calls: list[list[str]] = []

    def fake_run(cmd, cwd=None, env=None):
        calls.append(cmd)
        dest = Path(cmd[-1])
        (dest / ".git").mkdir(parents=True)
        if dest.name == "ollama":
            (dest / "LLAMA_CPP_VERSION").write_text("crow-colqwen2-mv\n")

    monkeypatch.setattr(embeddings, "_run", fake_run)
    ollama, llamcpp = embeddings._vendor_checkouts(cfg)
    assert ollama == cfg / "vendor" / "ollama"
    assert llamcpp == cfg / "vendor" / "llama.cpp"
    lc_clone = [c for c in calls if c[-1] == str(llamcpp)][0]
    assert "--branch" in lc_clone and "crow-colqwen2-mv" in lc_clone


# ----------------------------------------------------------------- repoint --


def test_repoint_surgical_preserves_comments(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "# top comment\n"
        "memory_path: /tmp/mem.lance\n"
        "daemons:\n"
        "  ollama-mv:\n"
        "    command: /old/ollama\n"
        "    env:\n"
        "      OLLAMA_HOST: 127.0.0.1:11392\n"
        "# bottom comment\n"
    )
    embeddings.repoint_command(tmp_path, "ollama-mv", "/new/ollama")
    text = cfg.read_text()
    assert "# top comment" in text and "# bottom comment" in text
    assert "/old/ollama" not in text
    parsed = yaml.safe_load(text)
    assert parsed["daemons"]["ollama-mv"]["command"] == "/new/ollama"
    assert parsed["daemons"]["ollama-mv"]["env"]["OLLAMA_HOST"] == "127.0.0.1:11392"


def test_repoint_yaml_merge_when_no_entry(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("memory_path: /tmp/mem.lance\n")
    embeddings.repoint_command(tmp_path, "ollama-mv", "/new/ollama")
    parsed = yaml.safe_load(cfg.read_text())
    assert parsed["daemons"]["ollama-mv"]["command"] == "/new/ollama"
    assert parsed["memory_path"] == "/tmp/mem.lance"


# --------------------------------------------------------------- provision --


def test_provision_idempotent(tmp_path, monkeypatch):
    monkeypatch.delenv("OLLAMA_MV_BIN", raising=False)
    fake_bin = tmp_path / "ollama"
    fake_bin.touch()
    (tmp_path / "config.yaml").write_text(
        f"daemons:\n  ollama-mv:\n    command: {fake_bin}\n"
    )

    def boom(*a, **k):
        raise AssertionError("build_from_source should not run")

    monkeypatch.setattr(embeddings, "build_from_source", boom)
    assert embeddings.provision(tmp_path) == fake_bin


def test_provision_builds_and_repoints(tmp_path, monkeypatch):
    monkeypatch.delenv("OLLAMA_MV_BIN", raising=False)
    (tmp_path / "config.yaml").write_text(
        "daemons:\n  ollama-mv:\n    command: /nonexistent/ollama\n"
    )
    built = tmp_path / "vendor" / "ollama" / "ollama"

    def fake_build(config_dir):
        built.parent.mkdir(parents=True, exist_ok=True)
        built.touch()
        return built

    monkeypatch.setattr(embeddings, "build_from_source", fake_build)
    assert embeddings.provision(tmp_path) == built
    parsed = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert parsed["daemons"]["ollama-mv"]["command"] == str(built)


# --------------------------------------------------------- verify embeddings --


class _Resp:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class _Client:
    def __init__(self, resps):
        self.resps = list(resps)
        self.calls = 0

    def post(self, url, json=None):
        self.calls += 1
        r = self.resps.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def close(self):
        pass


def test_verify_embeddings_ok(monkeypatch):
    monkeypatch.setattr(embeddings.time, "sleep", lambda s: None)
    client = _Client([_Resp(200, '{"embeddings": [[[0.1]]]}')])
    assert embeddings.verify_embeddings(client=client) is True
    assert client.calls == 1


def test_verify_embeddings_retries_then_fails(monkeypatch):
    monkeypatch.setattr(embeddings.time, "sleep", lambda s: None)
    client = _Client([httpx.ConnectError("boom"), _Resp(500, ""), _Resp(200, "{}")])
    assert embeddings.verify_embeddings(attempts=3, client=client) is False
    assert client.calls == 3
