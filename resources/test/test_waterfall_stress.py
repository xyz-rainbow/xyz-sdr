"""Stress del waterfall bajo zoom estrecho (presets bajos / frecuencias bajas)."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

import numpy as np

from core.band_buffer import BandFrame, compact_band_cols
from tui.widgets.waterfall_timeline import WaterfallTimeline


@patch.object(WaterfallTimeline, "content_region", new_callable=PropertyMock)
@patch.object(WaterfallTimeline, "size", new_callable=PropertyMock)
def test_waterfall_survives_full_history_low_span(mock_size, mock_region):
    """Rellena historial con zoom estrecho (250 kHz BW, 100 kHz span) sin excepción."""
    fake_size = SimpleNamespace(width=120, height=18)
    mock_region.return_value = fake_size
    mock_size.return_value = fake_size

    widget = WaterfallTimeline(max_history=100, waterfall_auto_level=True)
    widget._layout_height = 18
    widget._viewport_center_hz = 88e6
    widget._visible_span_hz = 100e3

    large = compact_band_cols(np.linspace(-90.0, -20.0, 4096, dtype=np.float32))
    floors = np.full(120, -85.0)
    ceilings = np.full(120, -25.0)
    widget.set_column_levels(floors, ceilings)

    t0 = time.perf_counter()
    for _ in range(105):
        widget._last_row_time = 0.0
        frame = BandFrame(88e6, 250e3, time.time(), large)
        widget.add_band_row(frame)
        text = widget.render()
        assert text is not None

    assert time.perf_counter() - t0 < 5.0
    assert len(widget._history) == 100
    assert all(len(row.band_cols) == len(large) for row in widget._history)
