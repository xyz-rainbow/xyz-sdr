"""
xyz-sdr | core/dsp.py
Procesado digital de señal: FFT, demodulación FM/AM/SSB, filtros.
"""

from __future__ import annotations

import numpy as np
from scipy import signal as scipy_signal
from typing import Literal

DemodMode = Literal["wbfm", "nbfm", "am", "usb", "lsb"]


# ─── FFT / Espectro ─────────────────────────────────────────────────────────

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
) -> tuple[np.ndarray, np.ndarray]:
    """PSD promediada sobre `num_avg` ventanas para reducir ruido."""
    step   = fft_size
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
        audio = audio / peak * 0.8

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
        audio = np.clip(audio / peak, -1, 1) * 0.8

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
        audio = audio / peak * 0.8

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
        audio = audio / peak * 0.8

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
