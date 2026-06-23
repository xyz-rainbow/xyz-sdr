"""Tests de selección de banda audible (passband)."""

from __future__ import annotations

from core.passband import (
    DRAG_PIXEL_THRESHOLD,
    clamp_passband_width,
    col_to_freq,
    default_passband_width,
    freq_to_col,
    symmetric_width_from_drag,
)


def test_col_to_freq_roundtrip():
    center = 100_600_000.0
    span = 2_048_000.0
    width = 120
    col = 60
    freq = col_to_freq(col, widget_width=width, viewport_center_hz=center, visible_span_hz=span)
    back = freq_to_col(freq, widget_width=width, viewport_center_hz=center, visible_span_hz=span)
    assert abs(back - col) <= 1


def test_symmetric_width_from_drag():
    center = 100_600_000.0
    cursor = 100_700_000.0
    assert symmetric_width_from_drag(center, cursor) == 200_000.0


def test_clamp_passband_wbfm():
    assert clamp_passband_width("wbfm", 50_000) == 80_000
    assert clamp_passband_width("wbfm", 200_000) == 200_000
    assert clamp_passband_width("wbfm", 400_000) == 250_000


def test_default_passband_by_mode():
    assert default_passband_width("wbfm") == 200_000
    assert default_passband_width("nbfm") == 12_500


def test_drag_pixel_threshold_sensible():
    assert DRAG_PIXEL_THRESHOLD >= 3
