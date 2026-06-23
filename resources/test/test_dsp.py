"""Tests de core/dsp.py — FFT, mapeo PSD y chunks RX."""

from __future__ import annotations

import numpy as np

from core.dsp import (
    average_psd,
    compute_effective_fft_size,
    compute_rx_chunk_samples,
    map_psd_to_columns,
    round_fft_size,
)


def test_round_fft_size_power_of_two():
    assert round_fft_size(1000, minimum=256, maximum=65536) == 1024
    assert round_fft_size(4096, minimum=4096, maximum=65536) == 4096
    assert round_fft_size(100_000, minimum=256, maximum=65536) == 65536


def test_compute_effective_fft_size_full_span_uses_base():
    fft = compute_effective_fft_size(
        4096, sample_rate=500_000, visible_span=500_000, display_width=120
    )
    assert fft == 4096


def test_compute_effective_fft_size_zoom_in_scales_up():
    fft = compute_effective_fft_size(
        4096,
        sample_rate=8_000_000,
        visible_span=100_000,
        display_width=120,
        max_fft=65536,
    )
    assert fft == 65536


def test_map_psd_to_columns_spectrum_waterfall_parity(synthetic_psd, center_hz, sample_rate):
    width = 100
    viewport_center = center_hz
    visible_span = sample_rate

    a = map_psd_to_columns(
        synthetic_psd, center_hz, sample_rate, viewport_center, visible_span, width
    )
    b = map_psd_to_columns(
        synthetic_psd, center_hz, sample_rate, viewport_center, visible_span, width
    )
    np.testing.assert_allclose(a, b, equal_nan=True)


def test_map_psd_to_columns_outside_capture_is_nan(synthetic_psd, center_hz, sample_rate):
    cols = map_psd_to_columns(
        synthetic_psd,
        center_hz,
        sample_rate,
        viewport_center_hz=center_hz + sample_rate * 2,
        visible_span_hz=50_000,
        width=40,
    )
    assert cols.shape == (40,)
    assert np.all(np.isnan(cols))


def test_average_psd_shape_and_overlap():
    rng = np.random.default_rng(0)
    samples = rng.normal(size=4096 * 12) + 1j * rng.normal(size=4096 * 12)
    samples = samples.astype(np.complex64)

    freqs, psd = average_psd(
        samples, fft_size=4096, sample_rate=500_000, num_avg=4, overlap=0.5
    )
    assert len(freqs) == 4096
    assert len(psd) == 4096
    assert np.isfinite(psd).all()


def test_compute_rx_chunk_samples_scales_with_fft():
    small = compute_rx_chunk_samples(4096, sample_rate=500_000, num_avg=8)
    large = compute_rx_chunk_samples(8192, sample_rate=500_000, num_avg=8)
    assert large >= small
    assert small % 4096 == 0
    assert large % 8192 == 0
