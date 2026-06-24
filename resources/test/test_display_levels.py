"""Tests de auto-level por columna (ColumnLevelTracker)."""

from __future__ import annotations

import numpy as np

from core.display_levels import ColumnLevelTracker
from tui.widgets.display_palette import compute_auto_levels, normalize_per_column


def test_per_column_norm_differs_with_noise_slope():
    """Mismo valor absoluto, distinto suelo local → distinta normalización."""
    width = 4
    tracker = ColumnLevelTracker(
        width=width,
        floor_pct=10,
        ceiling_pct=99,
        min_range_db=6.0,
        attack=1.0,
        release=1.0,
        smooth_bins=1,
    )
    # Ruido bajo a la izquierda, alto a la derecha
    cols = np.array([-50.0, -50.0, -30.0, -30.0])
    history = np.array(
        [
            [-55.0, -54.0, -35.0, -34.0],
            [-56.0, -55.0, -36.0, -35.0],
        ]
    )
    tracker.update(cols, history)
    floors, ceilings = tracker.floors, tracker.ceilings
    norms = normalize_per_column(cols, floors, ceilings)
    # Columnas 0 y 2 tienen el mismo valor absoluto relativo al suelo local
    assert abs(norms[0] - norms[2]) < 0.15
    # Pero el suelo local difiere entre izquierda y derecha
    assert floors[0] < floors[2] - 10


def test_reconfigure_resets_on_width_change():
    tracker = ColumnLevelTracker(width=2, attack=1.0, release=1.0, smooth_bins=1)
    tracker.update(np.array([-40.0, -30.0]))
    assert tracker.width == 2
    tracker.reconfigure(4, reset=True)
    assert tracker.width == 4
    assert not tracker._initialized


def test_min_range_db_prevents_zero_division():
    tracker = ColumnLevelTracker(
        width=3,
        min_range_db=6.0,
        attack=1.0,
        release=1.0,
        smooth_bins=1,
    )
    flat = np.full(3, -50.0)
    tracker.update(flat, flat.reshape(1, -1))
    assert np.all(tracker.ceilings >= tracker.floors + 6.0 - 1e-9)
    norms = normalize_per_column(flat, tracker.floors, tracker.ceilings)
    assert np.all(np.isfinite(norms))


def test_global_mode_constant_arrays():
    cols = np.array([-60.0, -45.0, -30.0, -55.0])
    lo, hi = compute_auto_levels(cols, low_pct=5, high_pct=99, min_range_db=6.0)
    floors = np.full(len(cols), lo)
    ceilings = np.full(len(cols), hi)
    norms = normalize_per_column(cols, floors, ceilings)
    assert len(norms) == len(cols)
    assert np.all((norms >= 0.0) & (norms <= 1.0))


def test_span_ratio_scales_min_range():
    tracker = ColumnLevelTracker(width=2, min_range_db=10.0, smooth_bins=1)
    tracker.set_span_ratio(0.0)
    assert tracker._effective_min_range() == 5.0
    tracker.set_span_ratio(1.0)
    assert tracker._effective_min_range() == 10.0
