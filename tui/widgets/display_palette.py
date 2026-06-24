"""
xyz-sdr | tui/widgets/display_palette.py
Paleta térmica compartida entre espectro y waterfall.
"""

from __future__ import annotations

import numpy as np

from textual.widget import Widget

# Gradiente térmico SDR (negro → azul → cian → verde → amarillo → rojo → blanco)
THERMAL_GRADIENT: tuple[str, ...] = (
    "#000000",
    "#01010b",
    "#020216",
    "#040422",
    "#060630",
    "#080840",
    "#0a0a52",
    "#0d0d66",
    "#10107c",
    "#111193",
    "#0d36a8",
    "#0a5dbd",
    "#0683d1",
    "#00aeff",
    "#00c2db",
    "#00d6b0",
    "#00eb82",
    "#00ff4c",
    "#5dfc30",
    "#a3f915",
    "#e2f600",
    "#ffff00",
    "#ffd000",
    "#ffa000",
    "#ff6a00",
    "#ff3700",
    "#ff0000",
    "#e6004c",
    "#cc007c",
    "#d900b3",
    "#ff00ff",
    "#ffffff",
)

_OUT_OF_BAND_MIX = 0.35
_OUT_OF_BAND_BG = "#0a0a12"


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"


def lerp_rgb(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    return _rgb_to_hex(
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    )


def gradient_color(norm: float, *, gradient: tuple[str, ...] = THERMAL_GRADIENT) -> str:
    """Interpola linealmente entre paradas del gradiente."""
    norm = max(0.0, min(1.0, norm))
    stops = len(gradient) - 1
    if stops <= 0:
        return gradient[0]
    idx_f = norm * stops
    idx_lo = int(idx_f)
    idx_hi = min(idx_lo + 1, stops)
    if idx_lo == idx_hi:
        return gradient[idx_lo]
    return lerp_rgb(gradient[idx_lo], gradient[idx_hi], idx_f - idx_lo)


# Pre-computar tablas de búsqueda (LUT) de 256 colores para in-band y out-of-band
_IN_BAND_LUT = [gradient_color(i / 255.0) for i in range(256)]
_OUT_OF_BAND_LUT = [lerp_rgb(_OUT_OF_BAND_BG, color, _OUT_OF_BAND_MIX) for color in _IN_BAND_LUT]


def cell_background(norm: float, *, in_band: bool) -> str:
    """Retorna el color de fondo usando la tabla de búsqueda rápida (LUT)."""
    idx = int(norm * 255.0)
    idx = max(0, min(255, idx))
    return _IN_BAND_LUT[idx] if in_band else _OUT_OF_BAND_LUT[idx]


def compute_auto_levels(
    values: np.ndarray,
    *,
    low_pct: float = 5.0,
    high_pct: float = 99.0,
    min_range_db: float = 6.0,
    fallback: tuple[float, float] = (-80.0, -20.0),
) -> tuple[float, float]:
    valid = values[~np.isnan(values)] if values.size else np.array([], dtype=np.float64)
    if len(valid) == 0:
        return fallback

    lo = float(np.percentile(valid, low_pct))
    hi = float(np.percentile(valid, high_pct))
    if hi - lo < min_range_db:
        mid = (hi + lo) / 2.0
        half = min_range_db / 2.0
        lo = mid - half
        hi = mid + half
    return lo, hi


def normalize_columns(
    col_values: np.ndarray,
    level_min: float,
    level_max: float,
) -> np.ndarray:
    """Normaliza columnas a [0, 1] con un solo min/max global; NaN permanece."""
    floor = np.full(len(col_values), float(level_min), dtype=np.float64)
    ceiling = np.full(len(col_values), float(level_max), dtype=np.float64)
    return normalize_per_column(col_values, floor, ceiling)


def normalize_per_column(
    col_values: np.ndarray,
    floor: np.ndarray,
    ceiling: np.ndarray,
) -> np.ndarray:
    """Normaliza cada columna con su propio suelo/techo en dB."""
    n = len(col_values)
    norms = np.full(n, np.nan, dtype=np.float64)
    floor = np.asarray(floor, dtype=np.float64).reshape(-1)[:n]
    ceiling = np.asarray(ceiling, dtype=np.float64).reshape(-1)[:n]
    if len(floor) < n:
        floor = np.pad(floor, (0, n - len(floor)), constant_values=floor[-1] if len(floor) else -80.0)
    if len(ceiling) < n:
        ceiling = np.pad(ceiling, (0, n - len(ceiling)), constant_values=ceiling[-1] if len(ceiling) else -20.0)

    valid = ~np.isnan(col_values)
    if not valid.any():
        return norms

    rng = ceiling - floor
    rng = np.where(rng <= 0, 1.0, rng)
    norms[valid] = np.clip((col_values[valid] - floor[valid]) / rng[valid], 0.0, 1.0)
    return norms


def plot_content_width(widget: Widget) -> int:
    """Ancho util para mapeo frecuencia→columna (alineado entre widgets)."""
    try:
        width = int(widget.content_region.width)
        if width > 0:
            return width
    except Exception:
        pass
    return max(int(widget.size.width), 1)
