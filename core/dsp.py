"""
xyz-sdr | core/dsp.py
Procesado digital de señal: FFT, demodulación FM/AM/SSB, filtros.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import signal as scipy_signal
from typing import Literal

DemodMode = Literal["wbfm", "nbfm", "am", "usb", "lsb"]

# Headroom fijo tras normalización; el volumen de usuario se aplica en audio_output.
NORMALIZE_LEVEL = 0.35

# Referencia para escalar lecturas IQ del worker RX (~16 ventanas FFT a 2.048 MHz)
RX_REFERENCE_SAMPLE_RATE = 2_048_000.0
RX_REFERENCE_FFT_WINDOWS = 16

DEFAULT_FFT_MAX = 65_536
DEFAULT_BAND_COLS_MAX = 4096
DEFAULT_TARGET_BINS_PER_COLUMN = 4.0


# ─── FFT / Espectro ─────────────────────────────────────────────────────────

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
    Mapea bins PSD a columnas de pantalla con agregación de picos (máximo).

    Usado por espectro y waterfall para garantizar la misma resolución visual.
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

    for col in range(width):
        f_start = left_hz + col * hz_per_col
        f_end = left_hz + (col + 1) * hz_per_col

        overlap_start = max(f_start, capture_left)
        overlap_end = min(f_end, capture_right)
        if overlap_start >= overlap_end:
            continue

        bin_start = int((overlap_start - capture_left) / hz_per_bin)
        bin_end = int((overlap_end - capture_left) / hz_per_bin)
        bin_start = max(0, min(bin_start, psd_len - 1))
        bin_end = max(bin_start + 1, min(bin_end, psd_len))
        col_values[col] = float(np.max(psd[bin_start:bin_end]))

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
        win   = scipy_signal.get_window("hann", fft_size)
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
) -> int:
    """Calcula cuántas muestras IQ leer por iteración del worker RX."""
    min_samples = fft_size * max(num_avg + 2, 8)
    reference_chunk = fft_size * reference_windows
    scaled = int(reference_chunk * (sample_rate / reference_rate))
    chunk = max(min_samples, scaled)
    chunk = max(fft_size, (chunk // fft_size) * fft_size)
    return min(chunk, max_samples)


# ─── Filtros ────────────────────────────────────────────────────────────────

def low_pass_filter(
    samples: np.ndarray,
    cutoff_hz: float,
    sample_rate: float,
    order: int = 64,
) -> np.ndarray:
    """Filtro paso bajo FIR."""
    nyq  = sample_rate / 2
    taps = scipy_signal.firwin(order + 1, cutoff_hz / nyq)
    return scipy_signal.lfilter(taps, 1.0, samples)


def decimate(samples: np.ndarray, factor: int) -> np.ndarray:
    """Diezma la señal por `factor` con anti-aliasing."""
    return scipy_signal.decimate(samples, factor, zero_phase=True)


def shift_to_baseband(
    samples: np.ndarray,
    offset_hz: float,
    sample_rate: float,
) -> np.ndarray:
    """Mezcla la señal para centrar offset_hz en DC."""
    if offset_hz == 0 or len(samples) == 0:
        return samples
    t = np.arange(len(samples), dtype=np.float64) / sample_rate
    rotator = np.exp(-1j * 2 * np.pi * offset_hz * t)
    return (samples * rotator).astype(samples.dtype, copy=False)


def fm_deemphasis(
    audio: np.ndarray,
    sample_rate: float,
    *,
    tau_us: float = 75.0,
) -> np.ndarray:
    """Filtro de de-emphasis FM (tau típico 75 µs América / 50 µs Europa)."""
    if tau_us <= 0 or len(audio) == 0:
        return audio
    tau_s = tau_us * 1e-6
    # y[n] = x[n] + alpha * (y[n-1] - x[n]); alpha = exp(-1/(fs*tau))
    alpha = math.exp(-1.0 / (sample_rate * tau_s))
    out = np.empty_like(audio, dtype=np.float64)
    prev_y = 0.0
    prev_x = 0.0
    for i, x in enumerate(audio.astype(np.float64, copy=False)):
        prev_y = float(x) + alpha * (prev_y - prev_x)
        prev_x = float(x)
        out[i] = prev_y
    return out.astype(np.float32)


def _normalize_audio(audio: np.ndarray) -> np.ndarray:
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * NORMALIZE_LEVEL
    return audio.astype(np.float32)


# ─── Demoduladores ──────────────────────────────────────────────────────────

def demod_wbfm(
    samples: np.ndarray,
    sample_rate: float = 2.048e6,
    audio_rate: float = 48_000,
    *,
    bandwidth_hz: float = 200_000,
    fm_deemphasis_us: float = 75.0,
    frequency_offset_hz: float = 0.0,
) -> np.ndarray:
    """
    Demodulador FM de banda ancha (WBFM).
    Ideal para radio FM comercial (88-108 MHz).
    """
    if frequency_offset_hz:
        samples = shift_to_baseband(samples, frequency_offset_hz, sample_rate)

    bw = max(bandwidth_hz, 10_000.0)
    filtered = low_pass_filter(samples, bw / 2, sample_rate)

    demod = np.angle(filtered[1:] * np.conj(filtered[:-1]))

    dec_factor = int(sample_rate / audio_rate)
    if dec_factor > 1:
        audio = decimate(demod, dec_factor)
    else:
        audio = demod

    audio = fm_deemphasis(audio, audio_rate, tau_us=fm_deemphasis_us)
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
) -> np.ndarray:
    """
    Demodulador FM de banda estrecha (NBFM).
    Ideal para comunicaciones de radioaficionados, PMR, etc.
    """
    if frequency_offset_hz:
        samples = shift_to_baseband(samples, frequency_offset_hz, sample_rate)

    bw = bandwidth_hz if bandwidth_hz is not None else deviation * 2.5
    filtered = low_pass_filter(samples, bw / 2, sample_rate)

    demod = np.angle(filtered[1:] * np.conj(filtered[:-1]))
    demod = demod / (2 * np.pi * deviation / sample_rate)

    dec_factor = int(sample_rate / audio_rate)
    if dec_factor > 1:
        audio = decimate(demod.real, dec_factor)
    else:
        audio = demod.real

    audio = fm_deemphasis(audio, audio_rate, tau_us=fm_deemphasis_us)
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
) -> np.ndarray:
    """
    Demodulador AM (detección de envolvente).
    """
    if frequency_offset_hz:
        samples = shift_to_baseband(samples, frequency_offset_hz, sample_rate)

    envelope = np.abs(samples)
    envelope -= np.mean(envelope)

    audio_bw = max(bandwidth_hz, 1_000.0)
    filtered = low_pass_filter(envelope, audio_bw / 2, sample_rate)

    dec_factor = int(sample_rate / audio_rate)
    if dec_factor > 1:
        audio = decimate(filtered, dec_factor)
    else:
        audio = filtered

    return _normalize_audio(audio)


def demod_ssb(
    samples: np.ndarray,
    sample_rate: float = 2.048e6,
    audio_rate: float = 48_000,
    mode: Literal["usb", "lsb"] = "usb",
) -> np.ndarray:
    """
    Demodulador SSB (USB/LSB).
    Ideal para radioaficionados en HF.
    """
    bw = 3_000  # 3 kHz ancho de banda de voz

    if mode == "lsb":
        # Invertir espectro para LSB
        samples = samples * np.exp(-1j * 2 * np.pi * bw * np.arange(len(samples)) / sample_rate)

    # Filtro paso bajo
    filtered = low_pass_filter(samples, bw, sample_rate)

    # Tomar parte real
    audio = filtered.real

    dec_factor = int(sample_rate / audio_rate)
    if dec_factor > 1:
        audio = decimate(audio, dec_factor)

    # Normalizar
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * NORMALIZE_LEVEL

    return audio.astype(np.float32)


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
) -> np.ndarray:
    """Demodula según el modo especificado. Retorna audio float32."""
    offset_kw = {"frequency_offset_hz": frequency_offset_hz}
    deemph_kw = {"fm_deemphasis_us": fm_deemphasis_us}

    if mode == "wbfm":
        bw = passband_width_hz if passband_width_hz is not None else 200_000
        return demod_wbfm(
            samples,
            sample_rate,
            audio_rate,
            bandwidth_hz=bw,
            **deemph_kw,
            **offset_kw,
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
        )
    if mode == "am":
        bw = passband_width_hz if passband_width_hz is not None else 5_000
        return demod_am(
            samples,
            sample_rate,
            audio_rate,
            bandwidth_hz=bw,
            **offset_kw,
        )
    if mode == "usb":
        return demod_ssb(samples, sample_rate, audio_rate, "usb")
    if mode == "lsb":
        return demod_ssb(samples, sample_rate, audio_rate, "lsb")
    raise ValueError(f"Modo desconocido: {mode}. Opciones: wbfm, nbfm, am, usb, lsb")


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
