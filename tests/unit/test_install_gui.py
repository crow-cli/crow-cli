"""The launcher and desktop files `crow-cli install gui` writes (hermetic).

Like `test_install_web.py`, only the pure text/template pieces are worth a
unit test: the real command shells out to bun and cargo and downloads
electron, which a unit test must not do.
"""

from __future__ import annotations

from pathlib import Path

from crow_cli.cli.install import app_dir, desktop_text, launcher_text


def test_the_app_lives_in_the_local_share_layout():
    path = app_dir(Path("/home/t"))
    assert path == Path("/home/t/.local/share/crow/gui")
    assert path.is_absolute()


def test_the_launcher_exports_the_bundled_binary_and_execs_electron():
    text = launcher_text()
    assert text.startswith("#!/usr/bin/env sh")
    # The electron main process finds crow-web through this env var.
    assert 'export CROW_WEB_BIN="${CROW_WEB_BIN:-$APP_DIR/crow-web}"' in text
    # The app dir is overridable and defaults to the install layout.
    assert 'APP_DIR="${CROW_GUI_DIR:-$HOME/.local/share/crow/gui}"' in text
    # One exec, straight into the app's electron binary.
    assert 'exec "$APP_DIR/node_modules/.bin/electron" "$APP_DIR"' in text


def test_the_desktop_entry_points_at_the_launcher():
    text = desktop_text(Path("/home/t/.local/bin/crow-gui"))
    assert "Type=Application" in text
    assert "Name=Crow" in text
    assert "Exec=/home/t/.local/bin/crow-gui" in text
    assert "Terminal=false" in text
