"""Tests de core/driver_runtime.py."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.driver_runtime import (
    bundled_manifest_path,
    bundled_plugins_dir,
    bundled_soapy_dll_dir,
    bundled_win_x64_dir,
    drivers_root,
    legacy_bundled_plugins_dir,
    load_bundled_manifest,
    resolve_bundled_sdrplay_plugin,
)


def test_drivers_root_layout(tmp_path, monkeypatch):
    monkeypatch.setattr("core.driver_runtime.project_root", lambda: tmp_path)
    assert drivers_root() == tmp_path / "drivers"
    assert bundled_win_x64_dir() == tmp_path / "drivers" / "win-x64"
    assert bundled_plugins_dir() == tmp_path / "drivers" / "win-x64" / "plugins"
    assert legacy_bundled_plugins_dir() == tmp_path / "resources" / "bin" / "win-x64"


def test_resolve_bundled_plugin_prefers_drivers(tmp_path, monkeypatch):
    monkeypatch.setattr("core.driver_runtime.project_root", lambda: tmp_path)
    drivers_plugins = bundled_plugins_dir()
    drivers_plugins.mkdir(parents=True)
    legacy = legacy_bundled_plugins_dir()
    legacy.mkdir(parents=True)

    legacy_dll = legacy / "sdrPlaySupport.dll"
    legacy_dll.write_bytes(b"x" * 40_000)

    drivers_dll = drivers_plugins / "sdrPlaySupport.dll"
    drivers_dll.write_bytes(b"y" * 40_000)

    manifest = {
        "size_bytes": drivers_dll.stat().st_size,
        "sha256": hashlib.sha256(drivers_dll.read_bytes()).hexdigest(),
    }
    bundled_manifest_path().parent.mkdir(parents=True, exist_ok=True)
    bundled_manifest_path().write_text(json.dumps(manifest), encoding="utf-8")

    resolved = resolve_bundled_sdrplay_plugin()
    assert resolved == drivers_dll


def test_resolve_bundled_plugin_falls_back_to_legacy(tmp_path, monkeypatch):
    monkeypatch.setattr("core.driver_runtime.project_root", lambda: tmp_path)
    legacy = legacy_bundled_plugins_dir()
    legacy.mkdir(parents=True)
    dll = legacy / "sdrPlaySupport.dll"
    dll.write_bytes(b"z" * 40_000)
    manifest = {
        "size_bytes": dll.stat().st_size,
        "sha256": hashlib.sha256(dll.read_bytes()).hexdigest(),
    }
    (legacy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    resolved = resolve_bundled_sdrplay_plugin()
    assert resolved == dll


def test_load_bundled_manifest_prefers_drivers(tmp_path, monkeypatch):
    monkeypatch.setattr("core.driver_runtime.project_root", lambda: tmp_path)
    bundled_manifest_path().parent.mkdir(parents=True, exist_ok=True)
    bundled_manifest_path().write_text('{"schema": "drivers"}', encoding="utf-8")
    legacy = legacy_bundled_plugins_dir()
    legacy.mkdir(parents=True)
    (legacy / "manifest.json").write_text('{"schema": "legacy"}', encoding="utf-8")

    manifest = load_bundled_manifest()
    assert manifest is not None
    assert manifest["schema"] == "drivers"


def test_bundled_soapy_dll_dir_none_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("core.driver_runtime.project_root", lambda: tmp_path)
    assert bundled_soapy_dll_dir() is None
