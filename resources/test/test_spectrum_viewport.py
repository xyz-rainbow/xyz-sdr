"""Tests: espectro conserva datos tras cambios de viewport."""

from __future__ import annotations

import time

import numpy as np

from core.band_buffer import BandFrame
from tui.widgets.spectrum_graph import SpectrumGraph


def _sample_frame() -> BandFrame:
    return BandFrame(
        center_hz=100_600_000.0,
        sample_rate=2_048_000.0,
        timestamp=time.time(),
        band_cols=np.linspace(-80.0, -20.0, 256, dtype=np.float32),
    )


def test_set_band_frame_survives_viewport_sync():
    spectrum = SpectrumGraph()
    spectrum._frequency_columns = 80

    spectrum.set_band_frame(_sample_frame())
    assert spectrum._viewport_cols is not None

    spectrum.set_viewport(100_600_000.0, 1_024_000.0)
    assert spectrum._viewport_cols is not None
    assert len(spectrum._viewport_cols) == 80


def test_viewport_cols_preserved_without_band_frame():
    spectrum = SpectrumGraph()
    spectrum._frequency_columns = 80
    cols = np.linspace(-70.0, -30.0, 80, dtype=np.float64)

    spectrum.set_viewport_cols(cols)
    spectrum.set_viewport(100_600_000.0, 1_024_000.0)

    assert spectrum._viewport_cols is not None
    np.testing.assert_array_equal(spectrum._viewport_cols, cols)


def test_set_band_frame_refreshes_after_set_viewport_clears_paint():
    """Regresión: set_viewport sin band_frame + set_band_frame debe repintar."""
    spectrum = SpectrumGraph()
    spectrum._frequency_columns = 80
    spectrum.clear()
    spectrum.set_viewport(7_100_000.0, 250_000.0)
    assert spectrum._viewport_cols is None

    spectrum.set_band_frame(_sample_frame())
    assert spectrum._viewport_cols is not None
    assert spectrum._band_frame is not None
    assert spectrum._paint_cache is None

