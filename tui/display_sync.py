"""
xyz-sdr | tui/display_sync.py
Sincronización compartida espectro/waterfall (app principal + harness).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from core.band_buffer import BandFrame, slice_band_to_viewport
from core.display_levels import ColumnLevelTracker
from tui.widgets.display_palette import compute_auto_levels
from tui.widgets.spectrum_graph import SpectrumGraph
from tui.widgets.waterfall_timeline import WaterfallTimeline


@dataclass
class DisplayLevelState:
    waterfall_auto_level: bool
    display_level_mode: str
    level_tracker: ColumnLevelTracker


@dataclass
class DisplayFrameContext:
    viewport_center: float
    visible_span: float
    passband_center_hz: float
    passband_width_hz: float
    passband_preview_width_hz: float | None
    display_width: int


def compute_column_levels(
    cols: np.ndarray,
    display_cfg: dict,
    state: DisplayLevelState,
) -> tuple[np.ndarray, np.ndarray]:
    """Calcula suelo/techo por columna (per-column o global)."""
    width = len(cols)
    min_range_db = float(display_cfg.get("waterfall_min_range_db", 6.0))
    low_pct = float(display_cfg.get("waterfall_level_low_pct", 5))
    high_pct = float(display_cfg.get("waterfall_level_high_pct", 99))

    if not state.waterfall_auto_level:
        return np.full(width, -80.0), np.full(width, -20.0)

    if state.display_level_mode == "per_column":
        if state.level_tracker.width != width:
            state.level_tracker.reconfigure(width, reset=True)
        state.level_tracker.push_viewport_row(cols)
        state.level_tracker.update(cols)
        return state.level_tracker.floors, state.level_tracker.ceilings

    level_min, level_max = compute_auto_levels(
        cols,
        low_pct=low_pct,
        high_pct=high_pct,
        min_range_db=min_range_db,
    )
    return np.full(width, level_min), np.full(width, level_max)


def apply_band_frame_to_widgets(
    frame: BandFrame,
    snr: float,
    seq: int,
    *,
    spectrum: SpectrumGraph | None,
    waterfall: WaterfallTimeline | None,
    ctx: DisplayFrameContext,
    display_cfg: dict,
    level_state: DisplayLevelState,
    scanner_step: Callable[[BandFrame, float, np.ndarray, np.ndarray], None] | None = None,
) -> tuple[int, np.ndarray | None]:
    """Renderiza un frame en widgets de visualización. Devuelve (seq, viewport_cols)."""

    plot_width = max(int(ctx.display_width), 1)
    if spectrum is not None:
        plot_width = max(plot_width, spectrum._column_width())

    cols = slice_band_to_viewport(
        frame.band_cols,
        frame.center_hz,
        frame.sample_rate,
        ctx.viewport_center,
        ctx.visible_span,
        plot_width,
    )

    floors, ceilings = compute_column_levels(cols, display_cfg, level_state)

    if scanner_step is not None:
        scanner_step(frame, snr, floors, ceilings)

    if spectrum is not None:
        spectrum.set_viewport(ctx.viewport_center, ctx.visible_span)
        spectrum.passband_center_hz = ctx.passband_center_hz
        spectrum.passband_width_hz = ctx.passband_width_hz
        spectrum.passband_preview_width_hz = ctx.passband_preview_width_hz
        spectrum.set_column_levels(floors, ceilings)
        spectrum.set_band_frame(frame, force=True)
        spectrum.set_viewport_cols(cols)

    if waterfall is not None:
        waterfall.set_viewport(ctx.viewport_center, ctx.visible_span)
        waterfall.passband_center_hz = ctx.passband_center_hz
        waterfall.passband_width_hz = ctx.passband_width_hz
        waterfall.passband_preview_width_hz = ctx.passband_preview_width_hz
        waterfall.set_column_levels(floors, ceilings)
        waterfall.add_viewport_row(cols, frame)

    return seq, cols
