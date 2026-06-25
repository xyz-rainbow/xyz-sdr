"""Tests de splash de arranque con líneas de estado."""

from __future__ import annotations

from tui.splash import (
    _phase_progress_window,
    _splash_display_lines,
    _splash_progress_percent,
    _trim_status_line,
)


def test_trim_status_line_short():
    assert _trim_status_line("13:51:26 [INFO] xyz-sdr: ok", 80) == "13:51:26 [INFO] xyz-sdr: ok"


def test_trim_status_line_long():
    line = "13:51:26 [INFO] core.band_profiles: Perfil de banda cargado: fm_broadcast (very long path)"
    trimmed = _trim_status_line(line, 40)
    assert trimmed.endswith("...")
    assert len(trimmed) <= 40


def test_splash_display_lines_shows_only_latest_phase():
    lines = [
        "15:23:36 [INFO] core.soapy_runtime: SOAPY plugin path: user dir",
        "Fase: config",
        "Fase: enumerate SDR",
    ]
    assert _splash_display_lines(lines) == ["Cargando: enumerate SDR…"]


def test_splash_display_lines_filters_noise():
    lines = [
        "15:23:36 [INFO] core.soapy_runtime: Soapy bundled runtime: Y:\\drivers\\soapy",
        "15:23:36 [INFO] xyz-sdr: Perfil de banda activo: fm_broadcast",
    ]
    shown = _splash_display_lines(lines)
    assert len(shown) == 1
    assert "fm_broadcast" in shown[0]


def test_phase_progress_window_mapping():
    assert _phase_progress_window(["Fase: config"]) == (15, 40)
    assert _phase_progress_window(["Fase: enumerate SDR"]) == (45, 78)
    assert _phase_progress_window(["Fase: recovery API"]) == (80, 95)
    assert _phase_progress_window(["Fase: listo"]) == (100, 100)


def test_splash_progress_creeps_during_enumerate():
    lines = ["Fase: enumerate SDR"]
    early = _splash_progress_percent(0.5, lines, thread_alive=True)
    late = _splash_progress_percent(15.0, lines, thread_alive=True)
    assert early >= 45
    assert late > early
    assert late <= 78
