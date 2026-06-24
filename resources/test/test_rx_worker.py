"""Tests de tui/rx_worker.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from core.band_buffer import BandFrameMailbox
from tui.rx_worker import run_rx_iteration


def test_run_rx_iteration_publishes_frame():
    host = MagicMock()
    host._bandwidth_changing = False
    host._rx_active = True
    host.sample_rate = 500_000.0
    host.tuned_frequency = 100e6
    host.visible_span = 500_000.0
    host._display_width = 80
    host.demod_mode = "wbfm"
    host.squelch_enabled = False
    host.squelch_threshold = 5.0
    host.passband_center_hz = 100e6
    host.passband_width_hz = 80_000.0
    host.fm_deemphasis_us = 50.0
    host.fm_agc_enabled = True
    host.debug_mode = False
    host.config = {"dsp": {"fft_size": 512, "fft_avg_windows": 2, "fft_overlap": 0.5, "band_cache_cols": 256, "audio_rate": 48000}}
    host._device.read_samples.return_value = np.random.randn(4096).astype(np.complex64)
    host._band_mailbox = BandFrameMailbox()
    host._recorder = None
    host._audio_output = None
    host._fm_demod_state = MagicMock()
    host._fm_agc = MagicMock()
    host._squelch_gate = MagicMock()
    host._squelch_gate.is_open.return_value = True

    result = run_rx_iteration(host)
    assert result is not None
    assert result.frame_published is True
