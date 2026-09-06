"""`crow-cli init` Step 5 — the source checkout, for real.

These clone actual git repositories (local ones, built in tmp_path) and run an
actual `uv sync`. Nothing is mocked: init's job is to leave a working checkout
on disk, so the tests look on disk.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from crow_cli.cli import source
from crow_cli.cli.init_cmd import run_init

MINIMAL_PYPROJECT = """\
[project]
name = "fake-checkout"
version = "0.0.1"
requires-python = ">=3.9"
dependencies = []
"""


def _git(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"git {args}: {proc.stderr}"
    return proc.stdout.strip()


def _seed(repo: Path, name: str) -> None:
    """A commit on `main` that looks enough like the real repo to bootstrap."""
    repo.mkdir(parents=True)
    _git(["init", "-b", "main"], repo)
    (repo / "pyproject.toml").write_text(MINIMAL_PYPROJECT)
    (repo / "README.md").write_text(f"# {name}\n")
    if name == "crow-cli":
        skill = repo / "skills" / "crow-cli"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: crow-cli\ndescription: map\n---\n\nbody\n")
    else:
        (repo / "sync-skills.py").write_text("# the site's skill publisher\n")
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "init"], repo)


@pytest.fixture
def remotes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Two real local repos standing in for the GitHub remotes."""
    made = {}
    for name in ("crow-cli", "crow-cli.github.io"):
        repo = tmp_path / "remotes" / name
        _seed(repo, name)
        made[name] = repo
    monkeypatch.setattr(source, "CROW_REPO", str(made["crow-cli"]))
    monkeypatch.setattr(source, "SITE_REPO", str(made["crow-cli.github.io"]))
    return made


@pytest.fixture
def quiet_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep yes-mode provider sniffing off the real environment."""
    for key in list(os.environ):
        if key.startswith("LLM_") or key.startswith(("YES_INSTALL_", "RUSTFS_", "SEARXNG_")):
            monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# clone_or_update
# ---------------------------------------------------------------------------


def test_clone_or_update_clones_then_updates(tmp_path: Path, remotes: dict[str, Path]):
    dest = tmp_path / "clone"
    assert source.clone_or_update(str(remotes["crow-cli"]), dest) == "cloned"
    assert (dest / "pyproject.toml").is_file()
    assert _git(["rev-parse", "--abbrev-ref", "HEAD"], dest) == "main"

    assert source.clone_or_update(str(remotes["crow-cli"]), dest) == "updated"

    # a new upstream commit arrives on the next pass
    (remotes["crow-cli"] / "NEW.md").write_text("new\n")
    _git(["add", "-A"], remotes["crow-cli"])
    _git(["commit", "-m", "new"], remotes["crow-cli"])
    assert source.clone_or_update(str(remotes["crow-cli"]), dest) == "updated"
    assert (dest / "NEW.md").read_text() == "new\n"


def test_clone_or_update_leaves_a_dirty_checkout_alone(tmp_path: Path, remotes: dict[str, Path]):
    dest = tmp_path / "clone"
    source.clone_or_update(str(remotes["crow-cli"]), dest)
    (dest / "README.md").write_text("local work in progress\n")

    assert source.clone_or_update(str(remotes["crow-cli"]), dest) == "dirty"
    # and it did not blow the local work away
    assert (dest / "README.md").read_text() == "local work in progress\n"


def test_clone_or_update_survives_an_unreachable_remote(tmp_path: Path, remotes: dict[str, Path]):
    dest = tmp_path / "clone"
    source.clone_or_update(str(remotes["crow-cli"]), dest)
    _git(["remote", "set-url", "origin", str(tmp_path / "gone")], dest)

    # the checkout is still usable; only the fetch failed
    assert source.clone_or_update(str(remotes["crow-cli"]), dest) == "offline"


def test_clone_or_update_refuses_a_non_empty_non_git_dir(tmp_path: Path, remotes: dict[str, Path]):
    dest = tmp_path / "clone"
    dest.mkdir()
    (dest / "something").write_text("x")
    with pytest.raises(source.SourceError, match="not a git checkout"):
        source.clone_or_update(str(remotes["crow-cli"]), dest)


# ---------------------------------------------------------------------------
# bootstrap
# ---------------------------------------------------------------------------


def test_bootstrap_clones_both_repos_syncs_and_installs_the_skill(
    tmp_path: Path, remotes: dict[str, Path]
):
    config_dir = tmp_path / "crow"
    lines: list[str] = []

    report = source.bootstrap(config_dir, log=lines.append)

    assert report["errors"] == []
    assert report["checkouts"] == {
        "crow-cli": str(source.global_checkout(config_dir)),
        "crow-cli.github.io": str(source.site_checkout(config_dir)),
    }
    assert source.is_checkout(source.global_checkout(config_dir))
    assert (source.site_checkout(config_dir) / "sync-skills.py").is_file()

    # the venv is pre-created so the first agent spawn is not a dep install
    assert report["synced"] is True
    assert (source.global_checkout(config_dir) / ".venv").is_dir()

    # the skill is installed GLOBALLY — a sibling of the config dir
    installed = Path(str(report["skill"]))
    assert installed == tmp_path / "skills" / "crow-cli" / "SKILL.md"
    assert installed.is_file()
    assert "name: crow-cli" in installed.read_text()

    assert any("cloned" in line for line in lines)


def test_bootstrap_is_idempotent(tmp_path: Path, remotes: dict[str, Path]):
    config_dir = tmp_path / "crow"
    first = source.bootstrap(config_dir)
    second = source.bootstrap(config_dir)

    assert first["errors"] == [] == second["errors"]
    assert second["checkouts"] == first["checkouts"]
    assert second["synced"] is True
    assert Path(str(second["skill"])).is_file()


def test_bootstrap_reports_a_clone_failure_and_keeps_going(
    tmp_path: Path, remotes: dict[str, Path], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(source, "CROW_REPO", str(tmp_path / "does-not-exist"))
    config_dir = tmp_path / "crow"

    report = source.bootstrap(config_dir)

    # crow-cli failed, the site still cloned, nothing raised
    assert len(report["errors"]) == 1
    assert "crow-cli:" in report["errors"][0]
    assert list(report["checkouts"]) == ["crow-cli.github.io"]
    assert report["skill"] is None
    assert report["synced"] is False


def test_bootstrap_reports_missing_git_without_raising(
    tmp_path: Path, remotes: dict[str, Path], monkeypatch: pytest.MonkeyPatch
):
    real_which = shutil.which
    monkeypatch.setattr(
        source.shutil,
        "which",
        lambda name, *a, **k: None if name == "git" else real_which(name, *a, **k),
    )

    report = source.bootstrap(tmp_path / "crow")

    assert report["checkouts"] == {}
    assert report["skill"] is None
    assert len(report["errors"]) == 1
    assert "git" in report["errors"][0]
    assert not (tmp_path / "crow" / "src").exists()


def test_bootstrap_reports_missing_uv_without_raising(
    tmp_path: Path, remotes: dict[str, Path], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(source, "uv_available", lambda: False)

    report = source.bootstrap(tmp_path / "crow")

    # the checkouts and the skill still landed; only the venv pre-sync did not
    assert len(report["checkouts"]) == 2
    assert report["synced"] is False
    assert report["skill"] is not None
    assert any("uv" in e for e in report["errors"])


# ---------------------------------------------------------------------------
# run_init
# ---------------------------------------------------------------------------


def test_run_init_clones_the_source_checkout(
    tmp_path: Path, remotes: dict[str, Path], quiet_env: None
):
    config_dir = tmp_path / "crow"

    run_init(config_dir=config_dir, yes=True, source=True)

    # the wizard still did its day job
    assert (config_dir / "config.yaml").is_file()
    assert (config_dir / ".env").is_file()
    # ... and Step 5 left a runnable checkout behind it
    assert source.is_checkout(source.global_checkout(config_dir))
    assert (source.global_checkout(config_dir) / ".venv").is_dir()
    assert (tmp_path / "skills" / "crow-cli" / "SKILL.md").is_file()


def test_run_init_no_source_skips_the_clone(
    tmp_path: Path, remotes: dict[str, Path], quiet_env: None
):
    config_dir = tmp_path / "crow"

    run_init(config_dir=config_dir, yes=True, source=False)

    assert (config_dir / "config.yaml").is_file()
    assert not (config_dir / "src").exists()
    assert not (tmp_path / "skills").exists()
