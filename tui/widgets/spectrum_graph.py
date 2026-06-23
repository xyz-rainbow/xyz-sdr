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
from tui.widgets.passband_messages import PassbandDragMixin


class SpectrumGraph(PassbandDragMixin, Widget):
    """Grafico de espectro FFT con barras ASCII alineadas al viewport."""

    DEFAULT_CSS = """
    SpectrumGraph {
        height: 10;
        background: #020f0a;
        border: solid #10b981;
    }
    """

    BARS = " \u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"

    passband_center_hz: reactive[float] = reactive(100_600_000.0)
    passband_width_hz: reactive[float] = reactive(200_000.0)
    passband_preview_width_hz: reactive[float | None] = reactive(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._band_frame: BandFrame | None = None
        self._viewport_cols: np.ndarray | None = None
        self._viewport_center_hz: float = 100_600_000.0
        self._visible_span_hz: float = 2_048_000.0
        self._last_refresh_at: float = 0.0
        self._refresh_min_interval: float = 0.05

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

    def clear(self) -> None:
        self._band_frame = None
        self._viewport_cols = None
        self.refresh()

    def set_viewport(self, center_hz: float, span_hz: float) -> None:
        self._viewport_center_hz = center_hz
        self._visible_span_hz = span_hz
        self._reslice_viewport(force=True)

    def _reslice_viewport(self, *, force: bool = False) -> None:
        width = max(self.size.width, 1)
        if self._band_frame is None:
            self._viewport_cols = None
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
        self.refresh()

    def render(self) -> Text:
        width = self.size.width
        height = self.size.height
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

        valid_mask = ~np.isnan(col_values)
        valid = col_values[valid_mask]
        if len(valid) == 0:
            result = Text()
            for row in range(height):
                if row == 0:
                    result.append("░" * width, "#1e1b4b")
                else:
                    result.append(" " * width)
                if row < height - 1:
                    result.append("\n")
            return result

        psd_min = float(np.percentile(valid, 5))
        psd_max = float(np.percentile(valid, 99))
        rng = psd_max - psd_min if psd_max != psd_min else 1.0

        norms = np.full(width, np.nan, dtype=np.float64)
        for col in range(width):
            val = col_values[col]
            if not np.isnan(val):
                norms[col] = max(0.0, min(1.0, (val - psd_min) / rng))

        peak_rows = np.full(width, -1, dtype=np.int32)
        for col in range(width):
            if not np.isnan(norms[col]):
                peak_rows[col] = int(norms[col] * max(height - 1, 1))

        result = Text()
        for row in range(height - 1, -1, -1):
            threshold = row / max(height - 1, 1)
            line = Text()
            for col in range(width):
                in_band = passband_cols and passband_cols[0] <= col <= passband_cols[1]
                val = col_values[col]
                if np.isnan(val):
                    if row == 0:
                        ch = "░"
                        color = "#14532d" if in_band else "#1e1b4b"
                        line.append(ch, color)
                    else:
                        line.append(" ")
                    continue

                norm = norms[col]
                is_peak = peak_rows[col] == row
                if is_peak and in_band:
                    line.append("·", self._peak_color(norm))
                elif norm >= threshold:
                    excess = (norm - threshold) * max(height - 1, 1)
                    bar_idx = min(int(excess * 2), len(self.BARS) - 1)
                    ch = self.BARS[bar_idx]
                    color = self._intensity_color(norm) if in_band else "#1e3a2f"
                    line.append(ch, color)
                elif in_band and row == 0:
                    line.append("░", "#14532d")
                else:
                    line.append(" ")
            result.append(line)
            if row > 0:
                result.append("\n")

        return result

    @staticmethod
    def _peak_color(norm: float) -> str:
        """Color del contorno de pico en la curva espectral."""
        if norm > 0.85:
            return "bold #ff6666"
        if norm > 0.7:
            return "bold #ffaa66"
        if norm > 0.5:
            return "bold #ffff66"
        return "bold #66ff99"

    @staticmethod
    def _intensity_color(norm: float) -> str:
        if norm > 0.85:
            return "bold #ff4444"
        if norm > 0.7:
            return "#ff8844"
        if norm > 0.5:
            return "#ffcc00"
        if norm > 0.3:
            return "#44ff44"
        return "#34d399"

    def watch_passband_center_hz(self, value: float) -> None:
        self.refresh()

    def watch_passband_width_hz(self, value: float) -> None:
        self.refresh()

    def watch_passband_preview_width_hz(self, value: float | None) -> None:
        self.refresh()
