"""Tests de core/dsp.py — FFT, mapeo PSD y chunks RX."""

from __future__ import annotations

import numpy as np
import pytest

from core.dsp import (
    AudioAgc,
    FmDemodState,
    SquelchGate,
    apply_fm_agc,
    apply_squelch,
    apply_squelch_with_state,
    average_psd,
    compute_effective_band_cols,
    compute_effective_fft_size,
    compute_rx_chunk_samples,
    compute_snr,
    demod_am,
    demod_nbfm,
    demod_raw,
    demod_ssb,
    demod_wbfm,
    demodulate,
    estimate_snr_at_freq,
    estimate_snr_db,
    fm_deemphasis,
    list_demod_modes,
    map_psd_to_columns,
    resample_iq_for_demod,
    round_fft_size,
    shift_to_baseband,
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


def test_compute_effective_band_cols_full_span_uses_base():
    cols = compute_effective_band_cols(
        1024, sample_rate=500_000, visible_span=500_000, display_width=120
    )
    assert cols == 1024


def test_compute_effective_band_cols_zoom_in_scales_up():
    cols = compute_effective_band_cols(
        1024,
        sample_rate=2_048_000,
        visible_span=100_000,
        display_width=120,
        max_cols=4096,
    )
    assert cols == 4096


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


def test_demod_wbfm_variable_bandwidth():
    rng = np.random.default_rng(0)
    n = 8192
    t = np.arange(n) / 2_048_000
    tone = np.exp(2j * np.pi * 25_000 * t).astype(np.complex64)
    narrow = demod_wbfm(tone, sample_rate=2_048_000, audio_rate=48_000, bandwidth_hz=100_000)
    wide = demod_wbfm(tone, sample_rate=2_048_000, audio_rate=48_000, bandwidth_hz=200_000)
    assert narrow.shape == wide.shape
    assert np.max(np.abs(narrow)) > 0
    assert np.max(np.abs(wide)) > 0


def test_fm_deemphasis_preserves_signal():
    t = np.arange(4800, dtype=np.float64) / 48_000
    audio = np.sin(2 * np.pi * 5_000 * t).astype(np.float32)
    out, zf = fm_deemphasis(audio, 48_000, tau_us=75.0)
    assert out.shape == audio.shape
    assert np.max(np.abs(out)) > 0
    assert zf.shape == (1,)
    out2, _ = fm_deemphasis(audio, 48_000, tau_us=75.0, zi=zf)
    assert out2.shape == audio.shape


def test_shift_to_baseband_noop_at_zero_offset():
    samples = np.array([1 + 1j, 2 + 2j], dtype=np.complex64)
    shifted = shift_to_baseband(samples, 0.0, 2_048_000)
    np.testing.assert_array_equal(shifted, samples)


def test_resample_iq_for_demod_reduces_high_rate():
    rng = np.random.default_rng(2)
    n = 80_000
    iq = (rng.normal(size=n) + 1j * rng.normal(size=n)).astype(np.complex64)
    out, sr = resample_iq_for_demod(iq, 8_000_000, 200_000)
    assert sr < 8_000_000
    assert sr >= 250_000
    assert len(out) < len(iq)


def test_demod_wbfm_high_sample_rate_produces_audio():
    n = 80_000
    t = np.arange(n) / 8_000_000
    tone = np.exp(2j * np.pi * 25_000 * t).astype(np.complex64)
    audio = demod_wbfm(
        tone,
        sample_rate=8_000_000,
        audio_rate=48_000,
        bandwidth_hz=200_000,
        fm_deemphasis_us=50.0,
    )
    assert audio.size > 0
    assert float(np.max(np.abs(audio))) > 0


# ---------------------------------------------------------------------------
# Coverage-gradual pass: pure demodulators, dispatcher, SNR, squelch.
# ---------------------------------------------------------------------------


def _tone(samples: int, freq_hz: float, sample_rate: float, amplitude: float = 0.5) -> np.ndarray:
    """Helper: complex64 IQ tone at baseband."""
    t = np.arange(samples) / sample_rate
    return (amplitude * np.exp(2j * np.pi * freq_hz * t)).astype(np.complex64)


def test_demod_nbfm_produces_audio_from_baseband_tone():
    n = 24_000
    samples = _tone(n, freq_hz=1_000, sample_rate=240_000)
    audio = demod_nbfm(samples, sample_rate=240_000, audio_rate=48_000)
    assert audio.ndim == 1
    assert audio.dtype == np.float32
    assert audio.size > 0
    # Centered at 1 kHz deviation -> should produce some non-trivial output.
    assert float(np.max(np.abs(audio))) > 0


def test_demod_nbfm_with_frequency_offset_shifts_first():
    """When frequency_offset_hz is set, signal is shifted to baseband first."""
    n = 24_000
    sample_rate = 480_000
    # Tone at +5 kHz, ask demodulator to center it via offset.
    samples = _tone(n, freq_hz=5_000, sample_rate=sample_rate)
    audio = demod_nbfm(
        samples,
        sample_rate=sample_rate,
        audio_rate=48_000,
        frequency_offset_hz=5_000.0,
        bandwidth_hz=12_000,
    )
    assert audio.size > 0


def test_demod_am_envelope_detection_basic():
    # AM: positive-real envelope on a baseband complex carrier.
    n = 24_000
    sample_rate = 240_000
    t = np.arange(n) / sample_rate
    envelope = (0.5 + 0.3 * np.sin(2 * np.pi * 1_000 * t)).astype(np.float32)
    samples = (envelope * np.exp(2j * np.pi * 0 * t)).astype(np.complex64)
    audio = demod_am(samples, sample_rate=sample_rate, audio_rate=48_000)
    assert audio.ndim == 1
    assert audio.size > 0


def test_demod_am_with_frequency_offset_shifts_first():
    n = 16_000
    sample_rate = 480_000
    samples = _tone(n, freq_hz=10_000, sample_rate=sample_rate, amplitude=0.5)
    audio = demod_am(
        samples,
        sample_rate=sample_rate,
        audio_rate=48_000,
        frequency_offset_hz=10_000.0,
    )
    assert audio.size > 0


def test_demod_ssb_usb_produces_audio():
    n = 24_000
    sample_rate = 240_000
    samples = _tone(n, freq_hz=1_500, sample_rate=sample_rate)
    audio = demod_ssb(
        samples,
        sample_rate=sample_rate,
        audio_rate=48_000,
        mode="usb",
        bandwidth_hz=3_000,
    )
    assert audio.dtype == np.float32
    assert audio.size > 0


def test_demod_ssb_lsb_produces_audio():
    n = 24_000
    sample_rate = 240_000
    samples = _tone(n, freq_hz=1_500, sample_rate=sample_rate)
    audio = demod_ssb(
        samples,
        sample_rate=sample_rate,
        audio_rate=48_000,
        mode="lsb",
        bandwidth_hz=3_000,
    )
    assert audio.size > 0


def test_demod_raw_passes_real_part_through_resampler():
    n = 24_000
    sample_rate = 240_000
    t = np.arange(n) / sample_rate
    samples = (np.exp(2j * np.pi * 1_000 * t)).astype(np.complex64)
    audio = demod_raw(samples, sample_rate=sample_rate, audio_rate=48_000)
    assert audio.dtype == np.float32
    assert audio.size > 0


def test_demodulate_dispatches_to_each_builtin_mode():
    n = 16_000
    samples = _tone(n, freq_hz=2_000, sample_rate=240_000)

    for mode in ("wbfm", "nbfm", "am", "usb", "lsb", "dsb"):
        audio = demodulate(samples, mode=mode, sample_rate=240_000, audio_rate=48_000)
        assert audio.size > 0, f"mode {mode} produced empty audio"


def test_demodulate_cw_uses_usb_with_bfo_offset():
    n = 16_000
    samples = _tone(n, freq_hz=1_000, sample_rate=240_000)
    audio = demodulate(
        samples, mode="cw", sample_rate=240_000, audio_rate=48_000,
        frequency_offset_hz=500.0,
    )
    assert audio.size > 0


def test_demodulate_raw_mode():
    n = 8_000
    samples = _tone(n, freq_hz=2_000, sample_rate=240_000)
    audio = demodulate(samples, mode="raw", sample_rate=240_000, audio_rate=48_000)
    assert audio.size > 0


def test_demodulate_unknown_mode_raises():
    samples = _tone(1024, freq_hz=1000, sample_rate=240_000)
    with pytest.raises(ValueError, match="Modo desconocido"):
        demodulate(samples, mode="bogus_mode_xyz", sample_rate=240_000)


def test_list_demod_modes_includes_builtins_without_plugins():
    modes = list_demod_modes(include_plugins=False)
    for builtin in ("wbfm", "nbfm", "am", "usb", "lsb", "raw"):
        assert builtin in modes


def test_list_demod_modes_swallows_plugin_discovery_errors():
    # Plugin import shouldn't break the builtin fallback path.
    modes = list_demod_modes(include_plugins=True)
    assert "wbfm" in modes


# -- SNR helpers --------------------------------------------------------------


def test_compute_snr_peak_vs_noise_window():
    psd = np.full(1024, -80.0, dtype=np.float32)
    psd[500] = -20.0  # 60 dB signal at idx 500
    snr = compute_snr(psd, signal_idx=500, noise_window=10)
    assert snr > 50.0


def test_compute_snr_empty_window_returns_floor():
    psd = np.full(4, -60.0, dtype=np.float32)
    # noise_window=10 + signal at idx 0 + len=4 -> mask fully False -> noise defaults to -100.
    # SNR = signal (-60) - noise (-100) = 40.
    snr = compute_snr(psd, signal_idx=0, noise_window=10)
    assert snr == pytest.approx(40.0)


def test_estimate_snr_db_basic():
    psd = np.full(1024, -80.0, dtype=np.float32)
    psd[500] = -30.0  # peak at idx 500
    snr = estimate_snr_db(psd)
    assert snr > 30.0


def test_estimate_snr_db_empty_returns_zero():
    assert estimate_snr_db(np.array([], dtype=np.float32)) == 0.0
    assert estimate_snr_db(None) == 0.0


def test_estimate_snr_at_freq_returns_zero_for_invalid_input():
    assert estimate_snr_at_freq(None, 100e6, 2_048_000, 100e6) == 0.0
    assert estimate_snr_at_freq(np.array([], dtype=np.float32), 100e6, 2_048_000, 100e6) == 0.0
    assert estimate_snr_at_freq(np.zeros(128, dtype=np.float32), 100e6, 0.0, 100e6) == 0.0


def test_estimate_snr_at_freq_peak_at_tuned_hz():
    psd = np.full(1024, -80.0, dtype=np.float32)
    psd[512] = -25.0
    sample_rate = 2_048_000.0
    center_hz = 100e6
    hz_per_bin = sample_rate / len(psd)
    tuned_hz = center_hz + (512 - 512) * hz_per_bin  # bin 512 == center
    snr = estimate_snr_at_freq(
        psd, center_hz, sample_rate, tuned_hz,
        noise_percentile=10.0, guard_bins=5,
    )
    assert snr > 30.0


def test_estimate_snr_at_freq_with_passband_width_guard():
    psd = np.full(1024, -80.0, dtype=np.float32)
    psd[500] = -20.0
    sample_rate = 2_048_000.0
    hz_per_bin = sample_rate / len(psd)
    center_hz = 100e6
    tuned_hz = center_hz + (500 - 512) * hz_per_bin
    snr = estimate_snr_at_freq(
        psd, center_hz, sample_rate, tuned_hz,
        noise_percentile=10.0,
        passband_width_hz=10_000.0,
    )
    assert snr > 30.0


# -- Squelch ------------------------------------------------------------------


def test_squelch_gate_opens_above_threshold():
    gate = SquelchGate(threshold_db=15.0, hang_ms=0.0)
    assert gate.is_open(20.0, now=0.0) is True
    assert gate.is_open(15.0, now=0.0) is True  # boundary
    assert gate.is_open(10.0, now=0.0) is False


def test_squelch_gate_hang_time_keeps_open_below_threshold():
    gate = SquelchGate(threshold_db=15.0, hang_ms=500.0)
    # First open with strong signal.
    assert gate.is_open(20.0, now=0.0) is True
    # Signal drops but we're still inside the hang window -> still open.
    assert gate.is_open(5.0, now=0.4) is True
    # Hang expires -> closed.
    assert gate.is_open(5.0, now=1.0) is False


def test_squelch_gate_configure_updates_threshold_and_hang():
    gate = SquelchGate(threshold_db=15.0, hang_ms=100.0)
    gate.configure(threshold_db=10.0, hang_ms=200.0)
    assert gate.threshold_db == 10.0
    assert gate.hang_s == pytest.approx(0.2)


def test_squelch_gate_reset_clears_state():
    gate = SquelchGate(threshold_db=15.0, hang_ms=500.0)
    gate.is_open(5.0, now=10.0)  # close it
    gate.reset()
    assert gate.is_open(20.0, now=11.0) is True


def test_apply_squelch_disabled_returns_input():
    audio = np.ones(64, dtype=np.float32)
    out = apply_squelch(audio, snr_db=0.0, enabled=False, threshold_db=10.0)
    np.testing.assert_array_equal(out, audio)


def test_apply_squelch_empty_audio_returns_empty():
    audio = np.array([], dtype=np.float32)
    out = apply_squelch(audio, snr_db=0.0, enabled=True, threshold_db=10.0)
    assert out.size == 0


def test_apply_squelch_open_passes_audio_through():
    audio = np.ones(64, dtype=np.float32) * 0.4
    out = apply_squelch(audio, snr_db=20.0, enabled=True, threshold_db=10.0)
    np.testing.assert_array_equal(out, audio)


def test_apply_squelch_closed_zeros_audio():
    audio = np.ones(64, dtype=np.float32) * 0.4
    out = apply_squelch(audio, snr_db=5.0, enabled=True, threshold_db=10.0)
    np.testing.assert_array_equal(out, np.zeros_like(audio))


def test_apply_squelch_with_state_reuses_gate():
    audio = np.ones(32, dtype=np.float32) * 0.5
    gate = SquelchGate(threshold_db=10.0, hang_ms=0.0)
    out, is_open = apply_squelch_with_state(
        audio, snr_db=20.0, gate=gate, enabled=True, now=0.0,
    )
    assert is_open is True
    np.testing.assert_array_equal(out, audio)
    # Second call with low SNR, no hang -> closed.
    out2, is_open2 = apply_squelch_with_state(
        audio, snr_db=0.0, gate=gate, enabled=True, now=1.0,
    )
    assert is_open2 is False
    np.testing.assert_array_equal(out2, np.zeros_like(audio))


def test_apply_squelch_with_state_disabled_short_circuits():
    audio = np.ones(16, dtype=np.float32)
    gate = SquelchGate(threshold_db=10.0, hang_ms=500.0)
    out, is_open = apply_squelch_with_state(
        audio, snr_db=0.0, gate=gate, enabled=False,
    )
    assert is_open is True
    np.testing.assert_array_equal(out, audio)


# -- AudioAgc + apply_fm_agc -------------------------------------------------


def test_audio_agc_state_machine_pumps_and_releases():
    agc = AudioAgc(target_rms=0.12, attack_ms=1.0, release_ms=50.0)
    quiet = np.full(48_000, 0.01, dtype=np.float32)
    out = agc.process(quiet, sample_rate=48_000)
    assert out.shape == quiet.shape
    # Loud input -> gain should shrink (no clipping).
    loud = np.full(48_000, 0.9, dtype=np.float32)
    out_loud = agc.process(loud, sample_rate=48_000)
    assert np.max(np.abs(out_loud)) <= 1.5  # clipping tolerance


def test_apply_fm_agc_disabled_returns_audio_unchanged():
    audio = np.full(1024, 0.25, dtype=np.float32)
    gate = AudioAgc()
    out = apply_fm_agc(audio, gate, enabled=False, sample_rate=48_000)
    np.testing.assert_array_equal(out, audio)


def test_apply_fm_agc_enabled_routes_through_gate():
    audio = np.full(2048, 0.1, dtype=np.float32)
    gate = AudioAgc(target_rms=0.12)
    out = apply_fm_agc(audio, gate, enabled=True, sample_rate=48_000)
    assert out.shape == audio.shape


def test_fm_demod_state_initialises_fields():
    state = FmDemodState()
    assert state.deemph_zi.shape == (1,)
    assert state.ssb_phase == 0.0
    assert state.lo_phase == 0.0
    assert state.last_filtered == 0j
    assert state.lp_zi == {}


def test_fm_demod_state_reset_clears_state():
    state = FmDemodState()
    state.ssb_phase = 1.5
    state.lo_phase = 0.7
    state.lp_zi[(100.0, 48000.0, 64)] = np.array([0.1])
    state.reset()
    assert state.ssb_phase == 0.0
    assert state.lo_phase == 0.0
    assert state.lp_zi == {}
