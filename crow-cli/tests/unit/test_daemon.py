"""Daemon lifecycle tests — unmanaged tracking for process and docker kinds.

The docker SDK boundary is faked at ``daemon._docker_container`` (the real
searxng container must never be touched by tests); everything else — pidfile
records, status/stop/restart logic — is the real code path.
"""

from __future__ import annotations

from pathlib import Path

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
