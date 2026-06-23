"""
xyz-sdr | core/passband.py
Ancho de banda audible por modo de demodulación (selección con ratón).
"""

from __future__ import annotations

from typing import Literal

DemodPassbandMode = Literal["wbfm", "nbfm", "am", "usb", "lsb"]

PASSBAND_DEFAULTS: dict[str, float] = {
    "wbfm": 200_000.0,
    "nbfm": 12_500.0,
    "am": 10_000.0,
    "usb": 3_000.0,
    "lsb": 3_000.0,
}

PASSBAND_LIMITS: dict[str, tuple[float, float]] = {
    "wbfm": (80_000.0, 250_000.0),
    "nbfm": (5_000.0, 25_000.0),
    "am": (3_000.0, 15_000.0),
    "usb": (1_500.0, 6_000.0),
    "lsb": (1_500.0, 6_000.0),
}

# Umbral de arrastre en píxeles: por debajo = clic corto (ancho por defecto).
DRAG_PIXEL_THRESHOLD = 5

# Paso de teclado [ ] para ajustar ancho en modos FM/AM.
PASSBAND_KEYBOARD_STEP: dict[str, float] = {
    "wbfm": 10_000.0,
    "nbfm": 2_500.0,
    "am": 1_000.0,
}


def default_passband_width(mode: str) -> float:
    return PASSBAND_DEFAULTS.get(mode, 200_000.0)


def passband_limits(mode: str) -> tuple[float, float]:
    return PASSBAND_LIMITS.get(mode, (80_000.0, 250_000.0))


def clamp_passband_width(mode: str, width_hz: float) -> float:
    lo, hi = passband_limits(mode)
    return max(lo, min(hi, float(width_hz)))


def symmetric_width_from_drag(center_hz: float, cursor_hz: float) -> float:
    """Ancho simétrico: 2 × distancia centro–cursor."""
    return 2.0 * abs(float(cursor_hz) - float(center_hz))


def col_to_freq(
    col: float,
    *,
    widget_width: int,
    viewport_center_hz: float,
    visible_span_hz: float,
) -> float:
    if widget_width <= 0 or visible_span_hz <= 0:
        return viewport_center_hz
    left_hz = viewport_center_hz - visible_span_hz / 2
    return left_hz + (col / widget_width) * visible_span_hz


def freq_to_col(
    freq_hz: float,
    *,
    widget_width: int,
    viewport_center_hz: float,
    visible_span_hz: float,
) -> int:
    if widget_width <= 0 or visible_span_hz <= 0:
        return widget_width // 2
    left_hz = viewport_center_hz - visible_span_hz / 2
    col = int((freq_hz - left_hz) / visible_span_hz * widget_width)
    return max(-1, min(col, widget_width))
