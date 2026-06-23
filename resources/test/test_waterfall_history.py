"""Tests de historial waterfall — tope dinámico, deque e slice incremental."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

import numpy as np

from core.band_buffer import BandFrame, slice_band_to_viewport
from tui.widgets.waterfall_timeline import WaterfallTimeline


def test_effective_max_history_formula():
    widget = WaterfallTimeline(max_history=100, history_buffer_ratio=2 / 3)
    widget._layout_height = 30
    assert widget._effective_max_history() == min(100, 30 + 20)


def test_effective_max_history_respects_toml_cap():
    widget = WaterfallTimeline(max_history=40, history_buffer_ratio=1.0)
    widget._layout_height = 50
    assert widget._effective_max_history() == 40


def test_deque_appendleft_respects_maxlen(flat_band_cols):
    widget = WaterfallTimeline(max_history=10, history_buffer_ratio=0.0)
    widget._layout_height = 5
    widget._ensure_history_maxlen()

    center = 100e6
    rate = 500e3
    from tui.widgets.waterfall_timeline import _WaterfallRow

    for _ in range(20):
        widget._ensure_history_maxlen()
        widget._history.appendleft(_WaterfallRow(center, rate, flat_band_cols))

    assert len(widget._history) <= widget._effective_max_history()


def _widget_with_size(max_history=50, buffer_ratio=0.5, width=120, height=10):
    widget = WaterfallTimeline(max_history=max_history, history_buffer_ratio=buffer_ratio)
    widget._layout_height = height
    return widget, SimpleNamespace(width=width, height=height)


@patch.object(WaterfallTimeline, "size", new_callable=PropertyMock)
def test_prepend_slice_row_updates_cache_shape(mock_size, flat_band_cols):
    from tui.widgets.waterfall_timeline import _WaterfallRow

    widget, fake_size = _widget_with_size()
    mock_size.return_value = fake_size
    widget._viewport_center_hz = 100e6
    widget._visible_span_hz = 200e3

    widget._history.appendleft(_WaterfallRow(100e6, 500e3, flat_band_cols))
    widget._rebuild_slice_cache()
    assert widget._slice_cache is not None

    frame = BandFrame(100e6, 500e3, time.time(), flat_band_cols + 3.0)
    widget._prepend_slice_row(frame)

    assert widget._slice_cache is not None
    assert widget._slice_cache.shape[1] == 120
    assert widget._slice_cache_rows >= 1


@patch.object(WaterfallTimeline, "size", new_callable=PropertyMock)
def test_prepend_slice_row_shift_preserves_width(mock_size, flat_band_cols):
    widget, fake_size = _widget_with_size(height=8)
    mock_size.return_value = fake_size
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
        widget._history.appendleft(_WaterfallRow(center, rate, flat_band_cols))

    assert len(widget._history) <= cap


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

    # El batch no debería ser más de 3× más lento que el enfoque fila a fila.
    assert batch_ms < row_ms * 3.0 + 1.0
