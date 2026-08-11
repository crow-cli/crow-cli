"""Daemon lifecycle tests — unmanaged tracking for process and docker kinds.

The docker SDK boundary is faked at ``daemon._docker_container`` (the real
searxng container must never be touched by tests); everything else — pidfile
records, status/stop/restart logic — is the real code path.
"""

from __future__ import annotations

import os
import subprocess
import time

import pytest

from crow_cli.cli import daemon as daemon_mod
from crow_cli.cli.daemon import DaemonSpec, pid_file, read_pid, restart, start, status, stop

CID = "c0ffee" * 10  # full 60-char container id


class FakeContainer:
    def __init__(self, cid: str = CID, status: str = "running"):
        self.id = cid
        self.status = status
        self.starts = 0
        self.stops = 0

    def start(self):
        self.starts += 1
        self.status = "running"

    def stop(self, timeout: int | None = None):
        self.stops += 1
        self.status = "exited"


@pytest.fixture
def docker_spec() -> DaemonSpec:
    # No health_url/tcp_port → healthy() is trivially True, no network.
    return DaemonSpec(name="searxng", kind="docker", container="crow-searxng-1")


def _patch_docker(monkeypatch, container: FakeContainer | None):
    monkeypatch.setattr(daemon_mod, "_docker_container", lambda spec: (container, None))


# ---------------------------------------------------------------- docker --


def test_docker_status_unmanaged_when_no_record(monkeypatch, tmp_path, docker_spec):
    _patch_docker(monkeypatch, FakeContainer())
    st = status(tmp_path, docker_spec)
    assert st["running"] is True
    assert st["managed"] is False
    assert st["detail"] == "unmanaged"
    assert st["healthy"] is True


def test_docker_status_managed_when_record_matches(monkeypatch, tmp_path, docker_spec):
    _patch_docker(monkeypatch, FakeContainer())
    pf = pid_file(tmp_path, "searxng")
    pf.parent.mkdir(parents=True)
    pf.write_text(CID)
    st = status(tmp_path, docker_spec)
    assert st["running"] is True
    assert st["managed"] is True
    assert st["detail"] == "running"


def test_docker_stop_refuses_unmanaged(monkeypatch, tmp_path, docker_spec):
    container = FakeContainer()
    _patch_docker(monkeypatch, container)
    msg = stop(tmp_path, docker_spec)
    assert "running unmanaged — not stopping it" in msg
    assert container.stops == 0


def test_docker_stop_stops_managed_and_clears_record(monkeypatch, tmp_path, docker_spec):
    container = FakeContainer()
    _patch_docker(monkeypatch, container)
    pf = pid_file(tmp_path, "searxng")
    pf.parent.mkdir(parents=True)
    pf.write_text(CID)
    assert stop(tmp_path, docker_spec) == "searxng: stopped"
    assert container.stops == 1
    assert not pf.exists()


def test_docker_stop_clears_stale_record_when_container_gone(
    monkeypatch, tmp_path, docker_spec
):
    _patch_docker(monkeypatch, None)
    pf = pid_file(tmp_path, "searxng")
    pf.parent.mkdir(parents=True)
    pf.write_text(CID)
    assert stop(tmp_path, docker_spec) == "searxng: not running"
    assert not pf.exists()


def test_docker_restart_skips_unmanaged(monkeypatch, tmp_path, docker_spec):
    container = FakeContainer()
    _patch_docker(monkeypatch, container)
    msg = restart(tmp_path, docker_spec)
    assert msg == (
        "searxng: running unmanaged — restart skipped "
        "(stop it yourself, then `daemon start`)"
    )
    assert container.stops == 0
    assert container.starts == 0
    assert not pid_file(tmp_path, "searxng").exists()


def test_docker_restart_cycles_managed(monkeypatch, tmp_path, docker_spec):
    container = FakeContainer()
    _patch_docker(monkeypatch, container)
    pf = pid_file(tmp_path, "searxng")
    pf.parent.mkdir(parents=True)
    pf.write_text(CID)
    assert restart(tmp_path, docker_spec) == "searxng: stopped; searxng: started"
    assert (container.stops, container.starts) == (1, 1)
    assert pf.read_text() == CID  # re-recorded after start


def test_docker_start_records_container_id(monkeypatch, tmp_path, docker_spec):
    container = FakeContainer(status="exited")
    _patch_docker(monkeypatch, container)
    assert start(tmp_path, docker_spec) == "searxng: started"
    assert container.starts == 1
    assert pid_file(tmp_path, "searxng").read_text() == CID


def test_docker_start_noop_on_unmanaged_running(monkeypatch, tmp_path, docker_spec):
    container = FakeContainer()
    _patch_docker(monkeypatch, container)
    msg = start(tmp_path, docker_spec)
    assert msg == "searxng: already running (unmanaged — not touching it)"
    assert container.starts == 0
    assert not pid_file(tmp_path, "searxng").exists()


# --------------------------------------------------------------- process --


def test_process_restart_skips_unmanaged(monkeypatch, tmp_path):
    spec = DaemonSpec(name="svc", kind="process", command="/bin/true")
    monkeypatch.setattr(daemon_mod, "healthy", lambda spec: True)
    msg = restart(tmp_path, spec)
    assert "running unmanaged — restart skipped" in msg


def test_read_pid_ignores_container_id_record(tmp_path):
    """The pidfile slot holds a container id for docker daemons — read_pid
    must not choke on it."""
    pf = pid_file(tmp_path, "searxng")
    pf.parent.mkdir(parents=True)
    pf.write_text(CID)
    assert read_pid(tmp_path, "searxng") is None
    assert daemon_mod._read_record(tmp_path, "searxng") == CID


def test_process_stop_signals_process_group(tmp_path):
    """Wrappers like `npm exec -> sh -> node` spawn children in the daemon's
    session — stop must signal the whole group, not just the leader, or the
    child keeps holding the port."""
    leader = subprocess.Popen(["sh", "-c", "sleep 60 & wait"], start_new_session=True)
    try:
        spec = DaemonSpec(name="grp", command="sh")
        pid_file(tmp_path, "grp").parent.mkdir(parents=True)
        pid_file(tmp_path, "grp").write_text(str(leader.pid))
        assert stop(tmp_path, spec) == "grp: stopped"
        leader.wait()  # reap the leader zombie so the group dissolves
        time.sleep(0.1)
        # The child sleep got the group signal too — with a leader-only
        # kill it would still be alive here and the probe would succeed.
        with pytest.raises(ProcessLookupError):
            os.killpg(leader.pid, 0)
    finally:
        if leader.poll() is None:
            leader.kill()


# -------------------------------------------------------------- services --


@pytest.mark.parametrize(
    ("url", "port"),
    [
        ("http://127.0.0.1:2779/mcp", 2779),
        ("http://localhost:2779/mcp", 2779),
        ("http://localhost/mcp", None),
        ("not-a-url", None),
        ("http://host:bad/mcp", None),
    ],
)
def test_port_from_url(url, port):
    assert daemon_mod._port_from_url(url) == port


def test_services_block_registers_daemon_with_port_from_mcp_url():
    """A services: entry becomes a DaemonSpec; with no explicit health check,
    the tcp port is derived from the same-named mcpServers url."""
    specs: dict[str, DaemonSpec] = {}
    cfg = {
        "mcpServers": {"playwright": {"transport": "http", "url": "http://localhost:2779/mcp"}},
        "services": {"playwright": {"command": "npx", "args": ["@playwright/mcp@v0.0.79", "--port", "2779"]}},
    }
    daemon_mod._apply_service_specs(specs, cfg)
    spec = specs["playwright"]
    assert spec.command == "npx"
    assert spec.args == ["@playwright/mcp@v0.0.79", "--port", "2779"]
    assert spec.tcp_port == 2779
    assert spec.health_url is None


def test_services_block_explicit_health_wins_over_url_derivation():
    specs: dict[str, DaemonSpec] = {}
    cfg = {
        "mcpServers": {"srv": {"transport": "http", "url": "http://localhost:9999/mcp"}},
        "services": {"srv": {"command": "srv-bin", "tcp_port": 1234}},
    }
    daemon_mod._apply_service_specs(specs, cfg)
    assert specs["srv"].tcp_port == 1234


def test_services_block_patches_builtin_without_clobber():
    """A service shadowing a built-in name sets only declared fields."""
    builtin = DaemonSpec(name="ollama-mv", command="ollama", start_timeout=60.0)
    specs = {"ollama-mv": builtin}
    cfg = {"services": {"ollama-mv": {"env": {"OLLAMA_HOST": "127.0.0.1:9999"}}}}
    daemon_mod._apply_service_specs(specs, cfg)
    assert specs["ollama-mv"].env == {"OLLAMA_HOST": "127.0.0.1:9999"}
    assert specs["ollama-mv"].command == "ollama"  # untouched
    assert specs["ollama-mv"].start_timeout == 60.0  # untouched


def test_services_block_ignores_non_dict_entries():
    specs: dict[str, DaemonSpec] = {}
    daemon_mod._apply_service_specs(specs, {"services": {"broken": "npx something"}})
    assert specs == {}
