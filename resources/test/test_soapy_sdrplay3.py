"""Tests de setup/soapy_sdrplay3.py (sin compilar)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from setup.soapy_sdrplay3 import (
    BUNDLED_DIR,
    BUNDLED_DLL_NAME,
    BUNDLED_MANIFEST,
    bundled_dll_path,
    command_available,
    install_bundled_soapy_sdrplay3,
    install_soapy_sdrplay3_if_needed,
    needs_soapy_sdrplay3_build,
    publish_bundled_dll,
)


def test_needs_build_when_plugin_missing():
    with patch("setup.soapy_sdrplay3.is_sdrplay_soapy_module_ok", return_value=False), patch(
        "setup.soapy_sdrplay3.check_sdrplay_plugin", return_value=False
    ), patch("setup.soapy_sdrplay3.bootstrap_soapy") as boot, patch(
        "setup.soapy_sdrplay3.assess_sdrplay_soapy_module", return_value="missing"
    ):
        boot.return_value = MagicMock(sdrplay_plugin_module=None)
        assert needs_soapy_sdrplay3_build() is True


def test_needs_build_false_when_plugin_ok():
    with patch("setup.soapy_sdrplay3.check_sdrplay_plugin", return_value=True):
        assert needs_soapy_sdrplay3_build() is False


def test_install_skips_when_not_needed():
    messages: list[str] = []

    with patch("setup.soapy_sdrplay3.needs_soapy_sdrplay3_build", return_value=False):
        ok = install_soapy_sdrplay3_if_needed("/tmp", say=messages.append, force=False)
    assert ok is True
    assert any("operativo" in m for m in messages)


def test_install_uses_bundled_before_build(tmp_path):
    messages: list[str] = []
    with patch("setup.soapy_sdrplay3.install_bundled_soapy_sdrplay3", return_value=True) as bundled, patch(
        "setup.soapy_sdrplay3.build_and_install_soapy_sdrplay3"
    ) as build, patch("core.soapy_runtime.check_sdrplay_api", return_value=True), patch(
        "setup.soapy_sdrplay3.find_pothos_install", return_value="C:/Pothos"
    ):
        ok = install_soapy_sdrplay3_if_needed(str(tmp_path), say=messages.append, force=True)
    assert ok is True
    bundled.assert_called_once()
    build.assert_not_called()


def test_bundled_dll_path_with_manifest(tmp_path, monkeypatch):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    monkeypatch.setattr("core.driver_runtime.bundled_plugins_dir", lambda root=None: plugins)
    monkeypatch.setattr(
        "core.driver_runtime.bundled_manifest_path", lambda root=None: tmp_path / "manifest.json"
    )
    monkeypatch.setattr("core.driver_runtime.legacy_bundled_plugins_dir", lambda root=None: legacy)
    dll = plugins / BUNDLED_DLL_NAME
    dll.write_bytes(b"x" * 40_000)
    manifest = {
        "size_bytes": 40_000,
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    # sha mismatch -> None
    assert bundled_dll_path() is None

    import hashlib

    manifest["sha256"] = hashlib.sha256(dll.read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert bundled_dll_path() == dll


def test_publish_bundled_dll(tmp_path, monkeypatch):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    monkeypatch.setattr("core.driver_runtime.bundled_plugins_dir", lambda root=None: plugins)
    monkeypatch.setattr(
        "core.driver_runtime.bundled_manifest_path", lambda root=None: tmp_path / "manifest.json"
    )
    monkeypatch.setattr(
        "core.driver_runtime.legacy_bundled_plugins_dir",
        lambda root=None: tmp_path / "legacy",
    )
    source = tmp_path / "built.dll"
    source.write_bytes(b"new-plugin-bytes-here" * 2000)
    messages: list[str] = []
    assert publish_bundled_dll(source, say=messages.append, source_commit="abc123") is True
    assert (plugins / BUNDLED_DLL_NAME).is_file()
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_commit"] == "abc123"
    assert manifest["size_bytes"] == (plugins / BUNDLED_DLL_NAME).stat().st_size


def test_command_available_git():
    assert command_available("python") is True
    assert command_available("xyz-sdr-nonexistent-tool-12345") is False
