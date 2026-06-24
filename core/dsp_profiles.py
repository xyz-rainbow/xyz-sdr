"""
xyz-sdr | core/dsp_profiles.py
Perfiles DSP por preset IQ (BANDWIDTH) para calidad de audio y CPU predecibles.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.device import BANDWIDTH_PRESETS

# Techo SR demod para WBFM/NBFM en presets altos (4–8 MHz).
WBFM_MAX_DEMOD_SR = 768_000.0


@dataclass(frozen=True)
class PresetProfile:
    """Parámetros DSP recomendados para un preset IQ."""

    capture_rate_hz: float
    iq_demod_max_hz: float
    iq_demod_min_hz: float
    oversample: float
    chunk_scale: float
    fft_avg_cap: int | None
    audio_chunk_max: int
    recommended_modes: tuple[str, ...]


# Perfiles por preset (orden ascendente).
_PRESET_TABLE: tuple[PresetProfile, ...] = (
    PresetProfile(
        capture_rate_hz=250_000,
        iq_demod_max_hz=160_000,
        iq_demod_min_hz=80_000,
        oversample=2.5,
        chunk_scale=0.25,
        fft_avg_cap=8,
        audio_chunk_max=8192,
        recommended_modes=("nbfm", "am", "usb", "lsb"),
    ),
    PresetProfile(
        capture_rate_hz=500_000,
        iq_demod_max_hz=250_000,
        iq_demod_min_hz=100_000,
        oversample=2.5,
        chunk_scale=0.5,
        fft_avg_cap=8,
        audio_chunk_max=16384,
        recommended_modes=("am", "nbfm", "usb", "lsb"),
    ),
    PresetProfile(
        capture_rate_hz=1_000_000,
        iq_demod_max_hz=560_000,
        iq_demod_min_hz=250_000,
        oversample=2.8,
        chunk_scale=0.75,
        fft_avg_cap=8,
        audio_chunk_max=32768,
        recommended_modes=("wbfm", "nbfm", "am"),
    ),
    PresetProfile(
        capture_rate_hz=2_048_000,
        iq_demod_max_hz=560_000,
        iq_demod_min_hz=250_000,
        oversample=2.8,
        chunk_scale=1.0,
        fft_avg_cap=None,
        audio_chunk_max=65536,
        recommended_modes=("wbfm", "nbfm", "am"),
    ),
    PresetProfile(
        capture_rate_hz=4_000_000,
        iq_demod_max_hz=WBFM_MAX_DEMOD_SR,
        iq_demod_min_hz=250_000,
        oversample=2.8,
        chunk_scale=1.0,
        fft_avg_cap=4,
        audio_chunk_max=65536,
        recommended_modes=("wbfm", "nbfm", "am", "usb", "lsb"),
    ),
    PresetProfile(
        capture_rate_hz=8_000_000,
        iq_demod_max_hz=WBFM_MAX_DEMOD_SR,
        iq_demod_min_hz=250_000,
        oversample=2.8,
        chunk_scale=1.0,
        fft_avg_cap=4,
        audio_chunk_max=65536,
        recommended_modes=("wbfm", "nbfm", "am", "usb", "lsb"),
    ),
)


def profile_for_sample_rate(capture_rate_hz: float) -> PresetProfile:
    """Devuelve el perfil más cercano al sample rate de captura."""
    rate = float(capture_rate_hz)
    best = _PRESET_TABLE[0]
    best_delta = abs(rate - best.capture_rate_hz)
    for profile in _PRESET_TABLE:
        delta = abs(rate - profile.capture_rate_hz)
        if delta < best_delta:
            best = profile
            best_delta = delta
    return best


def compute_target_demod_rate(
    channel_bw_hz: float,
    profile: PresetProfile,
    *,
    audio_rate: float = 48_000,
) -> float:
    """Tasa IQ objetivo para demodulación según PASS y perfil."""
    bw = max(float(channel_bw_hz), 3_000.0)
    target = max(bw * profile.oversample, audio_rate * 8.0, profile.iq_demod_min_hz)
    target = min(target, profile.iq_demod_max_hz)
    return target


def effective_fft_avg(num_avg: int, profile: PresetProfile) -> int:
    if profile.fft_avg_cap is None:
        return num_avg
    return min(num_avg, profile.fft_avg_cap)


def is_mode_recommended(mode: str, profile: PresetProfile) -> bool:
    return mode in profile.recommended_modes


def all_preset_rates() -> tuple[float, ...]:
    return BANDWIDTH_PRESETS
