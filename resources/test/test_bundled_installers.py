"""Tests de instaladores offline (SDRplay API)."""

from __future__ import annotations

from pathlib import Path

from setup.bundled_installers import (
    SDRPLAY_INSTALLER_FILENAME,
    acquire_sdrplay_installer,
    bundled_sdrplay_installer_path,
    local_sdrplay_installer_candidates,
)


def test_bundled_sdrplay_installer_with_manifest(tmp_path, monkeypatch):
    bundle_dir = tmp_path / "resources" / "installers" / "win-x64"
    bundle_dir.mkdir(parents=True)
    dll = bundle_dir / SDRPLAY_INSTALLER_FILENAME
    dll.write_bytes(b"fake-installer")

    import hashlib

    sha = hashlib.sha256(b"fake-installer").hexdigest()
    (bundle_dir / "manifest.json").write_text(
        f'{{"size_bytes": {len(b"fake-installer")}, "sha256": "{sha}"}}',
        encoding="utf-8",
    )

    monkeypatch.setattr("setup.bundled_installers.BUNDLED_INSTALLERS_DIR", bundle_dir)
    monkeypatch.setattr("setup.bundled_installers.BUNDLED_SDRPLAY_MANIFEST", bundle_dir / "manifest.json")

    path = bundled_sdrplay_installer_path()
    assert path == dll


def test_acquire_prefers_bundled_over_download(tmp_path, monkeypatch):
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    installer = bundle_dir / SDRPLAY_INSTALLER_FILENAME
    installer.write_bytes(b"x")

    monkeypatch.setattr(
        "setup.bundled_installers.bundled_sdrplay_installer_path",
        lambda **kwargs: installer,
    )
    monkeypatch.setattr(
        "setup.bundled_installers.download_file",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not download")),
    )

    messages: list[str] = []
    got = acquire_sdrplay_installer(str(tmp_path / "temp"), on_message=messages.append)
    assert got == str(installer.resolve())
    assert any("embebido" in m for m in messages)


def test_acquire_uses_env_installer(tmp_path, monkeypatch):
    monkeypatch.setattr("setup.bundled_installers.bundled_sdrplay_installer_path", lambda **k: None)
    custom = tmp_path / SDRPLAY_INSTALLER_FILENAME
    custom.write_bytes(b"x")
    monkeypatch.setenv("XYZ_SDR_SDRPLAY_INSTALLER", str(custom))

    got = acquire_sdrplay_installer(str(tmp_path), on_message=lambda _m: None)
    assert got == str(custom.resolve())
