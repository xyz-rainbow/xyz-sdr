"""Stress del waterfall bajo zoom estrecho (presets bajos / frecuencias bajas)."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

import numpy as np
import pytest

from core.band_buffer import BandFrame, compact_band_cols
from tui.widgets.waterfall_timeline import WaterfallTimeline, _WaterfallRow


@pytest.mark.slow
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


@patch.object(WaterfallTimeline, "content_region", new_callable=PropertyMock)
@patch.object(WaterfallTimeline, "size", new_callable=PropertyMock)
def test_prepend_viewport_row_survives_short_slice_cache(mock_size, mock_region):
    """Prepend con slice_cache más bajo que height del widget no lanza ValueError."""
    fake_size = SimpleNamespace(width=86, height=10)
    mock_region.return_value = fake_size
    mock_size.return_value = fake_size

    widget = WaterfallTimeline(max_history=50, waterfall_auto_level=False)
    widget._layout_height = 10
    widget._viewport_center_hz = 98e6
    widget._visible_span_hz = 2e6
    width = 86
    widget._slice_cache = np.linspace(-70.0, -30.0, width * 2, dtype=np.float64).reshape(2, width)
    widget._slice_cache_width = width
    widget._slice_cache_rows = 2

    new_row = np.full((1, width), -45.0, dtype=np.float64)
    widget._prepend_viewport_row(new_row, height=10, width=width)

    assert widget._slice_cache is not None
    assert widget._slice_cache.shape == (10, width)
    assert widget._slice_cache[0, 0] == -45.0


@patch.object(WaterfallTimeline, "content_region", new_callable=PropertyMock)
@patch.object(WaterfallTimeline, "size", new_callable=PropertyMock)
def test_clear_history_resets_slice_ring(mock_size, mock_region):
    fake_size = SimpleNamespace(width=118, height=14)
    mock_region.return_value = fake_size
    mock_size.return_value = fake_size

    widget = WaterfallTimeline(max_history=20)
    widget._layout_height = 14
    widget._slice_ring = np.zeros((14, 118), dtype=np.float64)
    widget._slice_ring_height = 14
    widget._slice_cache = widget._slice_ring
    widget._slice_cache_width = 118
    widget._slice_cache_rows = 14
    widget._history.append(_WaterfallRow(98e6, 2e6, np.zeros(8, dtype=np.float32)))

    widget.clear_history()

    assert len(widget._history) == 0
    assert widget._slice_ring is None
    assert widget._slice_cache is None
    assert widget._slice_cache_width == 0


@patch.object(WaterfallTimeline, "content_region", new_callable=PropertyMock)
@patch.object(WaterfallTimeline, "size", new_callable=PropertyMock)
def test_bandwidth_transition_mixed_history(mock_size, mock_region):
    """Historial con distintos sample_rate + prepend tras cambio de ancho sin excepción."""
    fake_size = SimpleNamespace(width=80, height=12)
    mock_region.return_value = fake_size
    mock_size.return_value = fake_size

    widget = WaterfallTimeline(max_history=50, waterfall_auto_level=False)
    widget._layout_height = 12
    widget._viewport_center_hz = 98e6
    widget._visible_span_hz = 2e6

    low = compact_band_cols(np.linspace(-90.0, -30.0, 512, dtype=np.float32))
    high = compact_band_cols(np.linspace(-85.0, -25.0, 4096, dtype=np.float32))
    widget._last_row_time = 0.0
    widget.add_band_row(BandFrame(98e6, 250e3, time.time(), low))
    widget.add_band_row(BandFrame(98e6, 2_048_000.0, time.time(), high))

    widget.set_viewport(98e6, 1_500_000.0)
    cols = np.linspace(-70.0, -40.0, 80, dtype=np.float64)
    widget._last_row_time = 0.0
    widget.add_viewport_row(cols, BandFrame(98e6, 2_048_000.0, time.time(), high))
    assert widget.render() is not None


@patch.object(WaterfallTimeline, "content_region", new_callable=PropertyMock)
@patch.object(WaterfallTimeline, "size", new_callable=PropertyMock)
def test_prepend_slice_row_width_change(mock_size, mock_region):
    fake_size = SimpleNamespace(width=86, height=10)
    mock_region.return_value = fake_size
    mock_size.return_value = fake_size

    widget = WaterfallTimeline(max_history=30, waterfall_auto_level=False)
    widget._layout_height = 10
    widget._viewport_center_hz = 98e6
    widget._visible_span_hz = 2e6
    width = 86
    widget._slice_cache = np.linspace(-70.0, -30.0, width, dtype=np.float64).reshape(1, width)
    widget._slice_cache_width = width
    widget._slice_cache_rows = 1
    widget._slice_ring = np.zeros((10, 118), dtype=np.float64)
    widget._slice_ring_height = 10

    frame = BandFrame(
        98e6,
        2_048_000.0,
        time.time(),
        compact_band_cols(np.linspace(-80.0, -30.0, 512, dtype=np.float32)),
    )
    widget._prepend_slice_row(frame)

    assert widget._slice_cache is not None
    assert widget._slice_cache.shape[1] == 86
