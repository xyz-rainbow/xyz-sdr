"""Tests de splash de arranque con líneas de estado."""

from __future__ import annotations

from tui.splash import (
    _phase_percent_from_lines,
    _splash_display_lines,
    _trim_status_line,
)


def test_trim_status_line_short():
    assert _trim_status_line("13:51:26 [INFO] xyz-sdr: ok", 80) == "13:51:26 [INFO] xyz-sdr: ok"


def test_trim_status_line_long():
    line = "13:51:26 [INFO] core.band_profiles: Perfil de banda cargado: fm_broadcast (very long path)"
    trimmed = _trim_status_line(line, 40)
    assert trimmed.endswith("...")
    assert len(trimmed) <= 40


def test_splash_display_lines_prefers_phases():
    lines = [
        "15:23:36 [INFO] core.soapy_runtime: SOAPY plugin path: user dir",
        "Fase: config",
        "Fase: enumerate SDR",
    ]
    assert _splash_display_lines(lines) == ["Fase: config", "Fase: enumerate SDR"]


def test_splash_display_lines_filters_noise():
    lines = [
        "15:23:36 [INFO] core.soapy_runtime: Soapy bundled runtime: Y:\\drivers\\soapy",
        "15:23:36 [INFO] xyz-sdr: Perfil de banda activo: fm_broadcast",
    ]
    shown = _splash_display_lines(lines)
    assert len(shown) == 1
    assert "fm_broadcast" in shown[0]


def test_phase_percent_mapping():
    assert _phase_percent_from_lines(["Fase: config"]) == 25
    assert _phase_percent_from_lines(["Fase: enumerate SDR"]) == 55
    assert _phase_percent_from_lines(["Fase: recovery API"]) == 80
    assert _phase_percent_from_lines(["Fase: listo"]) == 100
