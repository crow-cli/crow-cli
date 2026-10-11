"""`crow-cli install crow` — the .deb is the install.

The command's contract, without a 40-minute build or a root shell: which
artifact it looks for, what it needs to install it, the argv `dpkg -i` gets,
and which plan `--dry-run` prints for each route.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import typer
from rich.console import Console
from typer.testing import CliRunner

from crow_cli.cli import install_crow as ic

runner = CliRunner()


@pytest.fixture(autouse=True)
def wide_console(monkeypatch):
    """Keep rich from wrapping the plan lines the assertions match on."""
    monkeypatch.setattr(ic, "console", Console(width=200, force_terminal=False, highlight=False))
    monkeypatch.setattr(sys, "platform", "linux")


@pytest.fixture
def pipeline(tmp_path: Path) -> Path:
    """A fake checkout: repo_root() and pipeline_dir() both satisfied."""
    root = tmp_path / "crow-cli"
    (root / "packages" / "crow-gui" / "vscodium" / "assets").mkdir(parents=True)
    (root / "Cargo.toml").write_text("[workspace]\n")
    (root / "packages" / "crow-gui" / "build.sh").write_text("#!/bin/sh\n")
    monkeypatch_root(root)
    return root / "packages" / "crow-gui"


def monkeypatch_root(root: Path) -> None:
    ic.repo_root = lambda: root  # type: ignore[assignment]


def make_deb(pipeline: Path, name: str, mtime: float) -> Path:
    deb = pipeline / "vscodium" / "assets" / name
    deb.write_bytes(b"deb")
    os.utime(deb, (mtime, mtime))
    return deb


# ---- which artifact -------------------------------------------------------


def test_built_deb_picks_the_newest(pipeline):
    make_deb(pipeline, "crow_1.135.06805_amd64.deb", time.time() - 3600)
    newest = make_deb(pipeline, "crow_1.136.0_amd64.deb", time.time())
    assert ic.built_deb(pipeline) == newest


def test_built_deb_is_none_before_a_build(pipeline):
    assert ic.built_deb(pipeline) is None


# ---- what the route needs -------------------------------------------------


def test_preflight_reports_the_missing_build_tools(monkeypatch):
    monkeypatch.setattr(ic.shutil, "which", lambda name: None)
    monkeypatch.setattr(ic, "is_root", lambda: True)
    assert ic.deb_preflight() == ["dpkg-deb", "fakeroot"]


def test_preflight_wants_sudo_when_not_root(monkeypatch):
    monkeypatch.setattr(ic.shutil, "which", lambda name: None if name == "sudo" else f"/usr/bin/{name}")
    monkeypatch.setattr(ic, "is_root", lambda: False)
    assert ic.deb_preflight() == ["sudo"]


def test_preflight_is_satisfied_on_a_debian_host(monkeypatch):
    monkeypatch.setattr(ic.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(ic, "is_root", lambda: False)
    assert ic.deb_preflight() == []


# ---- the install step -----------------------------------------------------


def test_dpkg_install_goes_through_sudo_when_not_root(monkeypatch, pipeline, tmp_path):
    monkeypatch.setattr(ic, "is_root", lambda: False)
    calls = []

    def fake_run(argv, cwd=None):
        calls.append((argv, cwd))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(ic.subprocess, "run", fake_run)
    deb = make_deb(pipeline, "crow_1.135.06805_amd64.deb", time.time())
    ic.dpkg_install(deb)
    argv, cwd = calls[0]
    assert argv == ["sudo", "dpkg", "-i", str(deb)]
    assert Path(cwd) == deb.parent


def test_dpkg_install_as_root_needs_no_sudo(monkeypatch, pipeline):
    monkeypatch.setattr(ic, "is_root", lambda: True)
    calls = []
    monkeypatch.setattr(
        ic.subprocess, "run",
        lambda argv, cwd=None: calls.append(argv) or subprocess.CompletedProcess(argv, 0),
    )
    ic.dpkg_install(make_deb(pipeline, "crow_1.0_amd64.deb", time.time()))
    assert calls[0][0] == "dpkg"


def test_dpkg_failure_points_at_apt(monkeypatch, pipeline):
    monkeypatch.setattr(ic, "is_root", lambda: True)
    monkeypatch.setattr(
        ic.subprocess, "run",
        lambda argv, cwd=None: subprocess.CompletedProcess(argv, 1),
    )
    with pytest.raises(typer.Exit) as exc:
        ic.dpkg_install(make_deb(pipeline, "crow_1.0_amd64.deb", time.time()))
    assert exc.value.exit_code == 1


# ---- the plan -------------------------------------------------------------


def app():
    a = typer.Typer()
    a.command(name="crow")(ic.install_crow)
    return a


@pytest.fixture
def tools(monkeypatch):
    monkeypatch.setattr(ic.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(ic, "is_root", lambda: False)


def test_dry_run_plans_a_deb_build_and_a_dpkg_install(pipeline, tools):
    result = runner.invoke(app(), ["--dry-run"])
    assert result.exit_code == 0, result.output
    assert "./build.sh --arch x64 --deb" in result.output
    assert "would sudo dpkg -i" in result.output
    # the deb owns the trees and the menu entry: no prefix copy, no user .desktop
    assert "cp -a" not in result.output
    assert ".desktop" not in result.output


def test_dry_run_installs_an_already_built_deb_without_rebuilding(pipeline, tools):
    deb = make_deb(pipeline, "crow_1.135.06805_amd64.deb", time.time())
    result = runner.invoke(app(), ["--dry-run"])
    assert result.exit_code == 0, result.output
    assert "would skip the build" in result.output
    assert str(deb) in result.output


def test_dry_run_no_deb_falls_back_to_the_prefix_copy(pipeline, tools):
    result = runner.invoke(app(), ["--dry-run", "--no-deb"])
    assert result.exit_code == 0, result.output
    assert "./build.sh --arch x64" in result.output
    assert "--deb" not in result.output.split("./build.sh --arch x64")[1].split("\n")[0]
    assert "would cp -a" in result.output
    assert "dpkg" not in result.output
    assert ".desktop" in result.output


def test_missing_deb_tools_fail_before_the_build(pipeline, monkeypatch):
    monkeypatch.setattr(ic.shutil, "which", lambda name: None)
    monkeypatch.setattr(ic, "is_root", lambda: True)
    result = runner.invoke(app(), ["--dry-run"])
    assert result.exit_code == 1
    assert "dpkg-deb" in result.output and "fakeroot" in result.output
