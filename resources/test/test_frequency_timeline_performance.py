"""Tests de rendimiento y batch-update del FrequencyTimeline."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from rich.text import Text

from tui.widgets.frequency_timeline import FrequencyTimeline


class _SizedTimeline(FrequencyTimeline):
    def __init__(self, width: int = 120) -> None:
        super().__init__()
        self._mock_width = width

    @property
    def size(self):
        return MagicMock(width=self._mock_width, height=3)


def _timeline(width: int = 120) -> FrequencyTimeline:
    return _SizedTimeline(width=width)


def test_update_display_state_single_refresh():
    tl = _timeline()
    refresh_calls: list[None] = []
    original_refresh = tl.refresh

    def counting_refresh(*args, **kwargs):
        refresh_calls.append(None)
        return original_refresh(*args, **kwargs)

    with patch.object(tl, "refresh", side_effect=counting_refresh):
        tl.update_display_state(
            viewport_center_hz=101_000_000.0,
            visible_span_hz=1_000_000.0,
            tuned_freq_hz=100_800_000.0,
            passband_center_hz=100_800_000.0,
            passband_width_hz=150_000.0,
        )

    assert len(refresh_calls) == 1
    assert tl.viewport_center_hz == 101_000_000.0
    assert tl.tuned_freq_hz == 100_800_000.0


def test_render_cache_reuses_output():
    tl = _timeline()
    first = tl.render()
    second = tl.render()
    assert first is second


def test_render_cache_invalidates_on_state_change():
    tl = _timeline()
    first = tl.render()
    tl.tuned_freq_hz = 99_000_000.0
    tl._maybe_refresh()
    second = tl.render()
    assert first is not second


def test_batch_update_faster_than_individual_assignments():
    tl = _timeline()
    with patch.object(tl, "refresh"):
        t0 = time.perf_counter()
        for i in range(200):
            tl.update_display_state(
                viewport_center_hz=100_600_000.0 + i * 1000,
                tuned_freq_hz=100_600_000.0 + i * 500,
            )
        batch_elapsed = time.perf_counter() - t0

    tl2 = _timeline()
    refresh_count = 0
    real_refresh = tl2.refresh

    def count_refresh(*args, **kwargs):
        nonlocal refresh_count
        refresh_count += 1
        return real_refresh(*args, **kwargs)

    with patch.object(tl2, "refresh", side_effect=count_refresh):
        t0 = time.perf_counter()
        for i in range(200):
            tl2.viewport_center_hz = 100_600_000.0 + i * 1000
            tl2.tuned_freq_hz = 100_600_000.0 + i * 500
        individual_elapsed = time.perf_counter() - t0

    assert refresh_count >= 200
    assert batch_elapsed < individual_elapsed


def test_render_completes_within_budget():
    tl = _timeline(width=160)
    t0 = time.perf_counter()
    for _ in range(50):
        out = tl.render()
        assert isinstance(out, Text)
    elapsed = time.perf_counter() - t0
    # 50 renders a 160 cols — presupuesto holgado para CI/Windows.
    assert elapsed < 0.5, f"render demasiado lento: {elapsed:.3f}s"
