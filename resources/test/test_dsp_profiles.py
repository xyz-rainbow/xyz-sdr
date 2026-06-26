"""Tests for core/dsp_profiles.py -- preset DSP profile selection + clamping."""

from __future__ import annotations

import pytest

from core.device import BANDWIDTH_PRESETS
from core.dsp_profiles import (
    PresetProfile,
    all_preset_rates,
    compute_target_demod_rate,
    effective_fft_avg,
    is_mode_recommended,
    profile_for_sample_rate,
)


def test_profile_for_sample_rate_picks_exact_match() -> None:
    p = profile_for_sample_rate(2_048_000)
    assert p.capture_rate_hz == 2_048_000
    assert "wbfm" in p.recommended_modes


def test_profile_for_sample_rate_picks_nearest() -> None:
    # 1.9M is closer to 2_048_000 than to 1_000_000.
    p = profile_for_sample_rate(1_900_000)
    assert p.capture_rate_hz == 2_048_000

    # 600k closer to 500k than to 1M.
    p = profile_for_sample_rate(600_000)
    assert p.capture_rate_hz == 500_000


def test_profile_for_sample_rate_below_lowest_uses_lowest() -> None:
    p = profile_for_sample_rate(50_000)
    # Lowest preset is 250_000.
    assert p.capture_rate_hz == 250_000


def test_compute_target_demod_rate_clamps_to_profile_max() -> None:
    p = profile_for_sample_rate(2_048_000)
    # Huge BW -> clamped to iq_demod_max_hz.
    rate = compute_target_demod_rate(1_000_000, p, audio_rate=48_000)
    assert rate == p.iq_demod_max_hz


def test_compute_target_demod_rate_floor_on_tiny_bw() -> None:
    p = profile_for_sample_rate(2_048_000)
    rate = compute_target_demod_rate(500, p, audio_rate=48_000)
    # min(audio_rate*8, iq_demod_min_hz) clamped via max(...)
    assert rate >= p.iq_demod_min_hz


def test_compute_target_demod_rate_oversamples_bw() -> None:
    p = profile_for_sample_rate(250_000)
    # 250k profile: iq_demod_max_hz=160_000, iq_demod_min_hz=80_000, oversample=2.5.
    # bw=10k -> target = max(25k, 384k, 80k) = 384k -> clamped to 160_000.
    rate = compute_target_demod_rate(10_000, p, audio_rate=48_000)
    assert rate == pytest.approx(160_000)


def test_effective_fft_avg_caps_at_profile_limit() -> None:
    p = profile_for_sample_rate(250_000)
    # profile.fft_avg_cap=8 -> num_avg=64 capped to 8.
    assert effective_fft_avg(64, p) == 8


def test_effective_fft_avg_passthrough_when_no_cap() -> None:
    # profile_for_sample_rate(2_048_000).fft_avg_cap is None.
    p = profile_for_sample_rate(2_048_000)
    assert p.fft_avg_cap is None
    assert effective_fft_avg(64, p) == 64


def test_is_mode_recommended_membership() -> None:
    p = profile_for_sample_rate(2_048_000)
    assert is_mode_recommended("wbfm", p) is True
    assert is_mode_recommended("xyz", p) is False


def test_all_preset_rates_matches_bandwidth_presets() -> None:
    assert all_preset_rates() == BANDWIDTH_PRESETS