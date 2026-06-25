"""Tests de prioridad plugin Soapy (legacy Pothos vs usuario)."""

from __future__ import annotations

import os

from core.soapy_runtime import _configure_soapy_plugin_path, assess_sdrplay_soapy_module


def test_assess_legacy_by_mtime(tmp_path):
    legacy = tmp_path / "sdrPlaySupport.dll"
    legacy.write_bytes(b"x")
    old = 1_600_000_000.0
    os.utime(legacy, (old, old))
    assert assess_sdrplay_soapy_module(str(legacy)) == "legacy"


def test_configure_skips_legacy_pothos_when_user_present(tmp_path, monkeypatch):
    pothos = tmp_path / "pothos"
    mod_dir = pothos / "lib" / "SoapySDR" / "modules0.8"
    mod_dir.mkdir(parents=True)

    legacy = mod_dir / "sdrPlaySupport.dll"
    legacy.write_bytes(b"legacy")
    old = 1_600_000_000.0
    os.utime(legacy, (old, old))

    user_dir = tmp_path / "user" / "SoapySDR" / "modules0.8"
    user_dir.mkdir(parents=True)
    user_mod = user_dir / "sdrPlaySupport.dll"
    user_mod.write_bytes(b"ok")

    monkeypatch.setattr("core.soapy_runtime.user_soapy_plugin_dir", lambda: str(user_dir))
    monkeypatch.setenv("SOAPY_SDR_PLUGIN_PATH", "")

    _configure_soapy_plugin_path(str(pothos))
    plugin_path = os.environ.get("SOAPY_SDR_PLUGIN_PATH", "")
    assert str(user_dir) in plugin_path
    assert str(mod_dir) not in plugin_path
