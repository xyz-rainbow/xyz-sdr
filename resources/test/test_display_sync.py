"""Tests de tui/display_sync.py (niveles por columna)."""

from __future__ import annotations

import numpy as np

from core.display_levels import ColumnLevelTracker
from tui.display_sync import (
    DisplayFrameContext,
    DisplayLevelState,
    compute_column_levels,
)


def _state(*, auto: bool = True, mode: str = "global") -> DisplayLevelState:
    return DisplayLevelState(
        waterfall_auto_level=auto,
        display_level_mode=mode,
        level_tracker=ColumnLevelTracker(width=4),
    )


def test_compute_column_levels_disabled_returns_fixed():
    """Cuando waterfall_auto_level=False devuelve -80/-20 fijos."""
    state = _state(auto=False)
    cols = np.linspace(-90, -10, 50)
    floors, ceilings = compute_column_levels(cols, {}, state)
    assert floors.shape == (50,)
    assert ceilings.shape == (50,)
    assert np.all(floors == -80.0)
    assert np.all(ceilings == -20.0)


def test_compute_column_levels_global_mode_uses_pct():
    """display_level_mode='global' usa compute_auto_levels."""
    state = _state(mode="global")
    cols = np.array([-90, -70, -50, -30, -10] * 10, dtype=np.float32)
    cfg = {
        "waterfall_min_range_db": 6.0,
        "waterfall_level_low_pct": 5,
        "waterfall_level_high_pct": 95,
    }
    floors, ceilings = compute_column_levels(cols, cfg, state)
    assert floors.shape == (50,)
    assert ceilings.shape == (50,)
    # El rango debe respetar min_range_db
    assert (ceilings - floors).min() >= 6.0 - 1e-6


def test_compute_column_levels_per_column_uses_tracker():
    """display_level_mode='per_column' usa el tracker."""
    state = _state(mode="per_column")
    state.level_tracker = ColumnLevelTracker(width=20)
    cols = np.linspace(-90, -10, 20, dtype=np.float32)
    cfg = {"waterfall_min_range_db": 6.0, "waterfall_level_low_pct": 5, "waterfall_level_high_pct": 95}
    floors, ceilings = compute_column_levels(cols, cfg, state)
    assert floors.shape == (20,)
    assert ceilings.shape == (20,)


def test_compute_column_levels_per_column_resizes_tracker():
    """Si cambia el ancho, el tracker se reconfigura."""
    state = _state(mode="per_column")
    state.level_tracker = ColumnLevelTracker(width=10)
    cols = np.linspace(-90, -10, 30, dtype=np.float32)
    cfg = {"waterfall_min_range_db": 6.0, "waterfall_level_low_pct": 5, "waterfall_level_high_pct": 95}
    floors, ceilings = compute_column_levels(cols, cfg, state)
    assert state.level_tracker.width == 30
    assert floors.shape == (30,)


def test_compute_column_levels_uses_default_config_when_empty():
    """Sin cfg, usa defaults sensatos (6dB min, 5/99 pct)."""
    state = _state(mode="global")
    cols = np.array([-90, -70, -50, -30, -10] * 4, dtype=np.float32)
    floors, ceilings = compute_column_levels(cols, {}, state)
    assert (ceilings - floors).min() >= 6.0 - 1e-6


def test_display_frame_context_construction():
    ctx = DisplayFrameContext(
        viewport_center=7_100_000.0,
        visible_span=250_000.0,
        passband_center_hz=7_100_000.0,
        passband_width_hz=12_500.0,
        passband_preview_width_hz=None,
        display_width=80,
    )
    assert ctx.viewport_center == 7_100_000.0
    assert ctx.passband_preview_width_hz is None
    assert ctx.display_width == 80


def test_display_level_state_construction():
    state = DisplayLevelState(
        waterfall_auto_level=True,
        display_level_mode="per_column",
        level_tracker=ColumnLevelTracker(width=4),
    )
    assert state.waterfall_auto_level is True
    assert state.display_level_mode == "per_column"
    assert state.level_tracker.width == 4


def test_compute_column_levels_pct_extremes():
    """high_pct=99, low_pct=5 sobre señal uniforme da techo/suelo distintos."""
    state = _state(mode="global")
    cols = np.full(20, -50.0, dtype=np.float32)
    cfg = {"waterfall_min_range_db": 6.0, "waterfall_level_low_pct": 5, "waterfall_level_high_pct": 99}
    floors, ceilings = compute_column_levels(cols, cfg, state)
    # Uniforme: low/high pct ≈ mismo valor → min_range_db fuerza separación mínima
    assert (ceilings - floors).min() >= 6.0 - 1e-6


def test_compute_column_levels_clamps_range_with_min_range():
    """Si low_pct y high_pct coinciden, se fuerza min_range_db."""
    state = _state(mode="global")
    cols = np.full(20, -50.0, dtype=np.float32)
    cfg = {"waterfall_min_range_db": 20.0, "waterfall_level_low_pct": 50, "waterfall_level_high_pct": 50}
    floors, ceilings = compute_column_levels(cols, cfg, state)
    # Misma entrada → low==high → rango forzado a 20 dB
    assert np.allclose(ceilings - floors, 20.0)


def test_compute_column_levels_config_overrides():
    """Config custom sobrescribe defaults."""
    state = _state(mode="global")
    cols = np.linspace(-90, -10, 40, dtype=np.float32)
    cfg = {"waterfall_min_range_db": 12.0, "waterfall_level_low_pct": 10, "waterfall_level_high_pct": 90}
    floors, ceilings = compute_column_levels(cols, cfg, state)
    assert (ceilings - floors).min() >= 12.0 - 1e-6