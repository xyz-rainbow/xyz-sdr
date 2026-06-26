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
# Resolución fija del historial waterfall (independiente del zoom adaptativo).
WATERFALL_HISTORY_BAND_COLS = 512


def compact_band_cols(
    band_cols: np.ndarray,
    target: int = WATERFALL_HISTORY_BAND_COLS,
) -> np.ndarray:
    """Max-pool a rejilla fija para historial waterfall (menos RAM, geometría estable)."""
    src = np.asarray(band_cols, dtype=np.float32).reshape(-1)
    target = max(1, int(target))
    if len(src) <= target:
        return src.copy()

    edges = np.linspace(0, len(src), target + 1, dtype=np.int32)
    # np.maximum.reduceat es la versión vectorizada del max-pool por segmento.
    # Para segmentos vacíos (edges[i] == edges[i+1]) reduceat devuelve src[edges[i]],
    # igual que el fallback del bucle Python original.
    return np.maximum.reduceat(src, edges[:-1]).astype(np.float32, copy=False)


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

    cols = np.arange(width, dtype=np.float64)
    f_start = viewport_left + cols * hz_per_col
    f_end = f_start + hz_per_col

    overlap_start = np.maximum(f_start, capture_left)
    overlap_end = np.minimum(f_end, capture_left + sample_rate)
    valid = overlap_start < overlap_end

    bin_start = np.floor((overlap_start - capture_left) / band_hz_per_col).astype(np.int32)
    bin_end = np.ceil((overlap_end - capture_left) / band_hz_per_col).astype(np.int32)
    bin_start = np.clip(bin_start, 0, band_n - 1)
    bin_end = np.clip(bin_end, bin_start + 1, band_n)

    for col in range(width):
        if valid[col]:
            out[col] = float(np.max(band_cols[bin_start[col] : bin_end[col]]))

    return out


def slice_band_history_to_viewport(
    rows: list[tuple[float, float, np.ndarray]],
    viewport_center_hz: float,
    visible_span_hz: float,
    terminal_width: int,
) -> np.ndarray | None:
    """
    Slice en lote filas del waterfall (mismo mapeo de bins por columna).

    Returns:
        float array (n_rows, terminal_width) o None si no hay filas.
    """
    if not rows:
        return None

    width = max(terminal_width, 1)
    center_hz = rows[0][0]
    sample_rate = rows[0][1]
    band_n = len(rows[0][2])
    if band_n == 0 or sample_rate <= 0 or visible_span_hz <= 0:
        return None

    same_geometry = all(
        row[0] == center_hz and row[1] == sample_rate and len(row[2]) == band_n
        for row in rows
    )

    capture_left = center_hz - sample_rate / 2
    viewport_left = viewport_center_hz - visible_span_hz / 2
    band_hz_per_col = sample_rate / band_n
    hz_per_col = visible_span_hz / width

    cols = np.arange(width, dtype=np.float64)
    f_start = viewport_left + cols * hz_per_col
    f_end = f_start + hz_per_col
    overlap_start = np.maximum(f_start, capture_left)
    overlap_end = np.minimum(f_end, capture_left + sample_rate)
    valid = overlap_start < overlap_end

    bin_start = np.floor((overlap_start - capture_left) / band_hz_per_col).astype(np.int32)
    bin_end = np.ceil((overlap_end - capture_left) / band_hz_per_col).astype(np.int32)
    bin_start = np.clip(bin_start, 0, band_n - 1)
    bin_end = np.clip(bin_end, bin_start + 1, band_n)

    out = np.full((len(rows), width), np.nan, dtype=np.float64)

    if same_geometry:
        stack = np.stack([row[2] for row in rows])
        for col in range(width):
            if valid[col]:
                out[:, col] = np.max(stack[:, bin_start[col] : bin_end[col]], axis=1)
        return out

    for row_idx, (row_center, row_rate, band_cols) in enumerate(rows):
        out[row_idx] = slice_band_to_viewport(
            band_cols,
            row_center,
            row_rate,
            viewport_center_hz,
            visible_span_hz,
            width,
        )

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

    def peek_latest(self) -> tuple[BandFrame | None, float, int]:
        """Último frame publicado (sin consumir), para resync de secuencia."""
        with self._lock:
            if self._frame is None:
                return None, self._snr, self._sequence
            return self._frame, self._snr, self._sequence

    def clear(self) -> None:
        with self._lock:
            self._frame = None
            self._snr = 0.0
            self._sequence = 0
