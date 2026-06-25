"""Tests de splash de arranque con líneas de estado."""

from __future__ import annotations

from tui.splash import _trim_status_line


def test_trim_status_line_short():
    assert _trim_status_line("13:51:26 [INFO] xyz-sdr: ok", 80) == "13:51:26 [INFO] xyz-sdr: ok"


def test_trim_status_line_long():
    line = "13:51:26 [INFO] core.band_profiles: Perfil de banda cargado: fm_broadcast (very long path)"
    trimmed = _trim_status_line(line, 40)
    assert trimmed.endswith("...")
    assert len(trimmed) <= 40
