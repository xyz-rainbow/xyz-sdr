"""
xyz-sdr | core/dsp.py
Procesado digital de señal: FFT, demodulación FM/AM/SSB, filtros.
"""

from __future__ import annotations

import math
from fractions import Fraction
from dataclasses import dataclass, field

import numpy as np
from scipy import signal as scipy_signal
from typing import Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from core.dsp_profiles import PresetProfile

DemodMode = Literal["wbfm", "nbfm", "am", "usb", "lsb"]

# Headroom fijo tras normalización; el volumen de usuario se aplica en audio_output.
NORMALIZE_LEVEL = 0.35

# Referencia para escalar lecturas IQ del worker RX (~16 ventanas FFT a 2.048 MHz)
RX_REFERENCE_SAMPLE_RATE = 2_048_000.0
RX_REFERENCE_FFT_WINDOWS = 16

DEFAULT_FFT_MAX = 65_536
DEFAULT_BAND_COLS_MAX = 4096
DEFAULT_TARGET_BINS_PER_COLUMN = 4.0

_HANN_CACHE: dict[int, np.ndarray] = {}


def _hann_window(fft_size: int) -> np.ndarray:
    win = _HANN_CACHE.get(fft_size)
    if win is None:
        win = scipy_signal.get_window("hann", fft_size)
        _HANN_CACHE[fft_size] = win
    return win

def round_fft_size(size: int, *, minimum: int = 256, maximum: int = DEFAULT_FFT_MAX) -> int:
    """Redondea a la potencia de 2 más cercana dentro de [minimum, maximum]."""
    size = max(minimum, min(maximum, int(size)))
    if size <= minimum:
        return minimum
    power = 1 << int(math.ceil(math.log2(size)))
    return min(power, maximum)


def compute_effective_fft_size(
    base_fft: int,
    sample_rate: float,
    visible_span: float,
    *,
    display_width: int = 120,
    target_bins_per_column: float = DEFAULT_TARGET_BINS_PER_COLUMN,
    min_fft: int = 4096,
    max_fft: int = DEFAULT_FFT_MAX,
) -> int:
    """
    Escala el tamaño FFT al hacer zoom para mantener bins suficientes en el viewport.

    Cuando visible_span << sample_rate, aumenta la resolución espectral para que
    espectro y waterfall tengan varios bins por columna de pantalla.
    """
    base_fft = round_fft_size(base_fft, minimum=min_fft // 2, maximum=max_fft)
    if sample_rate <= 0 or visible_span <= 0 or visible_span >= sample_rate * 0.99:
        return base_fft

    width = max(display_width, 40)
    required = int(width * target_bins_per_column * (sample_rate / visible_span))
    return round_fft_size(max(base_fft, required), minimum=min_fft, maximum=max_fft)


def compute_effective_band_cols(
    base_cols: int,
    sample_rate: float,
    visible_span: float,
    *,
    display_width: int = 120,
    target_cols_per_column: float = DEFAULT_TARGET_BINS_PER_COLUMN,
    min_cols: int = 256,
    max_cols: int = DEFAULT_BAND_COLS_MAX,
) -> int:
    """
    Escala la rejilla interna de banda al hacer zoom para mantener celdas
    suficientes por columna de terminal al re-slicear espectro y waterfall.
    """
    base_cols = max(min_cols, min(max_cols, int(base_cols)))
    if sample_rate <= 0 or visible_span <= 0 or visible_span >= sample_rate * 0.99:
        return base_cols

    width = max(display_width, 40)
    required = int(width * target_cols_per_column * (sample_rate / visible_span))
    return max(base_cols, min(required, max_cols))


def map_psd_to_columns(
    psd: np.ndarray,
    capture_center_hz: float,
    sample_rate: float,
    viewport_center_hz: float,
    visible_span_hz: float,
    width: int,
) -> np.ndarray:
    """
    Mapea bins PSD a columnas de pantalla con agregación de picos (máximo) optimizada mediante NumPy.
    """
    width = max(width, 1)
    col_values = np.full(width, np.nan, dtype=np.float64)

    if psd is None or len(psd) == 0 or sample_rate <= 0 or visible_span_hz <= 0:
        return col_values

    left_hz = viewport_center_hz - visible_span_hz / 2
    hz_per_col = visible_span_hz / width
    capture_left = capture_center_hz - sample_rate / 2
    capture_right = capture_center_hz + sample_rate / 2
    psd_len = len(psd)
    hz_per_bin = sample_rate / psd_len

    cols = np.arange(width)
    f_starts = left_hz + cols * hz_per_col
    f_ends = left_hz + (cols + 1) * hz_per_col

    overlap_starts = np.maximum(f_starts, capture_left)
    overlap_ends = np.minimum(f_ends, capture_right)
    valid_overlap = overlap_starts < overlap_ends

    if not np.any(valid_overlap):
        return col_values

    bin_starts = ((overlap_starts - capture_left) / hz_per_bin).astype(np.int32)
    bin_ends = ((overlap_ends - capture_left) / hz_per_bin).astype(np.int32)

    bin_starts = np.clip(bin_starts, 0, psd_len - 1)
    bin_ends = np.clip(bin_ends, bin_starts + 1, psd_len)

    lengths = bin_ends - bin_starts
    single_bin = (lengths == 1) & valid_overlap
    col_values[single_bin] = psd[bin_starts[single_bin]]

    multi_bin = (lengths > 1) & valid_overlap
    valid_indices = np.where(multi_bin)[0]
    for col in valid_indices:
        col_values[col] = float(np.max(psd[bin_starts[col]:bin_ends[col]]))

    return col_values

def compute_psd(
    samples: np.ndarray,
    fft_size: int = 2048,
    sample_rate: float = 2.048e6,
    window: str = "hann",
) -> tuple[np.ndarray, np.ndarray]:
    """
    Calcula la densidad espectral de potencia (PSD) en dBFS.

    Returns:
        freqs_mhz : array de frecuencias relativas en MHz
        psd_db    : potencia en dBFS
    """
    n = min(len(samples), fft_size)
    samples = samples[:n]

    win    = scipy_signal.get_window(window, n)
    fft    = np.fft.fftshift(np.fft.fft(samples * win, n=fft_size))
    psd    = 20 * np.log10(np.abs(fft) / fft_size + 1e-12)

    freqs  = np.fft.fftshift(np.fft.fftfreq(fft_size, d=1.0/sample_rate))
    return freqs / 1e6, psd


def average_psd(
    samples: np.ndarray,
    fft_size: int = 2048,
    sample_rate: float = 2.048e6,
    num_avg: int = 8,
    overlap: float = 0.5,
) -> tuple[np.ndarray, np.ndarray]:
    """PSD promediada sobre `num_avg` ventanas para reducir ruido."""
    overlap = max(0.0, min(0.95, float(overlap)))
    step   = max(1, int(fft_size * (1.0 - overlap)))
    total  = len(samples)
    accum  = np.zeros(fft_size)
    count  = 0

    for i in range(0, total - fft_size, step):
        chunk = samples[i:i + fft_size]
        win = _hann_window(fft_size)
        fft   = np.fft.fftshift(np.fft.fft(chunk * win, n=fft_size))
        accum += np.abs(fft) ** 2
        count += 1
        if count >= num_avg:
            break

    if count == 0:
        count = 1

    psd   = 10 * np.log10(accum / count / fft_size + 1e-12)
    freqs = np.fft.fftshift(np.fft.fftfreq(fft_size, d=1.0/sample_rate))
    return freqs / 1e6, psd


def compute_rx_chunk_samples(
    fft_size: int,
    sample_rate: float,
    num_avg: int = 8,
    reference_rate: float = RX_REFERENCE_SAMPLE_RATE,
    reference_windows: int = RX_REFERENCE_FFT_WINDOWS,
    max_samples: int = 256 * 1024 * 4,
    *,
    chunk_scale: float = 1.0,
    low_rate_scale: float | None = None,
) -> int:
    """Calcula cuántas muestras IQ leer por iteración del worker RX."""
    min_samples = fft_size * max(num_avg + 2, 8)
    reference_chunk = fft_size * reference_windows
    scaled = int(reference_chunk * (sample_rate / reference_rate))
    if low_rate_scale is not None and sample_rate < 500_000:
        scaled = int(scaled * low_rate_scale)
    chunk = max(min_samples, scaled)
    chunk = int(chunk * max(chunk_scale, 0.1))
    chunk = max(fft_size, (chunk // fft_size) * fft_size)
    return min(chunk, max_samples)


def compute_audio_chunk_samples(
    fft_chunk: int,
    sample_rate: float,
    *,
    audio_chunk_max: int = 65_536,
    fft_size: int = 8192,
) -> int:
    """Tamaño IQ para demod audio (Phase 3: desacople espectro/audio)."""
    if sample_rate <= 500_000:
        target = min(audio_chunk_max, max(fft_size * 4, 4096))
    else:
        target = min(audio_chunk_max, max(fft_size * 8, fft_chunk // 2))
    target = max(fft_size, (target // fft_size) * fft_size)
    return min(target, fft_chunk)


# ─── Filtros ────────────────────────────────────────────────────────────────

def _adaptive_fir_order(
    cutoff_hz: float,
    sample_rate: float,
    *,
    min_order: int = 63,
    max_order: int = 4095,
) -> int:
    """Más taps cuando el corte es muy bajo respecto a la tasa (p. ej. WBFM @ 8 MHz)."""
    nyq = sample_rate / 2
    if cutoff_hz >= nyq * 0.95:
        return min_order
    transition_hz = max(cutoff_hz * 0.25, 1_500.0)
    order = int(3.3 * sample_rate / transition_hz)
    order = max(min_order, min(order, max_order))
    if order % 2 == 0:
        order += 1
    return order


def resample_iq_for_demod(
    samples: np.ndarray,
    sample_rate: float,
    channel_bw_hz: float,
    *,
    oversample: float = 2.8,
    min_rate: float = 250_000,
    max_rate: float | None = None,
    target_rate: float | None = None,
) -> tuple[np.ndarray, float]:
    """
    Reduce la tasa IQ antes de demodular.

    Con bandwidth IQ alto (p. ej. 8 MHz) un filtro corto no rechaza el ruido fuera del
    PASS (~200 kHz WBFM); decimar IQ primero mejora mucho el audio FM.
    """
    if len(samples) == 0 or sample_rate <= 0:
        return samples, sample_rate
    bw = max(channel_bw_hz, 10_000.0)
    if target_rate is not None:
        target = min(float(sample_rate), max(float(target_rate), min_rate))
    else:
        target = max(bw * oversample, min_rate)
        if max_rate is not None:
            target = min(target, max_rate)
        target = min(float(sample_rate), target)
    if sample_rate <= target * 1.1:
        return samples, float(sample_rate)

    out = samples
    sr = float(sample_rate)
    while sr / target > 1.05:
        factor = min(max(int(sr / target), 2), 16)
        out = scipy_signal.resample_poly(out, 1, factor)
        sr /= factor
    return out.astype(samples.dtype, copy=False), sr


def resample_audio_to_rate(
    audio: np.ndarray,
    sample_rate_in: float,
    sample_rate_out: float = 48_000,
) -> np.ndarray:
    """Remuestrea audio a tasa exacta (p. ej. 48 kHz) vía resample_poly racional."""
    if audio is None or len(audio) == 0 or sample_rate_in <= 0:
        return audio
    if abs(sample_rate_in - sample_rate_out) < 0.5:
        return np.asarray(audio, dtype=np.float32).ravel()
    ratio = Fraction(sample_rate_out / sample_rate_in).limit_denominator(1000)
    out = scipy_signal.resample_poly(
        np.asarray(audio, dtype=np.float64).ravel(),
        ratio.numerator,
        ratio.denominator,
    )
    return out.astype(np.float32, copy=False)


_FIR_TAPS_CACHE: dict[tuple[float, float, int], np.ndarray] = {}


def _fir_filter_key(cutoff_hz: float, sample_rate: float, order: int) -> tuple[float, float, int]:
    return (float(cutoff_hz), float(sample_rate), int(order))


def _fir_taps(cutoff_hz: float, sample_rate: float, order: int | None) -> tuple[np.ndarray, int]:
    nyq = sample_rate / 2
    if order is None:
        order = _adaptive_fir_order(cutoff_hz, sample_rate)
    key = _fir_filter_key(cutoff_hz, sample_rate, order)
    taps = _FIR_TAPS_CACHE.get(key)
    if taps is None:
        taps = scipy_signal.firwin(order + 1, cutoff_hz / nyq)
        _FIR_TAPS_CACHE[key] = taps
    return taps, order


def low_pass_filter(
    samples: np.ndarray,
    cutoff_hz: float,
    sample_rate: float,
    order: int | None = None,
    *,
    zi: np.ndarray | None = None,
) -> np.ndarray | tuple[np.ndarray, np.ndarray]:
    """Filtro paso bajo FIR (orden adaptativo si no se indica)."""
    nyq = sample_rate / 2
    if cutoff_hz >= nyq * 0.99:
        if zi is not None:
            return samples, zi
        return samples
    taps, _ = _fir_taps(cutoff_hz, sample_rate, order)
    if zi is not None:
        out, zf = scipy_signal.lfilter(taps, 1.0, samples, zi=zi)
        return out, zf
    return scipy_signal.lfilter(taps, 1.0, samples)


def low_pass_filter_with_state(
    samples: np.ndarray,
    cutoff_hz: float,
    sample_rate: float,
    state: FmDemodState | None,
    order: int | None = None,
) -> np.ndarray:
    """Filtro paso bajo con continuidad entre chunks vía FmDemodState."""
    nyq = sample_rate / 2
    if cutoff_hz >= nyq * 0.99:
        return samples
    taps, order = _fir_taps(cutoff_hz, sample_rate, order)
    key = _fir_filter_key(cutoff_hz, sample_rate, order)
    zi = None
    if state is not None:
        zi = state.lp_zi.get(key)
    if zi is None:
        zi = np.zeros(len(taps) - 1, dtype=np.float64)
    out, zf = scipy_signal.lfilter(taps, 1.0, samples, zi=zi)
    if state is not None:
        state.lp_zi[key] = zf
    return out


def decimate(samples: np.ndarray, factor: int) -> np.ndarray:
    """Diezma la señal por `factor` con anti-aliasing."""
    return scipy_signal.decimate(samples, factor, zero_phase=True)


def shift_to_baseband(
    samples: np.ndarray,
    offset_hz: float,
    sample_rate: float,
    state: FmDemodState | None = None,
) -> np.ndarray:
    """Mezcla la señal para centrar offset_hz en DC con continuidad de fase."""
    if offset_hz == 0 or len(samples) == 0:
        return samples
    t = np.arange(len(samples), dtype=np.float64) / sample_rate
    if state is not None:
        phase = state.lo_phase - 2 * np.pi * offset_hz * t
        state.lo_phase = (state.lo_phase - 2 * np.pi * offset_hz * len(samples) / sample_rate) % (2 * np.pi)
    else:
        phase = -2 * np.pi * offset_hz * t
    rotator = np.exp(1j * phase)
    return (samples * rotator).astype(samples.dtype, copy=False)


def fm_deemphasis(
    audio: np.ndarray,
    sample_rate: float,
    *,
    tau_us: float = 75.0,
    zi: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Filtro de de-emphasis FM (tau típico 75 µs América / 50 µs Europa).

    Implementación IIR estándar: y[n] = x[n] + alpha * y[n-1].
    Devuelve (audio, estado) para continuidad entre chunks.
    """
    if tau_us <= 0 or len(audio) == 0:
        empty_zi = np.zeros(1, dtype=np.float64)
        return audio, empty_zi if zi is None else zi
    tau_s = tau_us * 1e-6
    alpha = math.exp(-1.0 / (sample_rate * tau_s))
    b = np.array([1.0], dtype=np.float64)
    a = np.array([1.0, -alpha], dtype=np.float64)
    if zi is None:
        zi = np.zeros(1, dtype=np.float64)
    out, zf = scipy_signal.lfilter(b, a, audio.astype(np.float64, copy=False), zi=zi)
    return out.astype(np.float32), zf


def _normalize_audio(audio: np.ndarray) -> np.ndarray:
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * NORMALIZE_LEVEL
    return audio.astype(np.float32)


class AudioAgc:
    """AGC post-demod por chunks con ataque/release suaves."""

    def __init__(
        self,
        target_rms: float = 0.12,
        max_gain: float = 8.0,
        min_gain: float = 0.05,
        attack_ms: float = 8.0,
        release_ms: float = 250.0,
    ):
        self.target_rms = target_rms
        self.max_gain = max_gain
        self.min_gain = min_gain
        self.attack_ms = attack_ms
        self.release_ms = release_ms
        self._gain = 1.0

    def configure(
        self,
        *,
        target_rms: float | None = None,
        max_gain: float | None = None,
        attack_ms: float | None = None,
        release_ms: float | None = None,
    ) -> None:
        if target_rms is not None:
            self.target_rms = max(1e-4, target_rms)
        if max_gain is not None:
            self.max_gain = max(1.0, max_gain)
        if attack_ms is not None:
            self.attack_ms = max(0.1, attack_ms)
        if release_ms is not None:
            self.release_ms = max(1.0, release_ms)

    def reset(self) -> None:
        self._gain = 1.0

    def process(self, audio: np.ndarray, sample_rate: float = 48_000) -> np.ndarray:
        if audio is None or len(audio) == 0:
            return audio
        rms = float(np.sqrt(np.mean(np.square(audio.astype(np.float64)))))
        if rms < 1e-8:
            return audio
        desired = float(np.clip(self.target_rms / rms, self.min_gain, self.max_gain))
        chunk_ms = (len(audio) / max(sample_rate, 1.0)) * 1000.0
        tau = self.attack_ms if desired > self._gain else self.release_ms
        alpha = math.exp(-chunk_ms / max(tau, 0.1))
        self._gain = desired + (self._gain - desired) * alpha
        out = audio.astype(np.float32, copy=False) * self._gain
        return np.clip(out, -1.0, 1.0).astype(np.float32)


def apply_fm_agc(
    audio: np.ndarray,
    gate: AudioAgc,
    *,
    enabled: bool,
    sample_rate: float = 48_000,
) -> np.ndarray:
    """Aplica AGC FM reutilizando estado entre chunks RX."""
    if not enabled or audio is None or len(audio) == 0:
        return audio
    return gate.process(audio, sample_rate)


@dataclass
class FmDemodState:
    """Estado entre chunks para discriminador FM, de-emphasis y LO/SSB phase."""

    last_filtered: complex = 0j
    deemph_zi: np.ndarray = field(default_factory=lambda: np.zeros(1, dtype=np.float64))
    lo_phase: float = 0.0
    ssb_phase: float = 0.0
    lp_zi: dict[tuple[float, float, int], np.ndarray] = field(default_factory=dict)

    def reset(self) -> None:
        self.last_filtered = 0j
        self.deemph_zi = np.zeros(1, dtype=np.float64)
        self.lo_phase = 0.0
        self.ssb_phase = 0.0
        self.lp_zi.clear()


def _iq_demod_kwargs(
    profile: PresetProfile | None,
    channel_bw_hz: float,
    audio_rate: float,
) -> dict:
    if profile is None:
        return {}
    from core.dsp_profiles import compute_target_demod_rate

    target = compute_target_demod_rate(channel_bw_hz, profile, audio_rate=audio_rate)
    return {
        "oversample": profile.oversample,
        "min_rate": profile.iq_demod_min_hz,
        "max_rate": profile.iq_demod_max_hz,
        "target_rate": target,
    }


def _fm_discriminator(
    filtered: np.ndarray,
    state: FmDemodState | None,
) -> np.ndarray:
    """Discriminador de fase con continuidad opcional entre chunks."""
    if len(filtered) < 2:
        return np.zeros(0, dtype=np.float64)
    if state is not None and state.last_filtered != 0j:
        extended = np.empty(len(filtered) + 1, dtype=filtered.dtype)
        extended[0] = state.last_filtered
        extended[1:] = filtered
        demod = np.angle(extended[1:] * np.conj(extended[:-1]))
        state.last_filtered = complex(filtered[-1])
    else:
        demod = np.angle(filtered[1:] * np.conj(filtered[:-1]))
        if state is not None and len(filtered) > 0:
            state.last_filtered = complex(filtered[-1])
    return demod.astype(np.float64, copy=False)


def _audio_from_demod(
    demod: np.ndarray,
    sample_rate: float,
    audio_rate: float,
) -> np.ndarray:
    return resample_audio_to_rate(demod, sample_rate, audio_rate)


# ─── Demoduladores ──────────────────────────────────────────────────────────

def demod_wbfm(
    samples: np.ndarray,
    sample_rate: float = 2.048e6,
    audio_rate: float = 48_000,
    *,
    bandwidth_hz: float = 200_000,
    fm_deemphasis_us: float = 75.0,
    frequency_offset_hz: float = 0.0,
    fm_state: FmDemodState | None = None,
    profile: PresetProfile | None = None,
) -> np.ndarray:
    """
    Demodulador FM de banda ancha (WBFM).
    Ideal para radio FM comercial (88-108 MHz).
    """
    if frequency_offset_hz:
        samples = shift_to_baseband(samples, frequency_offset_hz, sample_rate, fm_state)

    bw = max(bandwidth_hz, 10_000.0)
    resample_kw = _iq_demod_kwargs(profile, bw, audio_rate)
    samples, sample_rate = resample_iq_for_demod(samples, sample_rate, bw, **resample_kw)
    filtered = low_pass_filter_with_state(samples, bw / 2, sample_rate, fm_state)

    demod = _fm_discriminator(filtered, fm_state)
    audio = _audio_from_demod(demod, sample_rate, audio_rate)

    if fm_state is not None:
        audio, fm_state.deemph_zi = fm_deemphasis(
            audio, audio_rate, tau_us=fm_deemphasis_us, zi=fm_state.deemph_zi
        )
    else:
        audio, _ = fm_deemphasis(audio, audio_rate, tau_us=fm_deemphasis_us)
    return _normalize_audio(audio)


def demod_nbfm(
    samples: np.ndarray,
    sample_rate: float = 2.048e6,
    audio_rate: float = 48_000,
    deviation: float = 5_000,
    *,
    bandwidth_hz: float | None = None,
    fm_deemphasis_us: float = 75.0,
    frequency_offset_hz: float = 0.0,
    fm_state: FmDemodState | None = None,
    profile: PresetProfile | None = None,
) -> np.ndarray:
    """
    Demodulador FM de banda estrecha (NBFM).
    Ideal para comunicaciones de radioaficionados, PMR, etc.
    """
    if frequency_offset_hz:
        samples = shift_to_baseband(samples, frequency_offset_hz, sample_rate, fm_state)

    bw = bandwidth_hz if bandwidth_hz is not None else deviation * 2.5
    bw = max(float(bw), 3_000.0)
    resample_kw = _iq_demod_kwargs(profile, bw, audio_rate)
    samples, sample_rate = resample_iq_for_demod(samples, sample_rate, bw, **resample_kw)
    filtered = low_pass_filter_with_state(samples, bw / 2, sample_rate, fm_state)

    demod = _fm_discriminator(filtered, fm_state)
    demod = demod / (2 * np.pi * deviation / sample_rate)
    audio = _audio_from_demod(demod, sample_rate, audio_rate)

    if fm_state is not None:
        audio, fm_state.deemph_zi = fm_deemphasis(
            audio, audio_rate, tau_us=fm_deemphasis_us, zi=fm_state.deemph_zi
        )
    else:
        audio, _ = fm_deemphasis(audio, audio_rate, tau_us=fm_deemphasis_us)
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = np.clip(audio / peak, -1, 1) * NORMALIZE_LEVEL
    return audio.astype(np.float32)


def demod_am(
    samples: np.ndarray,
    sample_rate: float = 2.048e6,
    audio_rate: float = 48_000,
    *,
    bandwidth_hz: float = 5_000,
    frequency_offset_hz: float = 0.0,
    fm_state: FmDemodState | None = None,
    profile: PresetProfile | None = None,
) -> np.ndarray:
    """
    Demodulador AM (detección de envolvente).
    """
    if frequency_offset_hz:
        samples = shift_to_baseband(samples, frequency_offset_hz, sample_rate, fm_state)

    audio_bw = max(bandwidth_hz, 1_000.0)
    resample_kw = _iq_demod_kwargs(profile, audio_bw, audio_rate)
    samples, sample_rate = resample_iq_for_demod(samples, sample_rate, audio_bw, **resample_kw)

    envelope = np.abs(samples)
    envelope -= np.mean(envelope)

    filtered = low_pass_filter_with_state(envelope, audio_bw / 2, sample_rate, fm_state)
    audio = _audio_from_demod(filtered.astype(np.float64), sample_rate, audio_rate)
    return _normalize_audio(audio)


def demod_ssb(
    samples: np.ndarray,
    sample_rate: float = 2.048e6,
    audio_rate: float = 48_000,
    mode: Literal["usb", "lsb"] = "usb",
    *,
    bandwidth_hz: float = 3_000,
    frequency_offset_hz: float = 0.0,
    fm_state: FmDemodState | None = None,
    profile: PresetProfile | None = None,
) -> np.ndarray:
    """
    Demodulador SSB (USB/LSB).
    Ideal para radioaficionados en HF.
    """
    bw = max(float(bandwidth_hz), 1_500.0)

    if frequency_offset_hz:
        samples = shift_to_baseband(samples, frequency_offset_hz, sample_rate, fm_state)

    resample_kw = _iq_demod_kwargs(profile, bw, audio_rate)
    samples, sample_rate = resample_iq_for_demod(samples, sample_rate, bw, **resample_kw)

    if mode == "lsb":
        t = np.arange(len(samples)) / sample_rate
        if fm_state is not None:
            phase = fm_state.ssb_phase - 2 * np.pi * bw * t
            fm_state.ssb_phase = (fm_state.ssb_phase - 2 * np.pi * bw * len(samples) / sample_rate) % (2 * np.pi)
        else:
            phase = -2 * np.pi * bw * t
        samples = samples * np.exp(1j * phase)

    filtered = low_pass_filter_with_state(samples, bw / 2, sample_rate, fm_state)
    audio = _audio_from_demod(filtered.real.astype(np.float64), sample_rate, audio_rate)
    return _normalize_audio(audio)


def demod_raw(
    samples: np.ndarray,
    sample_rate: float = 2.048e6,
    audio_rate: float = 48_000,
    *,
    frequency_offset_hz: float = 0.0,
    fm_state: FmDemodState | None = None,
) -> np.ndarray:
    """Demodulador RAW — convierte la parte real de la señal IQ a audio real directamente."""
    if frequency_offset_hz:
        samples = shift_to_baseband(samples, frequency_offset_hz, sample_rate, fm_state)
    audio = samples.real.astype(np.float64)
    resampled = resample_audio_to_rate(audio, sample_rate, audio_rate)
    return _normalize_audio(resampled)


# ─── Router de demodulación ─────────────────────────────────────────────────

def demodulate(
    samples: np.ndarray,
    mode: DemodMode = "wbfm",
    sample_rate: float = 2.048e6,
    audio_rate: float = 48_000,
    *,
    passband_width_hz: float | None = None,
    fm_deemphasis_us: float = 75.0,
    frequency_offset_hz: float = 0.0,
    fm_state: FmDemodState | None = None,
    profile: PresetProfile | None = None,
) -> np.ndarray:
    """Demodula según el modo especificado. Retorna audio float32 @ audio_rate."""
    from core.dsp_profiles import profile_for_sample_rate

    if profile is None:
        profile = profile_for_sample_rate(sample_rate)
    offset_kw = {"frequency_offset_hz": frequency_offset_hz, "profile": profile}
    deemph_kw = {"fm_deemphasis_us": fm_deemphasis_us}
    fm_kw = {"fm_state": fm_state}

    if mode == "wbfm":
        bw = passband_width_hz if passband_width_hz is not None else 200_000
        return demod_wbfm(
            samples,
            sample_rate,
            audio_rate,
            bandwidth_hz=bw,
            **deemph_kw,
            **offset_kw,
            **fm_kw,
        )
    if mode == "nbfm":
        bw = passband_width_hz
        return demod_nbfm(
            samples,
            sample_rate,
            audio_rate,
            bandwidth_hz=bw,
            **deemph_kw,
            **offset_kw,
            **fm_kw,
        )
    if mode == "am":
        bw = passband_width_hz if passband_width_hz is not None else 5_000
        return demod_am(
            samples,
            sample_rate,
            audio_rate,
            bandwidth_hz=bw,
            **offset_kw,
            **fm_kw,
        )
    if mode == "usb":
        bw = passband_width_hz if passband_width_hz is not None else 3_000
        return demod_ssb(
            samples,
            sample_rate,
            audio_rate,
            "usb",
            bandwidth_hz=bw,
            **offset_kw,
            **fm_kw,
        )
    if mode == "lsb":
        bw = passband_width_hz if passband_width_hz is not None else 3_000
        return demod_ssb(
            samples,
            sample_rate,
            audio_rate,
            "lsb",
            bandwidth_hz=bw,
            **offset_kw,
            **fm_kw,
        )
    if mode == "cw":
        bw = passband_width_hz if passband_width_hz is not None else 800.0
        bfo_offset = frequency_offset_hz + 800.0
        return demod_ssb(
            samples,
            sample_rate,
            audio_rate,
            "usb",
            bandwidth_hz=bw,
            frequency_offset_hz=bfo_offset,
            fm_state=fm_state,
            profile=profile,
        )
    if mode == "dsb":
        bw = passband_width_hz if passband_width_hz is not None else 6_000.0
        return demod_am(
            samples,
            sample_rate,
            audio_rate,
            bandwidth_hz=bw,
            **offset_kw,
            **fm_kw,
        )
    if mode == "raw":
        return demod_raw(
            samples,
            sample_rate,
            audio_rate,
            frequency_offset_hz=frequency_offset_hz,
            fm_state=fm_state,
        )

    # ── Plugins externos (entry_points) ─────────────────────────────────
    # Si el mode no es builtin, busca en plugins descubiertos.
    # Permite a usuarios añadir modos demod custom sin tocar el core.
    try:
        from core.plugins import discover_demodulators
        for plugin_name, plugin in discover_demodulators().items():
            if plugin_name == mode:
                return plugin.demodulate(
                    samples,
                    sample_rate=sample_rate,
                    audio_rate=audio_rate,
                    passband_width_hz=passband_width_hz,
                    fm_deemphasis_us=fm_deemphasis_us,
                    frequency_offset_hz=frequency_offset_hz,
                )
    except Exception as exc:
        # Si el discovery falla, seguimos con el raise estándar
        import logging
        logging.getLogger(__name__).debug("Plugin discovery falló: %s", exc)

    raise ValueError(
        f"Modo desconocido: {mode}. Opciones builtin: wbfm, nbfm, am, usb, lsb, cw, dsb, raw. "
        f"Plugins: ver discover_demodulators()."
    )


# ─── Lista de modos (builtin + plugins) ──────────────────────────────────────


BUILTIN_DEMOD_MODES: tuple[str, ...] = (
    "wbfm", "nbfm", "am", "usb", "lsb", "cw", "dsb", "raw",
)


def list_demod_modes(*, include_plugins: bool = True) -> list[str]:
    """Lista todos los modos demod disponibles (builtin + plugins).

    Args:
        include_plugins: si True, consulta ``discover_demodulators()`` y añade
            los nombres de plugins externos.

    Returns:
        Lista ordenada de nombres de modo.
    """
    modes = list(BUILTIN_DEMOD_MODES)
    if include_plugins:
        try:
            from core.plugins import discover_demodulators
            for name in discover_demodulators().keys():
                if name not in modes:
                    modes.append(name)
        except Exception:
            pass
    return sorted(modes)


# ─── Métricas ───────────────────────────────────────────────────────────────

def compute_snr(psd_db: np.ndarray, signal_idx: int, noise_window: int = 50) -> float:
    """Estima la SNR alrededor del índice de señal dado."""
    signal_power = psd_db[signal_idx]
    left  = max(0, signal_idx - noise_window)
    right = min(len(psd_db), signal_idx + noise_window)
    mask  = np.ones(len(psd_db), dtype=bool)
    mask[left:right] = False
    noise_power = np.mean(psd_db[mask]) if mask.any() else -100.0
    return float(signal_power - noise_power)


def estimate_snr_db(psd_db: np.ndarray) -> float:
    """SNR estimada para squelch: pico vs percentil 10 del ruido de fondo."""
    if psd_db is None or len(psd_db) == 0:
        return 0.0
    return float(np.max(psd_db) - np.percentile(psd_db, 10))


def estimate_snr_at_freq(
    psd_db: np.ndarray,
    center_hz: float,
    sample_rate: float,
    tuned_hz: float,
    *,
    noise_percentile: float = 10.0,
    guard_bins: int | None = None,
    passband_width_hz: float | None = None,
) -> float:
    """SNR en la frecuencia sintonizada (bin local vs ruido de fondo excluido)."""
    if psd_db is None or len(psd_db) == 0 or sample_rate <= 0:
        return 0.0

    psd_len = len(psd_db)
    hz_per_bin = sample_rate / psd_len
    capture_left = center_hz - sample_rate / 2
    bin_idx = int(round((tuned_hz - capture_left) / hz_per_bin))
    bin_idx = max(0, min(psd_len - 1, bin_idx))

    if guard_bins is not None:
        guard = guard_bins
    elif passband_width_hz and passband_width_hz > 0:
        guard = max(3, int(round((passband_width_hz / hz_per_bin) / 2)))
    else:
        guard = max(3, psd_len // 64)
    mask = np.ones(psd_len, dtype=bool)
    left = max(0, bin_idx - guard)
    right = min(psd_len, bin_idx + guard + 1)
    mask[left:right] = False

    signal_power = float(psd_db[bin_idx])
    if not mask.any():
        noise_power = float(np.percentile(psd_db, noise_percentile))
    else:
        noise_power = float(np.percentile(psd_db[mask], noise_percentile))
    return signal_power - noise_power


class SquelchGate:
    """Squelch con apertura inmediata y cierre retardado (hang time)."""

    def __init__(self, threshold_db: float = 15.0, hang_ms: float = 500.0):
        self.threshold_db = threshold_db
        self.hang_s = max(0.0, hang_ms) / 1000.0
        self._open = True
        self._hang_until = 0.0

    def configure(self, *, threshold_db: float | None = None, hang_ms: float | None = None) -> None:
        if threshold_db is not None:
            self.threshold_db = threshold_db
        if hang_ms is not None:
            self.hang_s = max(0.0, hang_ms) / 1000.0

    def is_open(self, snr_db: float, *, now: float | None = None) -> bool:
        import time

        ts = time.time() if now is None else now
        if snr_db >= self.threshold_db:
            self._open = True
            self._hang_until = ts + self.hang_s
            return True
        if self._open and ts < self._hang_until:
            return True
        self._open = False
        return False

    def reset(self) -> None:
        self._open = True
        self._hang_until = 0.0


def apply_squelch(
    audio: np.ndarray,
    snr_db: float,
    *,
    enabled: bool,
    threshold_db: float,
    gate: SquelchGate | None = None,
    hang_ms: float = 500.0,
) -> np.ndarray:
    """Silencia el audio si la SNR cae por debajo del umbral (con hang time opcional)."""
    if not enabled or audio is None or len(audio) == 0:
        return audio

    squelch_gate = gate
    if squelch_gate is None:
        squelch_gate = SquelchGate(threshold_db=threshold_db, hang_ms=hang_ms)
    else:
        squelch_gate.configure(threshold_db=threshold_db, hang_ms=hang_ms)

    if squelch_gate.is_open(snr_db):
        return audio
    return np.zeros_like(audio)


def apply_squelch_with_state(
    audio: np.ndarray,
    snr_db: float,
    gate: SquelchGate,
    *,
    enabled: bool,
    now: float | None = None,
) -> tuple[np.ndarray, bool]:
    """Aplica squelch reutilizando estado del gate. Devuelve (audio, is_open)."""
    if not enabled or audio is None or len(audio) == 0:
        return audio, True
    is_open = gate.is_open(snr_db, now=now)
    if is_open:
        return audio, True
    return np.zeros_like(audio), False
