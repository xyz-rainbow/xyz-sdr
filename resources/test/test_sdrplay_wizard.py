"""Tests del wizard SDRplay y plugin bundled."""

from __future__ import annotations

from core.sdrplay_wizard import collect_sdrplay_wizard_snapshot, format_wizard_lines


def test_wizard_reports_bundled_plugin_present(tmp_path, monkeypatch):
    bundled_plugins = tmp_path / "drivers" / "win-x64" / "plugins"
    bundled_plugins.mkdir(parents=True)
    bundled_mod = bundled_plugins / "sdrPlaySupport.dll"
    bundled_mod.write_bytes(b"ok-bundled-plugin" * 4000)

    class _Status:
        pothos_root = None
        devices = []
        sdrplay_plugin_module = None
        sdrplay_plugin_status = "missing"

    monkeypatch.setattr(
        "core.sdrplay_wizard.bootstrap_soapy",
        lambda **kwargs: _Status(),
    )
    monkeypatch.setattr("core.sdrplay_wizard.sdrplay_find_ok", lambda **kwargs: False)
    monkeypatch.setattr("core.sdrplay_wizard.check_sdrplay_service_running", lambda: True)
    monkeypatch.setattr(
        "core.sdrplay_wizard.resolve_bundled_sdrplay_plugin",
        lambda **kwargs: bundled_mod,
    )
    monkeypatch.setattr("core.sdrplay_wizard.assess_sdrplay_soapy_module", lambda path: "present")

    snapshot = collect_sdrplay_wizard_snapshot(attempt_recover=False)
    lines = format_wizard_lines(snapshot)
    assert snapshot.plugin_status == "present"
    assert any("Plugin: present" in line for line in lines)
