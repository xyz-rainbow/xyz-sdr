"""Tests de historial waterfall — tope dinámico, deque e slice incremental."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

import numpy as np

from core.band_buffer import BandFrame, slice_band_to_viewport
from tui.widgets.display_palette import gradient_color
from tui.widgets.waterfall_timeline import WaterfallTimeline


def test_effective_max_history_uses_config_cap():
    widget = WaterfallTimeline(max_history=100, history_buffer_ratio=2 / 3)
    widget._layout_height = 30
    assert widget._effective_max_history() == 100


def test_effective_max_history_respects_toml_cap():
    widget = WaterfallTimeline(max_history=40, history_buffer_ratio=1.0)
    widget._layout_height = 50
    assert widget._effective_max_history() == 40


def test_deque_append_respects_maxlen(flat_band_cols):
    widget = WaterfallTimeline(max_history=10, history_buffer_ratio=0.0)
    widget._layout_height = 5
    widget._ensure_history_maxlen()

    center = 100e6
    rate = 500e3
    from tui.widgets.waterfall_timeline import _WaterfallRow

    for _ in range(20):
        widget._ensure_history_maxlen()
        widget._history.append(_WaterfallRow(center, rate, flat_band_cols))

    assert len(widget._history) <= widget._effective_max_history()


def _widget_with_size(max_history=50, buffer_ratio=0.5, width=120, height=10):
    widget = WaterfallTimeline(max_history=max_history, history_buffer_ratio=buffer_ratio)
    widget._layout_height = height
    return widget, SimpleNamespace(width=width, height=height)


def _patch_geometry(mock_size, mock_region, fake_size):
    """Simula content_region (área útil) y size del widget."""
    mock_region.return_value = fake_size
    mock_size.return_value = fake_size


@patch.object(WaterfallTimeline, "content_region", new_callable=PropertyMock)
@patch.object(WaterfallTimeline, "size", new_callable=PropertyMock)
def test_prepend_slice_row_updates_cache_shape(mock_size, mock_region, flat_band_cols):
    from tui.widgets.waterfall_timeline import _WaterfallRow

    widget, fake_size = _widget_with_size()
    _patch_geometry(mock_size, mock_region, fake_size)
    widget._viewport_center_hz = 100e6
    widget._visible_span_hz = 200e3

    widget._history.append(_WaterfallRow(100e6, 500e3, flat_band_cols))
    widget._rebuild_slice_cache()
    assert widget._slice_cache is not None

    frame = BandFrame(100e6, 500e3, time.time(), flat_band_cols + 3.0)
    widget._prepend_slice_row(frame)

    assert widget._slice_cache is not None
    assert widget._slice_cache.shape[1] == 120
    assert widget._slice_cache_rows >= 1


@patch.object(WaterfallTimeline, "content_region", new_callable=PropertyMock)
@patch.object(WaterfallTimeline, "size", new_callable=PropertyMock)
def test_prepend_slice_row_shift_preserves_width(mock_size, mock_region, flat_band_cols):
    widget, fake_size = _widget_with_size(height=8)
    _patch_geometry(mock_size, mock_region, fake_size)
    widget._viewport_center_hz = 100e6
    widget._visible_span_hz = 500e3

    width = 120
    row_a = slice_band_to_viewport(
        flat_band_cols, 100e6, 500e3, 100e6, 500e3, width
    ).reshape(1, -1)
    widget._slice_cache = np.vstack([row_a, row_a, row_a])
    widget._slice_cache_rows = 3
    widget._slice_cache_width = width

    frame = BandFrame(100e6, 500e3, time.time(), flat_band_cols + 5.0)
    widget._prepend_slice_row(frame)

    assert widget._slice_cache.shape[1] == width
    assert widget._slice_cache_rows <= 8


def test_history_memory_bounded(flat_band_cols):
    """El historial no debe crecer más allá del tope dinámico."""
    widget = WaterfallTimeline(max_history=100, history_buffer_ratio=2 / 3)
    widget._layout_height = 25
    cap = widget._effective_max_history()

    center = 100e6
    rate = 250e3
    from tui.widgets.waterfall_timeline import _WaterfallRow

    for _ in range(cap + 30):
        widget._ensure_history_maxlen()
        widget._history.append(_WaterfallRow(center, rate, flat_band_cols))

    assert len(widget._history) <= cap


@patch.object(WaterfallTimeline, "content_region", new_callable=PropertyMock)
@patch.object(WaterfallTimeline, "size", new_callable=PropertyMock)
def test_history_scroll_offset_shows_older_rows(mock_size, mock_region, flat_band_cols):
    from tui.widgets.waterfall_timeline import _WaterfallRow

    widget, fake_size = _widget_with_size(height=5, max_history=50)
    _patch_geometry(mock_size, mock_region, fake_size)
    widget._viewport_center_hz = 100e6
    widget._visible_span_hz = 500e3

    for idx in range(10):
        cols = flat_band_cols + float(idx)
        widget._history.append(_WaterfallRow(100e6, 500e3, cols))

    assert widget.scroll_history(1, steps=2)
    assert widget.history_offset == 2
    widget._rebuild_slice_cache()
    assert widget._slice_cache is not None
    assert widget._slice_cache_rows == 5


def test_scroll_history_multi_step_stops_at_end(flat_band_cols):
    from tui.widgets.waterfall_timeline import _WaterfallRow

    widget = WaterfallTimeline(max_history=50, history_buffer_ratio=0.0)
    widget._layout_height = 5
    for _ in range(7):
        widget._history.append(_WaterfallRow(100e6, 500e3, flat_band_cols))

    assert widget.scroll_history(1, steps=10)
    assert widget.history_offset == widget._max_history_offset()


@patch("tui.widgets.waterfall_timeline.is_shift_pressed", return_value=True)
def test_handle_wheel_shift_scrolls_history(mock_shift, flat_band_cols):
    from textual.events import MouseScrollDown
    from tui.widgets.waterfall_timeline import _WaterfallRow

    widget = WaterfallTimeline(max_history=50)
    widget._layout_height = 5
    for _ in range(12):
        widget._history.append(_WaterfallRow(100e6, 500e3, flat_band_cols))

    event = MouseScrollDown(None, 0, 0, 0, -1, 0, False, False, False)
    widget._handle_wheel(event, scroll_up=False)

    assert widget.history_offset > 0
    mock_shift.assert_called_once()


@patch.object(WaterfallTimeline, "content_region", new_callable=PropertyMock)
@patch.object(WaterfallTimeline, "size", new_callable=PropertyMock)
def test_render_anchors_data_at_top(mock_size, mock_region, flat_band_cols):
    """Filas vacías abajo; datos anclados arriba (top-down)."""
    from tui.widgets.waterfall_timeline import _WaterfallRow

    widget, fake_size = _widget_with_size(height=6, width=20)
    _patch_geometry(mock_size, mock_region, fake_size)
    widget._viewport_center_hz = 100e6
    widget._visible_span_hz = 500e3

    widget._history.append(_WaterfallRow(100e6, 500e3, flat_band_cols))
    widget._history.append(_WaterfallRow(100e6, 500e3, flat_band_cols + 1.0))
    widget._rebuild_slice_cache()
    widget.set_column_levels(
        np.full(20, -90.0),
        np.full(20, -30.0),
    )
    widget._norm_last_update = time.time()

    text = widget.render()
    lines = str(text).split("\n")
    assert len(lines) == 6
    assert "░" in lines[-1]
    assert "░" not in lines[0]


def test_auto_level_from_slice_cache(flat_band_cols):
    widget = WaterfallTimeline(waterfall_auto_level=True, min_range_db=6.0)
    widget._slice_cache = np.array([[-50.0, -40.0], [-55.0, -35.0]], dtype=np.float64)
    widget._norm_last_update = 0.0
    widget._update_normalization(force=True)
    floors, ceilings = widget._levels_for_width(2)
    assert ceilings.max() > floors.min()
    assert ceilings.max() - floors.min() >= 6.0


def test_manual_level_ignores_slice_cache(flat_band_cols):
    widget = WaterfallTimeline(
        waterfall_auto_level=False,
        manual_norm_min=-70.0,
        manual_norm_max=-25.0,
    )
    widget._slice_cache = np.array([[-10.0, 0.0]], dtype=np.float64)
    widget._update_normalization(force=True)
    floors, ceilings = widget._levels_for_width(1)
    assert floors[0] == -70.0
    assert ceilings[0] == -25.0


def test_gradient_color_interpolates():
    c0 = gradient_color(0.0)
    c1 = gradient_color(1.0)
    cm = gradient_color(0.5)
    assert c0 != c1
    assert cm != c0
    assert cm != c1


def test_batch_slice_not_slower_than_linear_threshold(flat_band_cols):
    """Regresión: slice en lote debe ser razonable vs fila a fila (sanity perf)."""
    from core.band_buffer import slice_band_history_to_viewport

    rows = [(100e6, 500e3, flat_band_cols) for _ in range(40)]
    width = 120

    t0 = time.perf_counter()
    for _ in range(30):
        slice_band_history_to_viewport(rows, 100e6, 100_000, width)
    batch_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    for _ in range(30):
        for row in rows:
            slice_band_to_viewport(row[2], row[0], row[1], 100e6, 100_000, width)
    row_ms = (time.perf_counter() - t0) * 1000

    assert batch_ms < row_ms * 3.0 + 1.0
