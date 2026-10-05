"""The systemd unit `crow-cli install web` writes (hermetic).

The install command itself shells out to bun, cargo and systemctl, which is
exactly what a unit test must not do; what is worth testing without them is
the unit file, because a typo in ExecStart is a service that never starts,
and the repo discovery, because everything else hangs off it.
"""

from __future__ import annotations

from pathlib import Path

from crow_cli.cli.install_web import UNIT_NAME, repo_root, unit_path, unit_text


def test_the_unit_starts_the_binary_with_its_three_arguments():
    text = unit_text(
        Path("/home/t/.local/bin/crow-web"),
        2770,
        Path("/home/t/src"),
        "ws://127.0.0.1:2769/acp",
    )
    assert (
        "ExecStart=/home/t/.local/bin/crow-web --port 2770 --root /home/t/src"
        " --acp-url ws://127.0.0.1:2769/acp" in text
    )
    # A pty pump that panics must come back, not stay down.
    assert "Restart=on-failure" in text
    # The shells are interactive; a dumb TERM breaks every tui in them.
    assert "Environment=TERM=xterm-256color" in text
    assert text.strip().endswith("WantedBy=default.target")
    assert "[Unit]" in text and "[Service]" in text and "[Install]" in text


def test_the_unit_lives_in_the_systemd_user_directory():
    path = unit_path()
    assert path.name == UNIT_NAME
    assert path.parts[-3:-1] == ("systemd", "user")
    assert path.is_absolute()


def test_repo_root_is_the_checkout_that_owns_rust_and_the_workspace():
    root = repo_root()
    assert (root / "Cargo.toml").is_file()
    assert (root / "packages" / "chat" / "package.json").is_file()
    assert (root / "crates" / "crow-web" / "Cargo.toml").is_file()
