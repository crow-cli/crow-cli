"""The non-Debian path of ``crow-cli install desktop``: unpack the release .deb
into a user-local app dir. Every test builds a tiny .deb and installs into
tmp_path, so nothing touches ~/.local or needs root."""

import io
import os
import shutil
import tarfile
from pathlib import Path

from crow_cli.cli import install
from crow_cli.cli.install import install_local

#: A real dynamically linked ELF, so the ldd dependency check runs for real.
ELF = Path(shutil.which("true") or "/usr/bin/true").resolve().read_bytes()


def make_deb(path: Path, extra: dict[str, bytes] | None = None) -> Path:
    """Write a .deb shaped like the Tauri release: usr/{bin,lib,share}."""
    files = {
        "usr/bin/Crow": ELF,
        "usr/lib/Crow/extension-host/host.cjs": b"// host",
        "usr/share/applications/Crow.desktop": b"[Desktop Entry]\nExec=Crow\nIcon=Crow\n",
        "usr/share/icons/hicolor/256x256@2/apps/Crow.png": b"png",
        **(extra or {}),
    }
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as tar:
        for name, body in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(body))
    members = [
        ("debian-binary", b"2.0\n"),
        ("control.tar.gz", b"x"),  # odd length: exercises ar's 2-byte padding
        ("data.tar.gz", data.getvalue()),
    ]
    with path.open("wb") as f:
        f.write(b"!<arch>\n")
        for name, body in members:
            f.write(f"{name:<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(body):<10}`\n".encode())
            f.write(body + b"\n" * (len(body) % 2))
    return path


def test_installs_self_contained_app_dir(tmp_path):
    prefix = tmp_path / "local"
    install_local(make_deb(tmp_path / "crow.deb"), prefix)

    app = prefix / "crow.app"
    exe = app / "bin" / "Crow"
    assert os.access(exe, os.X_OK)
    # Tauri finds resources at <exe dir>/../lib/Crow.
    assert (app / "lib" / "Crow" / "extension-host" / "host.cjs").is_file()
    assert (prefix / "bin" / "Crow").resolve() == exe
    assert (prefix / "share" / "applications" / "Crow.desktop").read_text() == (
        f'[Desktop Entry]\nExec="{exe}"\n'
        f"Icon={app}/share/icons/hicolor/256x256@2/apps/Crow.png\n"
    )
    assert sorted(p.name for p in prefix.iterdir()) == ["bin", "crow.app", "share"]


def test_reinstall_replaces_app_dir_and_sweeps_killed_staging(tmp_path):
    prefix = tmp_path / "local"
    install_local(make_deb(tmp_path / "v1.deb", {"usr/lib/Crow/v1.js": b""}), prefix)
    (prefix / ".crow.app-killed").mkdir()  # staging from a SIGKILLed run

    install_local(make_deb(tmp_path / "v2.deb"), prefix)

    assert not (prefix / "crow.app" / "lib" / "Crow" / "v1.js").exists()
    assert sorted(p.name for p in prefix.iterdir()) == ["bin", "crow.app", "share"]


def test_missing_libraries_fail_before_touching_install(tmp_path, monkeypatch, capsys):
    prefix = tmp_path / "local"
    install_local(make_deb(tmp_path / "v1.deb", {"usr/lib/Crow/v1.js": b""}), prefix)
    monkeypatch.setattr(install, "missing_libraries", lambda _: ["libwebkit2gtk-4.1.so.0"])

    assert install_local(make_deb(tmp_path / "v2.deb"), prefix) is False

    assert "libwebkit2gtk-4.1.so.0" in capsys.readouterr().out
    assert (prefix / "crow.app" / "lib" / "Crow" / "v1.js").exists()
    assert sorted(p.name for p in prefix.iterdir()) == ["bin", "crow.app", "share"]
