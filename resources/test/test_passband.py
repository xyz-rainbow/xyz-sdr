"""Tests for core/passband.py -- passband widths, clamping and pixel conversions."""

from __future__ import annotations

import pytest

from core.passband import (
    PASSBAND_DEFAULTS,
    PASSBAND_LIMITS,
    clamp_passband_width,
    col_to_freq,
    default_passband_width,
    freq_to_col,
    passband_limits,
    symmetric_width_from_drag,
)


@pytest.mark.parametrize("mode", list(PASSBAND_DEFAULTS))
def test_default_passband_width_known_modes(mode: str) -> None:
    assert default_passband_width(mode) == PASSBAND_DEFAULTS[mode]


def test_default_passband_width_unknown_mode_falls_back() -> None:
    # Unknown mode falls back to the wbfm default (200k).
    assert default_passband_width("totally_unknown_mode") == 200_000.0


@pytest.mark.parametrize("mode", list(PASSBAND_LIMITS))
def test_passband_limits_known_modes(mode: str) -> None:
    lo, hi = passband_limits(mode)
    assert lo > 0
    assert hi > lo


def test_passband_limits_unknown_mode_fallback() -> None:
    lo, hi = passband_limits("nope")
    assert lo == 80_000.0
    assert hi == 250_000.0


def test_clamp_passband_width_inside_range_passthrough() -> None:
    assert clamp_passband_width("wbfm", 150_000.0) == 150_000.0


def test_clamp_passband_width_below_low_clamped() -> None:
    assert clamp_passband_width("wbfm", 1_000.0) == 80_000.0


def test_clamp_passband_width_above_high_clamped() -> None:
    assert clamp_passband_width("wbfm", 1_000_000.0) == 250_000.0


def test_symmetric_width_from_drag_basic() -> None:
    assert symmetric_width_from_drag(100e6, 100.05e6) == pytest.approx(100_000.0)


def test_symmetric_width_from_drag_negative_cursor() -> None:
    assert symmetric_width_from_drag(100e6, 99.95e6) == pytest.approx(100_000.0)


def test_col_to_freq_middle_is_center() -> None:
    freq = col_to_freq(60, widget_width=120, viewport_center_hz=100e6, visible_span_hz=2_048_000)
    assert freq == pytest.approx(100e6)


def test_col_to_freq_zero_is_left_edge() -> None:
    freq = col_to_freq(0, widget_width=120, viewport_center_hz=100e6, visible_span_hz=2_048_000)
    assert freq == pytest.approx(100e6 - 1_024_000)


def test_col_to_freq_invalid_widget_returns_center() -> None:
    freq = col_to_freq(0, widget_width=0, viewport_center_hz=100e6, visible_span_hz=2_048_000)
    assert freq == 100e6


def test_freq_to_col_middle_is_center_widget() -> None:
    col = freq_to_col(100e6, widget_width=120, viewport_center_hz=100e6, visible_span_hz=2_048_000)
    assert col == 60


def test_freq_to_col_left_edge_is_zero() -> None:
    col = freq_to_col(100e6 - 1_024_000, widget_width=120, viewport_center_hz=100e6, visible_span_hz=2_048_000)
    assert col == 0


def test_freq_to_col_clamps_out_of_range() -> None:
    # Way above the visible span -> clamped to widget_width.
    col = freq_to_col(1e9, widget_width=120, viewport_center_hz=100e6, visible_span_hz=2_048_000)
    assert col == 120
    # Way below -> clamped to -1 sentinel (out of range).
    col = freq_to_col(0, widget_width=120, viewport_center_hz=100e6, visible_span_hz=2_048_000)
    assert col == -1


def test_freq_to_col_invalid_widget_returns_middle() -> None:
    col = freq_to_col(100e6, widget_width=0, viewport_center_hz=100e6, visible_span_hz=2_048_000)
    assert col == 0