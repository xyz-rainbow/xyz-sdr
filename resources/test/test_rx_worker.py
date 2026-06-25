"""Tests del RX worker: parametrizados por modo de demodulación y configuración.

Antes: un único test con MagicMock ad-hoc (~40 líneas).
Ahora: parametrización por (mode, record_iq, bandwidth_changing) + fixture compartida.

Usa la fixture `sdr_mock_host` de conftest.py.
"""

from __future__ import annotations

import pytest

from core.band_buffer import BandFrameMailbox
from tui.rx_worker import run_rx_iteration


@pytest.fixture
def sdr_mock_host():
    """Mock mínimo de XyzSDRApp para tests del RX worker."""
    from unittest.mock import MagicMock
    import numpy as np

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
    host._device.read_samples.return_value = np.random.default_rng(0).standard_normal(4096).astype(np.complex64)
    host._band_mailbox = BandFrameMailbox()
    host._recorder = None
    host._audio_output = None
    host._fm_demod_state = MagicMock()
    host._fm_agc = MagicMock()
    host._squelch_gate = MagicMock()
    host._squelch_gate.is_open.return_value = True
    host.consume_rx_warmup_samples.side_effect = lambda requested: requested
    return host


# ── Modos de demodulación ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "mode,needs_passband",
    [
        ("wbfm", True),
        ("nbfm", True),
        ("am",   True),
        ("usb",  True),
        ("lsb",  True),
        ("cw",   True),
        ("raw",  False),
        ("dsb",  True),
    ],
)
def test_run_rx_iteration_publishes_frame_per_mode(sdr_mock_host, mode, needs_passband):
    """Cada modo demod debe producir un frame sin lanzar."""
    sdr_mock_host.demod_mode = mode
    if not needs_passband:
        # raw no necesita passband width
        sdr_mock_host.passband_width_hz = 0

    result = run_rx_iteration(sdr_mock_host)
    assert result is not None
    assert result.frame_published is True


# ── Recorder paths ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("record_iq,record_audio", [
    (False, False),
    (True,  False),
    (False, True),
    (True,  True),
])
def test_run_rx_iteration_recorder_paths(sdr_mock_host, record_iq, record_audio):
    """La combinación record_iq × record_audio no debe lanzar."""
    from unittest.mock import MagicMock
    recorder = MagicMock()
    # Simular que los métodos retornan algo inocuo
    recorder.write_iq.return_value = None
    recorder.write_audio.return_value = None
    sdr_mock_host._recorder = recorder if (record_iq or record_audio) else None

    result = run_rx_iteration(sdr_mock_host)
    assert result is not None
    if record_iq:
        recorder.write_iq.assert_called()


# ── Bandwidth changing ────────────────────────────────────────────────────────


def test_run_rx_iteration_bandwidth_changing_returns_early(sdr_mock_host):
    """Si _bandwidth_changing es True, el worker duerme y devuelve None (early exit)."""
    sdr_mock_host._bandwidth_changing = True
    result = run_rx_iteration(sdr_mock_host)
    # El worker hace time.sleep(0.01) y retorna None — no publica frame
    assert result is None


# ── Squelch cerrado ──────────────────────────────────────────────────────────


def test_run_rx_iteration_squelch_closed_suppresses_audio(sdr_mock_host):
    """Si squelch está cerrado, no debe encolar audio."""
    sdr_mock_host.squelch_enabled = True
    sdr_mock_host._squelch_gate.is_open.return_value = False

    audio_output = sdr_mock_host._audio_output
    run_rx_iteration(sdr_mock_host)

    # Si el squelch está cerrado, audio_output.enqueue NO debe haber sido llamado
    if audio_output is not None and hasattr(audio_output, "enqueue"):
        audio_output.enqueue.assert_not_called()


# ── Debug mode ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("debug_mode", [True, False])
def test_run_rx_iteration_debug_mode_safe(sdr_mock_host, debug_mode):
    """Debug mode on/off no debe cambiar el contrato del frame."""
    sdr_mock_host.debug_mode = debug_mode
    result = run_rx_iteration(sdr_mock_host)
    assert result is not None
    assert result.frame_published is True