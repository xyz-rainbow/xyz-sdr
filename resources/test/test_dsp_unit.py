"""Tests unitarios adicionales de core/dsp.py."""

from __future__ import annotations

import numpy as np

from core.dsp import FmDemodState, _hann_window, average_psd, demodulate, low_pass_filter, low_pass_filter_with_state


def test_hann_window_cached():
    w1 = _hann_window(256)
    w2 = _hann_window(256)
    assert w1 is w2
    assert len(w1) == 256


def test_average_psd_shape():
    samples = np.random.randn(4096).astype(np.complex64)
    freqs, psd = average_psd(samples, fft_size=512, sample_rate=1_000_000, num_avg=2)
    assert len(freqs) == 512
    assert len(psd) == 512


def test_low_pass_filter_caches_taps():
    x = np.random.randn(1000).astype(np.float32)
    y1 = low_pass_filter(x, 10_000, 200_000)
    y2 = low_pass_filter(x, 10_000, 200_000)
    assert y1.shape == y2.shape


def test_low_pass_filter_zi_chunk_continuity():
    """Filtrado por chunks con estado zi debe coincidir con filtrado continuo."""
    rng = np.random.default_rng(0)
    x = rng.standard_normal(800).astype(np.float64)
    cutoff, sr = 10_000.0, 200_000.0
    y_full = low_pass_filter(x, cutoff, sr)

    state = FmDemodState()
    mid = 320
    y_a = low_pass_filter_with_state(x[:mid], cutoff, sr, state)
    y_b = low_pass_filter_with_state(x[mid:], cutoff, sr, state)
    y_chunked = np.concatenate([y_a, y_b])

    np.testing.assert_allclose(y_full, y_chunked, rtol=1e-5, atol=1e-4)


def test_demod_raw_produces_audio():
    rng = np.random.default_rng(1)
    iq = (rng.standard_normal(4096) + 1j * rng.standard_normal(4096)).astype(np.complex64) * 0.1
    audio = demodulate(iq, mode="raw", sample_rate=250_000, audio_rate=48_000)
    assert len(audio) > 0
    assert np.isfinite(audio).all()


def test_demod_cw_routes_to_ssb():
    t = np.arange(4096, dtype=np.float64) / 250_000
    tone = np.exp(2j * np.pi * 1000 * t).astype(np.complex64)
    audio = demodulate(tone, mode="cw", sample_rate=250_000, audio_rate=48_000, passband_width_hz=800)
    assert len(audio) > 0
