"""Fixtures compartidas para tests de xyz-sdr."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from core.band_buffer import BandFrameMailbox


@pytest.fixture
def center_hz() -> float:
    return 100_600_000.0


@pytest.fixture
def sample_rate() -> float:
    return 500_000.0


@pytest.fixture
def band_cols_count() -> int:
    return 512


@pytest.fixture
def synthetic_psd() -> np.ndarray:
    rng = np.random.default_rng(42)
    psd = rng.normal(loc=-60.0, scale=5.0, size=4096)
    psd[2048] = -20.0  # pico central
    return psd


@pytest.fixture
def flat_band_cols(band_cols_count: int) -> np.ndarray:
    cols = np.linspace(-80.0, -20.0, band_cols_count, dtype=np.float32)
    return cols


# ── Fixture compartida para tests del RX worker ──────────────────────────────


@pytest.fixture
def sdr_mock_host() -> MagicMock:
    """Mock de XyzSDRApp con todos los atributos que consume `tui.rx_worker.run_rx_iteration`.

    Tests que lo usan:
    - resources/test/test_rx_worker.py (parametrizado por modo/recorder/squelch)
    - resources/test/test_sdr_features.py (features end-to-end simuladas)
    """
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
    host.config = {
        "dsp": {
            "fft_size": 512,
            "fft_avg_windows": 2,
            "fft_overlap": 0.5,
            "band_cache_cols": 256,
            "audio_rate": 48000,
        }
    }
    host._device.read_samples.return_value = (
        np.random.default_rng(0).standard_normal(4096).astype(np.complex64)
    )
    host._band_mailbox = BandFrameMailbox()
    host._recorder = None
    host._audio_output = None
    host._fm_demod_state = MagicMock()
    host._fm_agc = MagicMock()
    host._squelch_gate = MagicMock()
    host._squelch_gate.is_open.return_value = True
    host.consume_rx_warmup_samples.side_effect = lambda requested: requested
    return host
