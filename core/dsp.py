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


# ─── Demoduladores ──────────────────────────────────────────────────────────

def demod_wbfm(
    samples: np.ndarray,
    sample_rate: float = 2.048e6,
    audio_rate: float = 48_000,
) -> np.ndarray:
    """
    Demodulador FM de banda ancha (WBFM).
    Ideal para radio FM comercial (88-108 MHz).
    """
    # Filtro paso bajo para limitar ancho de banda
    bw = 200_000  # 200 kHz
    filtered = low_pass_filter(samples, bw / 2, sample_rate)

    # Demodulación FM: ángulo entre muestras consecutivas
    demod = np.angle(filtered[1:] * np.conj(filtered[:-1]))

    # Decimar a frecuencia de audio
    dec_factor = int(sample_rate / audio_rate)
    if dec_factor > 1:
        audio = decimate(demod, dec_factor)
    else:
        audio = demod

    # Normalizar
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * NORMALIZE_LEVEL

    return audio.astype(np.float32)


def demod_nbfm(
    samples: np.ndarray,
    sample_rate: float = 2.048e6,
    audio_rate: float = 48_000,
    deviation: float = 5_000,
) -> np.ndarray:
    """
    Demodulador FM de banda estrecha (NBFM).
    Ideal para comunicaciones de radioaficionados, PMR, etc.
    """
    # Filtro paso bajo más estrecho
    bw = deviation * 2.5
    filtered = low_pass_filter(samples, bw, sample_rate)

    demod = np.angle(filtered[1:] * np.conj(filtered[:-1]))
    demod = demod / (2 * np.pi * deviation / sample_rate)  # Normalizar desviación

    dec_factor = int(sample_rate / audio_rate)
    if dec_factor > 1:
        audio = decimate(demod.real, dec_factor)
    else:
        audio = demod.real

    # Normalizar
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = np.clip(audio / peak, -1, 1) * NORMALIZE_LEVEL

    return audio.astype(np.float32)


def demod_am(
    samples: np.ndarray,
    sample_rate: float = 2.048e6,
    audio_rate: float = 48_000,
) -> np.ndarray:
    """
    Demodulador AM (detección de envolvente).
    """
    # Envolvente = magnitud de la señal compleja
    envelope = np.abs(samples)

    # Eliminar componente DC
    envelope -= np.mean(envelope)

    # Filtro paso bajo de audio
    audio_bw = 5_000  # 5 kHz
    filtered = low_pass_filter(envelope, audio_bw, sample_rate)

    dec_factor = int(sample_rate / audio_rate)
    if dec_factor > 1:
        audio = decimate(filtered, dec_factor)
    else:
        audio = filtered

    # Normalizar
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * NORMALIZE_LEVEL

    return audio.astype(np.float32)


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
) -> np.ndarray:
    """Demodula según el modo especificado. Retorna audio float32."""
    DEMOD_MAP = {
        "wbfm": lambda s: demod_wbfm(s, sample_rate, audio_rate),
        "nbfm": lambda s: demod_nbfm(s, sample_rate, audio_rate),
        "am":   lambda s: demod_am(s, sample_rate, audio_rate),
        "usb":  lambda s: demod_ssb(s, sample_rate, audio_rate, "usb"),
        "lsb":  lambda s: demod_ssb(s, sample_rate, audio_rate, "lsb"),
    }
    if mode not in DEMOD_MAP:
        raise ValueError(f"Modo desconocido: {mode}. Opciones: {list(DEMOD_MAP)}")
    return DEMOD_MAP[mode](samples)


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
