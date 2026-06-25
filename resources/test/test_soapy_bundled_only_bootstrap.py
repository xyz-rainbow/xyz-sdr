"""Tests de bootstrap bundled-only (sin plugins Pothos)."""

from __future__ import annotations

import core.soapy_runtime as soapy_runtime
from core.soapy_runtime import bootstrap_soapy


def test_bootstrap_sets_plugin_present_bundled_only(tmp_path, monkeypatch):
    soapy_dir = tmp_path / "drivers" / "win-x64" / "soapy"
    soapy_dir.mkdir(parents=True)
    (soapy_dir / "SoapySDR.dll").write_bytes(b"soapy" * 5000)

    bundled_plugins = tmp_path / "drivers" / "win-x64" / "plugins"
    bundled_plugins.mkdir(parents=True)
    bundled_mod = bundled_plugins / "sdrPlaySupport.dll"
    bundled_mod.write_bytes(b"plugin" * 4000)

    monkeypatch.setattr("core.driver_runtime.bundled_soapy_dll_dir", lambda root=None: soapy_dir)
    monkeypatch.setattr("core.driver_runtime.bundled_plugins_dir", lambda root=None: bundled_plugins)
    monkeypatch.setattr(
        "core.driver_runtime.bundled_manifest_path",
        lambda root=None: tmp_path / "drivers" / "win-x64" / "manifest.json",
    )
    monkeypatch.setattr("core.driver_runtime.resolve_bundled_sdrplay_plugin", lambda **kwargs: bundled_mod)
    monkeypatch.setattr("core.soapy_runtime.find_pothos_install", lambda: str(tmp_path / "pothos"))
    monkeypatch.setattr("core.soapy_runtime.check_sdrplay_api", lambda: True)
    monkeypatch.setattr("core.soapy_runtime.sync_sdrplay_api_dll_to_pothos", lambda *a, **k: False)
    monkeypatch.setattr("core.soapy_runtime._prepend_path", lambda *a, **k: None)
    monkeypatch.setattr("core.soapy_runtime._register_dll_directory", lambda *a, **k: None)
    monkeypatch.setattr("core.soapy_runtime._prepend_sys_path", lambda *a, **k: None)
    monkeypatch.setattr("core.soapy_runtime._python_site_packages", lambda *a, **k: None)

    import sys
    import types

    fake_soapy = types.ModuleType("SoapySDR")
    fake_soapy.Device = types.SimpleNamespace(enumerate=lambda: [])
    monkeypatch.setitem(sys.modules, "SoapySDR", fake_soapy)
    monkeypatch.setattr("core.soapy_runtime.check_sdrplay_plugin", lambda: True)
    monkeypatch.setenv("XYZ_SDR_ALLOW_POTHOS_PLUGINS", "0")

    soapy_runtime._bootstrap_done = False
    soapy_runtime._last_status = None

    status = bootstrap_soapy(force=True)
    assert status.sdrplay_plugin_status == "present"
    assert status.sdrplay_plugin_module is not None
