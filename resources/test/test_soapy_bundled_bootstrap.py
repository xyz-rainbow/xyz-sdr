"""Tests de bootstrap Soapy con drivers/win-x64 bundled."""

from __future__ import annotations

import os

from core.soapy_runtime import _configure_soapy_plugin_path


def test_configure_uses_bundled_when_user_missing(tmp_path, monkeypatch):
    pothos = tmp_path / "pothos"
    mod_dir = pothos / "lib" / "SoapySDR" / "modules0.8"
    mod_dir.mkdir(parents=True)

    bundled_plugins = tmp_path / "drivers" / "win-x64" / "plugins"
    bundled_plugins.mkdir(parents=True)
    bundled_mod = bundled_plugins / "sdrPlaySupport.dll"
    bundled_mod.write_bytes(b"ok-bundled" * 4000)

    user_dir = tmp_path / "user" / "SoapySDR" / "modules0.8"
    user_dir.mkdir(parents=True)

    monkeypatch.setattr("core.soapy_runtime.user_soapy_plugin_dir", lambda: str(user_dir))
    monkeypatch.setattr("core.driver_runtime.bundled_plugins_dir", lambda root=None: bundled_plugins)
    monkeypatch.setattr(
        "core.driver_runtime.bundled_manifest_path",
        lambda root=None: tmp_path / "drivers" / "win-x64" / "manifest.json",
    )
    monkeypatch.setattr(
        "core.driver_runtime.legacy_bundled_plugins_dir",
        lambda root=None: tmp_path / "resources" / "bin" / "win-x64",
    )
    monkeypatch.setenv("SOAPY_SDR_PLUGIN_PATH", "")

    _configure_soapy_plugin_path(str(pothos))
    plugin_path = os.environ.get("SOAPY_SDR_PLUGIN_PATH", "")
    assert str(bundled_plugins) in plugin_path
