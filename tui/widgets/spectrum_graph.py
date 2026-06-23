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

from core.band_buffer import BandFrame, slice_band_to_viewport


class SpectrumGraph(Widget):
    """Grafico de espectro FFT con barras ASCII alineadas al viewport."""

    DEFAULT_CSS = """
    SpectrumGraph {
        height: 10;
        background: #020f0a;
        border: solid #10b981;
    }
    """

    BARS = " \u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"  # ▁▂▃▄▅▆▇█

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._band_frame: BandFrame | None = None
        self._viewport_cols: np.ndarray | None = None
        self._viewport_center_hz: float = 100_600_000.0
        self._visible_span_hz: float = 2_048_000.0
        self._last_refresh_at: float = 0.0
        self._refresh_min_interval: float = 0.05

    # ── Eventos de Raton ─────────────────────────────────────────────────────

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        """Hacer scroll o zoom desde el gráfico de espectro."""
        event.stop()
        from tui.widgets.frequency_timeline import FrequencyTimeline
        if event.ctrl:
            self.post_message(FrequencyTimeline.ZoomRequest(direction=-1))
        else:
            self.post_message(FrequencyTimeline.ScrollRequest(direction=1))

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        """Hacer scroll o zoom desde el gráfico de espectro."""
        event.stop()
        from tui.widgets.frequency_timeline import FrequencyTimeline
        if event.ctrl:
            self.post_message(FrequencyTimeline.ZoomRequest(direction=1))
        else:
            self.post_message(FrequencyTimeline.ScrollRequest(direction=-1))

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Clic: desenfocar inputs sin cambiar la frecuencia."""
        event.stop()
        self.app.set_focus(None)

    # ── API publica ──────────────────────────────────────────────────────────

    def set_band_frame(self, frame: BandFrame) -> None:
        """Recibe un frame de banda pre-proyectado (desde el display timer)."""
        self._band_frame = frame
        self._reslice_viewport()

    def clear(self) -> None:
        """Limpia datos (p. ej. al cambiar bandwidth)."""
        self._band_frame = None
        self._viewport_cols = None
        self.refresh()

    def set_viewport(self, center_hz: float, span_hz: float) -> None:
        """Actualiza viewport y re-slicea desde la caché (sin esperar RX)."""
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

    # ── Rendering ────────────────────────────────────────────────────────────

    def render(self) -> Text:
        width = self.size.width
        height = self.size.height
        if width < 5 or height < 2:
            return Text("...")

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

        result = Text()
        for row in range(height - 1, -1, -1):
            threshold = row / max(height - 1, 1)
            line = Text()
            for col in range(width):
                val = col_values[col]
                if np.isnan(val):
                    if row == 0:
                        line.append("░", "#1e1b4b")
                    else:
                        line.append(" ")
                else:
                    norm = max(0.0, min(1.0, (val - psd_min) / rng))
                    if norm >= threshold:
                        excess = (norm - threshold) * max(height - 1, 1)
                        bar_idx = min(int(excess * 2), len(self.BARS) - 1)
                        ch = self.BARS[bar_idx]
                        color = self._intensity_color(norm)
                        line.append(ch, color)
                    else:
                        line.append(" ")
            result.append(line)
            if row > 0:
                result.append("\n")

        return result

    @staticmethod
    def _intensity_color(norm: float) -> str:
        """Devuelve color Rich basado en intensidad normalizada [0,1]."""
        if norm > 0.85:
            return "bold #ff4444"
        elif norm > 0.7:
            return "#ff8844"
        elif norm > 0.5:
            return "#ffcc00"
        elif norm > 0.3:
            return "#44ff44"
        else:
            return "#34d399"
