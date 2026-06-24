"""Tests matriz presets BANDWIDTH × modos demod."""

from __future__ import annotations

import numpy as np
import pytest

from core.device import BANDWIDTH_PRESETS
from core.dsp import (
    demodulate,
    resample_audio_to_rate,
    resample_iq_for_demod,
    FmDemodState,
)
from core.dsp_profiles import (
    compute_target_demod_rate,
    profile_for_sample_rate,
)
from core.passband import default_passband_width


def _synthetic_fm_iq(
    sample_rate: float,
    *,
    n: int | None = None,
    mod_hz: float = 1_000.0,
    carrier_offset_hz: float = 0.0,
) -> np.ndarray:
    if n is None:
        n = min(int(sample_rate // 50), 80_000)
    t = np.arange(n, dtype=np.float64) / sample_rate
    phase = 2 * np.pi * mod_hz * t
    if carrier_offset_hz:
        phase += 2 * np.pi * carrier_offset_hz * t
    return np.exp(1j * phase * 0.05).astype(np.complex64)


@pytest.mark.parametrize("capture_rate", BANDWIDTH_PRESETS)
def test_resample_iq_for_demod_with_profile(capture_rate: float):
    profile = profile_for_sample_rate(capture_rate)
    bw = 200_000.0
    target = compute_target_demod_rate(bw, profile, audio_rate=48_000)
    iq = _synthetic_fm_iq(capture_rate, n=min(int(capture_rate // 100), 80_000))
    out, sr = resample_iq_for_demod(
        iq,
        capture_rate,
        bw,
        oversample=profile.oversample,
        min_rate=profile.iq_demod_min_hz,
        max_rate=profile.iq_demod_max_hz,
        target_rate=target,
    )
    assert sr <= capture_rate + 1.0
    assert sr >= profile.iq_demod_min_hz * 0.9
    assert sr <= profile.iq_demod_max_hz * 1.05
    assert len(out) <= len(iq)


@pytest.mark.parametrize("capture_rate", BANDWIDTH_PRESETS)
def test_demod_wbfm_all_presets(capture_rate: float):
    profile = profile_for_sample_rate(capture_rate)
    bw = default_passband_width("wbfm")
    iq = _synthetic_fm_iq(capture_rate)
    audio = demodulate(
        iq,
        mode="wbfm",
        sample_rate=capture_rate,
        audio_rate=48_000,
        passband_width_hz=bw,
        fm_deemphasis_us=50.0,
        profile=profile,
    )
    assert audio.size > 0
    assert float(np.max(np.abs(audio))) > 0
    duration = len(iq) / capture_rate
    expected = int(duration * 48_000)
    assert abs(len(audio) - expected) <= max(expected * 0.05, 48)


@pytest.mark.parametrize(
    ("mode", "capture_rate"),
    [
        ("nbfm", 250_000),
        ("am", 500_000),
        ("usb", 250_000),
        ("lsb", 500_000),
    ],
)
def test_demod_modes_recommended_presets(mode: str, capture_rate: float):
    profile = profile_for_sample_rate(capture_rate)
    bw = default_passband_width(mode)
    n = min(int(capture_rate // 20), 40_000)
    iq = _synthetic_fm_iq(capture_rate, n=n, mod_hz=800.0)
    audio = demodulate(
        iq,
        mode=mode,
        sample_rate=capture_rate,
        audio_rate=48_000,
        passband_width_hz=bw,
        profile=profile,
    )
    assert audio.size > 0


def test_resample_audio_to_rate_exact_48k():
    sr_in = 560_000 / 11  # ~50.9 kHz caso previo
    n_in = int(sr_in * 0.01)
    audio = np.sin(2 * np.pi * 1000 * np.arange(n_in) / sr_in).astype(np.float32)
    out = resample_audio_to_rate(audio, sr_in, 48_000)
    expected = int(round(n_in * 48_000 / sr_in))
    assert abs(len(out) - expected) <= 2


def test_wbfm_golden_rms_similar_2048_vs_8mhz():
    """Regresión: calidad audio WBFM no debe degradar entre 2M y 8M."""
    bw = 200_000.0
    n = 80_000
    iq = _synthetic_fm_iq(2_048_000, n=n)
    state_a = FmDemodState()
    state_b = FmDemodState()
    a = demodulate(
        iq,
        mode="wbfm",
        sample_rate=2_048_000,
        audio_rate=48_000,
        passband_width_hz=bw,
        fm_deemphasis_us=50.0,
        fm_state=state_a,
    )
    b = demodulate(
        iq,
        mode="wbfm",
        sample_rate=8_000_000,
        audio_rate=48_000,
        passband_width_hz=bw,
        fm_deemphasis_us=50.0,
        fm_state=state_b,
    )
    rms_a = float(np.sqrt(np.mean(a.astype(np.float64) ** 2)))
    rms_b = float(np.sqrt(np.mean(b.astype(np.float64) ** 2)))
    if rms_a > 1e-6 and rms_b > 1e-6:
        delta_db = 20 * np.log10(rms_b / rms_a)
        assert abs(delta_db) < 9.0


def test_fm_state_continuity():
    iq = _synthetic_fm_iq(2_048_000, n=16_384)
    state = FmDemodState()
    first = demodulate(
        iq[:8192],
        mode="wbfm",
        sample_rate=2_048_000,
        audio_rate=48_000,
        fm_state=state,
    )
    second = demodulate(
        iq[8192:],
        mode="wbfm",
        sample_rate=2_048_000,
        audio_rate=48_000,
        fm_state=state,
    )
    assert state.last_filtered != 0j
    assert first.size > 0 and second.size > 0
