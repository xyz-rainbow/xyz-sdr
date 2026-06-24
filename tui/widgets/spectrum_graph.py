"""
xyz-sdr | tui/widgets/spectrum_graph.py
Grafico de espectro FFT en ASCII art, alineado al viewport de frecuencias.
"""

from __future__ import annotations

import time

import numpy as np
from rich.text import Text
from textual.widget import Widget
from textual import events
from textual.reactive import reactive

from core.band_buffer import BandFrame, slice_band_to_viewport
from core.passband import freq_to_col
from tui.widgets.display_palette import cell_background, normalize_per_column, plot_content_width
from tui.widgets.passband_messages import PassbandDragMixin


class SpectrumGraph(PassbandDragMixin, Widget):
    """Grafico de espectro FFT con relleno termico alineado al waterfall."""

    DEFAULT_CSS = """
    SpectrumGraph {
        height: 10;
        background: #020f0a;
        border: solid #10b981;
    }
    """

    passband_center_hz: reactive[float] = reactive(100_600_000.0)
    passband_width_hz: reactive[float] = reactive(200_000.0)
    passband_preview_width_hz: reactive[float | None] = reactive(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._band_frame: BandFrame | None = None
        self._viewport_cols: np.ndarray | None = None
        self._viewport_center_hz: float = 100_600_000.0
        self._visible_span_hz: float = 2_048_000.0
        self._frequency_columns: int = 0
        self._column_floors: np.ndarray | None = None
        self._column_ceilings: np.ndarray | None = None
        self._last_refresh_at: float = 0.0
        self._refresh_min_interval: float = 0.05
        self._paint_cache: Text | None = None
        self._paint_cache_key: tuple | None = None

    def set_frequency_columns(self, width: int) -> None:
        """Fija el ancho de columnas espectrales (debe coincidir con el espectro)."""
        width = max(int(width), 1)
        if width == self._frequency_columns:
            return
        self._frequency_columns = width
        self._invalidate_cache()
        self._reslice_viewport(force=True)

    def set_column_levels(self, floors: np.ndarray, ceilings: np.ndarray) -> None:
        floors = np.asarray(floors, dtype=np.float64).reshape(-1)
        ceilings = np.asarray(ceilings, dtype=np.float64).reshape(-1)
        if (
            self._column_floors is not None
            and np.array_equal(self._column_floors, floors)
            and self._column_ceilings is not None
            and np.array_equal(self._column_ceilings, ceilings)
        ):
            return
        self._column_floors = floors
        self._column_ceilings = ceilings
        self._invalidate_cache()

    def set_level_range(self, level_min: float, level_max: float) -> None:
        """Compatibilidad modo global: mismo suelo/techo en todas las columnas."""
        width = self._column_width()
        self.set_column_levels(
            np.full(width, float(level_min)),
            np.full(width, float(level_max)),
        )

    def _invalidate_cache(self) -> None:
        self._paint_cache = None
        self._paint_cache_key = None

    def _default_levels(self, width: int) -> tuple[np.ndarray, np.ndarray]:
        return (
            np.full(width, -80.0, dtype=np.float64),
            np.full(width, -20.0, dtype=np.float64),
        )

    def _levels_for_width(self, width: int) -> tuple[np.ndarray, np.ndarray]:
        if self._column_floors is None or self._column_ceilings is None:
            return self._default_levels(width)
        floors = np.asarray(self._column_floors, dtype=np.float64).reshape(-1)
        ceilings = np.asarray(self._column_ceilings, dtype=np.float64).reshape(-1)
        if len(floors) < width:
            floors = np.pad(floors, (0, width - len(floors)), constant_values=-80.0)
        if len(ceilings) < width:
            ceilings = np.pad(ceilings, (0, width - len(ceilings)), constant_values=-20.0)
        return floors[:width], ceilings[:width]

    def _column_width(self) -> int:
        if self._frequency_columns > 0:
            return self._frequency_columns
        return plot_content_width(self)

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        event.stop()
        from tui.widgets.frequency_timeline import FrequencyTimeline

        if event.ctrl:
            self.post_message(FrequencyTimeline.ZoomRequest(direction=-1))
        else:
            self.post_message(FrequencyTimeline.ScrollRequest(direction=1))

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        event.stop()
        from tui.widgets.frequency_timeline import FrequencyTimeline

        if event.ctrl:
            self.post_message(FrequencyTimeline.ZoomRequest(direction=1))
        else:
            self.post_message(FrequencyTimeline.ScrollRequest(direction=-1))

    def _effective_passband_width(self) -> float | None:
        preview = self.passband_preview_width_hz
        if preview is not None and preview > 0:
            return preview
        if self.passband_width_hz > 0:
            return self.passband_width_hz
        return None

    def _passband_cols(self, width: int) -> tuple[int, int] | None:
        band_w = self._effective_passband_width()
        if band_w is None or band_w <= 0:
            return None
        left_hz = self.passband_center_hz - band_w / 2
        right_hz = self.passband_center_hz + band_w / 2
        col_l = freq_to_col(
            left_hz,
            widget_width=width,
            viewport_center_hz=self._viewport_center_hz,
            visible_span_hz=self._visible_span_hz,
        )
        col_r = freq_to_col(
            right_hz,
            widget_width=width,
            viewport_center_hz=self._viewport_center_hz,
            visible_span_hz=self._visible_span_hz,
        )
        return min(col_l, col_r), max(col_l, col_r)

    def set_band_frame(self, frame: BandFrame) -> None:
        self._band_frame = frame
        self._reslice_viewport()

    def set_viewport_cols(self, cols: np.ndarray) -> None:
        """Establece columnas ya recortadas al viewport (evita re-slice)."""
        width = self._column_width()
        viewport = np.asarray(cols, dtype=np.float64).reshape(-1)
        if len(viewport) != width:
            viewport = np.pad(
                viewport,
                (0, max(0, width - len(viewport))),
                constant_values=np.nan,
            )[:width]
        self._viewport_cols = viewport
        now = time.perf_counter()
        if now - self._last_refresh_at < self._refresh_min_interval:
            return
        self._last_refresh_at = now
        self._invalidate_cache()
        self.refresh()

    def clear(self) -> None:
        self._band_frame = None
        self._viewport_cols = None
        self._invalidate_cache()
        self.refresh()

    def set_viewport(self, center_hz: float, span_hz: float) -> None:
        self._viewport_center_hz = center_hz
        self._visible_span_hz = span_hz
        self._reslice_viewport(force=True)

    def _reslice_viewport(self, *, force: bool = False) -> None:
        width = self._column_width()
        if self._band_frame is None:
            self._viewport_cols = None
            self._invalidate_cache()
            self.refresh()
            return

        self._viewport_cols = slice_band_to_viewport(
            self._band_frame.band_cols,
            self._band_frame.center_hz,
            self._band_frame.sample_rate,
            self._viewport_center_hz,
            self._visible_span_hz,
            width,
        )

        now = time.perf_counter()
        if not force and now - self._last_refresh_at < self._refresh_min_interval:
            return

        self._last_refresh_at = now
        self._invalidate_cache()
        self.refresh()

    def render(self) -> Text:
        width = self._column_width()
        height = max(int(self.size.height), 2)
        if width < 5 or height < 2:
            return Text("...")

        passband_cols = self._passband_cols(width)

        if self._viewport_cols is None:
            lines = [""] * height
            msg = "Esperando senal... [S] para iniciar RX"
            mid = height // 2
            pad = max(0, (width - len(msg)) // 2)
            lines[mid] = " " * pad + msg
            result = Text()
            for i, line in enumerate(lines):
                result.append(line.ljust(width), "#34d399")
                if i < height - 1:
                    result.append("\n")
            return result

        col_values = self._viewport_cols
        if len(col_values) != width:
            col_values = np.pad(
                col_values,
                (0, max(0, width - len(col_values))),
                constant_values=np.nan,
            )[:width]

        floors, ceilings = self._levels_for_width(width)
        cache_key = (
            col_values.tobytes(),
            floors.tobytes(),
            ceilings.tobytes(),
            width,
            height,
            self.passband_center_hz,
            self.passband_width_hz,
            self.passband_preview_width_hz,
        )
        if self._paint_cache is not None and cache_key == self._paint_cache_key:
            return self._paint_cache

        norms = normalize_per_column(col_values, floors, ceilings)
        peak_rows = np.full(width, -1, dtype=np.int32)
        valid = ~np.isnan(norms)
        if valid.any():
            peak_rows[valid] = (norms[valid] * max(height - 1, 1)).astype(np.int32)

        result = Text()
        for row in range(height - 1, -1, -1):
            line = Text()
            for col in range(width):
                in_band = passband_cols and passband_cols[0] <= col <= passband_cols[1]
                if np.isnan(norms[col]):
                    if row == 0:
                        ch = "░"
                        color = "#14532d" if in_band else "#1e1b4b"
                        line.append(ch, color)
                    else:
                        line.append(" ")
                    continue

                norm = float(norms[col])
                peak = int(peak_rows[col])
                if row <= peak:
                    bg = cell_background(norm, in_band=in_band)
                    line.append("█" if row == peak and in_band else " ", f"on {bg}")
                elif row == peak + 1 and in_band:
                    line.append("·", "bold #ffffff")
                elif in_band and row == 0:
                    line.append("░", "#14532d")
                else:
                    line.append(" ")
            result.append(line)
            if row > 0:
                result.append("\n")

        self._paint_cache = result
        self._paint_cache_key = cache_key
        return result

    def watch_passband_center_hz(self, value: float) -> None:
        self._invalidate_cache()
        self.refresh()

    def watch_passband_width_hz(self, value: float) -> None:
        self._invalidate_cache()
        self.refresh()

    def watch_passband_preview_width_hz(self, value: float | None) -> None:
        self._invalidate_cache()
        self.refresh()
