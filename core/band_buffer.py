"""
xyz-sdr | core/band_buffer.py
Caché de banda IQ: proyección PSD → rejilla fija y slice al viewport terminal.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import numpy as np

from core.dsp import map_psd_to_columns

DEFAULT_BAND_CACHE_COLS = 512


@dataclass(frozen=True)
class BandFrame:
    """Un frame espectral proyectado sobre el bandwidth IQ completo."""

    center_hz: float
    sample_rate: float
    timestamp: float
    band_cols: np.ndarray  # float32, longitud fija


def project_psd_to_band(
    psd: np.ndarray,
    center_hz: float,
    sample_rate: float,
    band_cols: int = DEFAULT_BAND_CACHE_COLS,
) -> np.ndarray:
    """Proyecta la PSD del BW completo a una rejilla interna fija (una vez por frame)."""
    band_cols = max(band_cols, 1)
    projected = map_psd_to_columns(
        psd,
        center_hz,
        sample_rate,
        center_hz,
        sample_rate,
        band_cols,
    )
    return projected.astype(np.float32, copy=False)


def slice_band_to_viewport(
    band_cols: np.ndarray,
    center_hz: float,
    sample_rate: float,
    viewport_center_hz: float,
    visible_span_hz: float,
    terminal_width: int,
) -> np.ndarray:
    """Recorta/re-muestrea la rejilla de banda al viewport visible en terminal."""
    width = max(terminal_width, 1)
    out = np.full(width, np.nan, dtype=np.float64)

    band_n = len(band_cols)
    if band_n == 0 or sample_rate <= 0 or visible_span_hz <= 0:
        return out

    capture_left = center_hz - sample_rate / 2
    viewport_left = viewport_center_hz - visible_span_hz / 2
    band_hz_per_col = sample_rate / band_n
    hz_per_col = visible_span_hz / width

    for col in range(width):
        f_start = viewport_left + col * hz_per_col
        f_end = f_start + hz_per_col

        overlap_start = max(f_start, capture_left)
        overlap_end = min(f_end, capture_left + sample_rate)
        if overlap_start >= overlap_end:
            continue

        bin_start = int((overlap_start - capture_left) / band_hz_per_col)
        bin_end = int((overlap_end - capture_left) / band_hz_per_col)
        bin_start = max(0, min(bin_start, band_n - 1))
        bin_end = max(bin_start + 1, min(bin_end, band_n))
        out[col] = float(np.max(band_cols[bin_start:bin_end]))

    return out


def make_band_frame(
    psd: np.ndarray,
    center_hz: float,
    sample_rate: float,
    band_cols: int = DEFAULT_BAND_CACHE_COLS,
) -> BandFrame:
    """Construye un BandFrame desde PSD cruda."""
    return BandFrame(
        center_hz=center_hz,
        sample_rate=sample_rate,
        timestamp=time.time(),
        band_cols=project_psd_to_band(psd, center_hz, sample_rate, band_cols),
    )


class BandFrameMailbox:
    """Cola coalesced: el worker publica; el main thread consume el frame más reciente."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: BandFrame | None = None
        self._snr: float = 0.0
        self._sequence: int = 0

    def publish(self, frame: BandFrame, snr: float) -> None:
        with self._lock:
            self._frame = frame
            self._snr = snr
            self._sequence += 1

    def consume_if_new(self, last_sequence: int) -> tuple[BandFrame | None, float, int]:
        with self._lock:
            if self._frame is None or self._sequence <= last_sequence:
                return None, self._snr, last_sequence
            return self._frame, self._snr, self._sequence

    def clear(self) -> None:
        with self._lock:
            self._frame = None
            self._snr = 0.0
            self._sequence = 0
