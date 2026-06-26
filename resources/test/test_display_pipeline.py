"""Tests del pipeline espectro/waterfall tras frames RX."""

from __future__ import annotations

import time

import numpy as np

from core.band_buffer import BandFrame, slice_band_to_viewport
from tui.widgets.spectrum_graph import SpectrumGraph
from tui.widgets.waterfall_timeline import WaterfallTimeline


def _sample_frame() -> BandFrame:
    return BandFrame(
        center_hz=7_100_000.0,
        sample_rate=250_000.0,
        timestamp=time.time(),
        band_cols=np.linspace(-85.0, -25.0, 256, dtype=np.float32),
    )


def test_apply_frame_survives_viewport_sync():
    """Simula _apply_display_frame + _update_display_width (set_viewport)."""
    spectrum = SpectrumGraph()
    waterfall = WaterfallTimeline()
    spectrum._frequency_columns = 80
    waterfall._frequency_columns = 80
    frame = _sample_frame()
    center = 7_100_000.0
    span = 250_000.0

    cols = slice_band_to_viewport(
        frame.band_cols, frame.center_hz, frame.sample_rate, center, span, 80
    )
    floors = np.full(80, -90.0)
    ceilings = np.full(80, -30.0)

    spectrum.set_column_levels(floors, ceilings)
    spectrum.set_viewport(center, span)
    spectrum.set_band_frame(frame)
    spectrum.set_viewport_cols(cols)

    waterfall.set_column_levels(floors, ceilings)
    waterfall.set_viewport(center, span)
    waterfall.add_viewport_row(cols, frame)

    assert spectrum._viewport_cols is not None
    assert spectrum._band_frame is not None

    spectrum.set_viewport(center, span)
    waterfall.set_viewport(center, span)

    assert spectrum._viewport_cols is not None
    assert waterfall._slice_cache is not None or len(waterfall._history) > 0


def test_waterfall_rebuilds_from_history_after_layout_width():
    wf = WaterfallTimeline()
    wf._frequency_columns = 80
    frame = _sample_frame()
    wf.set_viewport(7_100_000.0, 250_000.0)
    wf.add_band_row(frame)
    assert len(wf._history) == 1
  # width was 80, slice should exist
    assert wf._slice_cache is not None
