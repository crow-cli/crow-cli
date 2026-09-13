"""crow_cli.__version__ comes from the installed package metadata, whose
single source of truth is [project].version in pyproject.toml."""

import tomllib
from importlib.metadata import version
from pathlib import Path

import crow_cli

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_version_matches_pyproject():
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    assert crow_cli.__version__ == pyproject["project"]["version"]


def test_version_matches_installed_metadata():
    assert crow_cli.__version__ == version("crow-cli")


def test_cli_version_flag():
    from typer.testing import CliRunner

    from crow_cli.cli.main import app

    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert crow_cli.__version__ in result.output
