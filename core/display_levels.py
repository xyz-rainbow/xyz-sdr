"""
xyz-sdr | core/display_levels.py
Auto-level por columna de frecuencia para espectro y waterfall.
"""

from __future__ import annotations

import numpy as np


def _smooth_1d(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1 or len(values) < 2:
        return values
    window = min(window, len(values))
    if window % 2 == 0:
        window += 1
    kernel = np.ones(window, dtype=np.float64) / window
    padded = np.pad(values, (window // 2, window // 2), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def _asymmetric_ema(
    current: np.ndarray,
    target: np.ndarray,
    *,
    attack: float,
    release: float,
    lower_is_fast: bool,
) -> np.ndarray:
    """EMA por columna: attack cuando el target va en la dirección indicada."""
    attack = float(np.clip(attack, 0.0, 1.0))
    release = float(np.clip(release, 0.0, 1.0))
    if lower_is_fast:
        blend = np.where(target < current, attack, release)
    else:
        blend = np.where(target > current, attack, release)
    return (1.0 - blend) * current + blend * target


class ColumnLevelTracker:
    """Suelo y techo dinámicos por columna (display AGC por frecuencia)."""

    def __init__(
        self,
        width: int = 1,
        *,
        floor_pct: float = 10.0,
        ceiling_pct: float = 99.0,
        min_range_db: float = 6.0,
        attack: float = 0.35,
        release: float = 0.08,
        smooth_bins: int = 3,
        history_rows: int = 32,
        fallback_floor: float = -80.0,
        fallback_ceiling: float = -20.0,
    ):
        self._floor_pct = float(floor_pct)
        self._ceiling_pct = float(ceiling_pct)
        self._min_range_db = float(min_range_db)
        self._attack = float(attack)
        self._release = float(release)
        self._smooth_bins = max(1, int(smooth_bins))
        self._history_rows = max(1, int(history_rows))
        self._fallback_floor = float(fallback_floor)
        self._fallback_ceiling = float(fallback_ceiling)
        self._span_ratio = 1.0
        self._initialized = False
        self.reconfigure(width, reset=True)

    @property
    def width(self) -> int:
        return len(self._floor)

    @property
    def floors(self) -> np.ndarray:
        return self._floor

    @property
    def ceilings(self) -> np.ndarray:
        return self._ceiling

    def set_span_ratio(self, ratio: float) -> None:
        self._span_ratio = float(np.clip(ratio, 0.0, 1.0))

    def _effective_min_range(self) -> float:
        return self._min_range_db * (0.5 + 0.5 * self._span_ratio)

    def reconfigure(self, width: int, *, reset: bool = False) -> None:
        width = max(int(width), 1)
        if hasattr(self, "_floor") and width == len(self._floor) and not reset:
            return
        self._floor = np.full(width, self._fallback_floor, dtype=np.float64)
        self._ceiling = np.full(width, self._fallback_ceiling, dtype=np.float64)
        self._initialized = False

    def update(
        self,
        cols: np.ndarray,
        history_2d: np.ndarray | None = None,
    ) -> None:
        width = len(self._floor)
        if width <= 0:
            return

        cols = np.asarray(cols, dtype=np.float64).reshape(-1)
        if len(cols) < width:
            cols = np.pad(cols, (0, width - len(cols)), constant_values=np.nan)
        cols = cols[:width]

        blocks = [cols.reshape(1, -1)]
        if history_2d is not None:
            hist = np.asarray(history_2d, dtype=np.float64)
            if hist.ndim == 2 and hist.shape[1] == width and hist.shape[0] > 0:
                blocks.append(hist[-self._history_rows :])

        data = np.vstack(blocks)
        target_floor = np.nanpercentile(data, self._floor_pct, axis=0)
        target_ceil = np.nanpercentile(data, self._ceiling_pct, axis=0)

        valid = ~np.isnan(cols)
        target_floor = np.where(valid, np.minimum(target_floor, cols), target_floor)
        target_ceil = np.where(valid, np.maximum(target_ceil, cols), target_ceil)

        min_range = self._effective_min_range()
        target_ceil = np.maximum(target_ceil, target_floor + min_range)

        if not self._initialized:
            self._floor = target_floor.copy()
            self._ceiling = target_ceil.copy()
            self._initialized = True
        else:
            self._floor = _asymmetric_ema(
                self._floor,
                target_floor,
                attack=self._attack,
                release=self._release,
                lower_is_fast=True,
            )
            self._ceiling = _asymmetric_ema(
                self._ceiling,
                target_ceil,
                attack=self._attack,
                release=self._release,
                lower_is_fast=False,
            )
            self._ceiling = np.maximum(self._ceiling, self._floor + min_range)

        if self._smooth_bins > 1:
            self._floor = _smooth_1d(self._floor, self._smooth_bins)
            self._ceiling = _smooth_1d(self._ceiling, self._smooth_bins)
            self._ceiling = np.maximum(self._ceiling, self._floor + min_range)
