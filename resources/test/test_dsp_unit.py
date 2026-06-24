"""Tests unitarios adicionales de core/dsp.py."""

from __future__ import annotations

import numpy as np

from core.dsp import _hann_window, average_psd, low_pass_filter


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
