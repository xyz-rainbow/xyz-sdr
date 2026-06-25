"""Tests de rutas de reparación SDRplay."""

from __future__ import annotations

from core.sdrplay_repair import (
    sdrplay_api_installer_hint,
    sdrplay_api_repair_recommendations,
    volk_warning_is_benign,
)


def test_repair_recommendations_include_local_installer():
    recs = sdrplay_api_repair_recommendations()
    assert any("install_sdrplay_api.bat" in r for r in recs)
    assert any("install_drivers.ps1" in r for r in recs)


def test_volk_warning_is_benign():
    assert volk_warning_is_benign("[WARNING] SoapyVOLKConverters: no VOLK config file found.")
    assert not volk_warning_is_benign("SEGFAULT in setupStream")
