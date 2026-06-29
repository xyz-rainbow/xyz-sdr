"""Tests de change_bandwidth + estado display (espectro/cascada)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from tui.app import XyzSDRApp
from tui.widgets.spectrum_graph import SpectrumGraph
from tui.widgets.waterfall_timeline import WaterfallTimeline, _WaterfallRow


def _simulated_device(*, sample_rate: float = 250_000.0):
    dev = MagicMock()
    dev.is_simulated = True
    dev.driver = "simulated"
    dev.sample_rate = sample_rate
    dev._device_kwargs = None
    dev.is_sample_rate_supported = lambda rate: True
    dev.get_supported_sample_rates = lambda: [250_000.0, 2_048_000.0, 8_000_000.0]
    dev.same_device_as = lambda _k: False
    return dev


@pytest.fixture
def app_with_widgets():
    app = XyzSDRApp(driver="simulated", center_freq=98_000_000.0, demod_mode="wbfm")
    app._device = _simulated_device(sample_rate=250_000.0)
    app.sample_rate = 250_000.0
    app._hardware_ready = True
    app._rx_active = False
    app._display_width = 80
    app._bandwidth_changing = False

    spectrum = SpectrumGraph()
    waterfall = WaterfallTimeline()
    spectrum._band_frame = None
    waterfall._history.append(
        _WaterfallRow(98e6, 250e3, np.linspace(-80, -30, 256, dtype=np.float32))
    )
    waterfall._slice_ring = np.zeros((10, 80), dtype=np.float64)
    waterfall._slice_ring_height = 10
    waterfall._slice_cache = waterfall._slice_ring
    waterfall._slice_cache_width = 80

    def query_one(selector, expected_type=None):
        if selector == "#spectrum":
            return spectrum
        if selector == "#waterfall":
            return waterfall
        if selector == "#btn_rx":
            btn = MagicMock()
            return btn
        raise LookupError(selector)

    app.query_one = query_one  # type: ignore[method-assign]
    return app, spectrum, waterfall


def test_change_bandwidth_invalidates_waterfall_state(app_with_widgets):
    app, _spectrum, waterfall = app_with_widgets
    app._rx_active = True

    with patch.object(app, "_stop_rx"), patch.object(app, "_start_rx"), patch.object(
        app, "_sync_viewport"
    ), patch.object(app, "_persist_device_config"), patch.object(
        app, "_sync_bandwidth_select_value"
    ), patch.object(
        app, "_update_status"
    ):
        ok = app.change_bandwidth(2_048_000.0)

    assert ok is True
    assert app.sample_rate == 2_048_000.0
    assert len(waterfall._history) == 0
    assert waterfall._slice_ring is None
    assert waterfall._slice_cache is None


def test_change_bandwidth_clears_band_mailbox(app_with_widgets):
    app, _spectrum, _waterfall = app_with_widgets
    from core.band_buffer import BandFrame
    import time

    app._band_mailbox.publish(
        BandFrame(98e6, 250e3, time.time(), np.zeros(64, dtype=np.float32)),
        snr=10.0,
    )

    with patch.object(app, "_stop_rx"), patch.object(app, "_start_rx"), patch.object(
        app, "_sync_viewport"
    ), patch.object(app, "_persist_device_config"), patch.object(
        app, "_sync_bandwidth_select_value"
    ), patch.object(
        app, "_update_status"
    ):
        app.change_bandwidth(2_048_000.0)

    frame, _snr, seq = app._band_mailbox.peek_latest()
    assert frame is None
    assert seq == 0
