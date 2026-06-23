"""
xyz-sdr | tui/widgets/spectrum_graph.py
Grafico de espectro FFT en ASCII art, alineado al viewport de frecuencias.
"""

from __future__ import annotations

import numpy as np
from rich.text import Text
from textual.widget import Widget
from textual import events


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
        self._psd: np.ndarray | None = None
        self._freqs_abs_hz: np.ndarray | None = None
        self._viewport_center_hz: float = 100_600_000.0
        self._visible_span_hz: float = 2_048_000.0

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
        """Sintonizar directamente al hacer clic en el gráfico."""
        event.stop()
        width = self.size.width
        if width <= 0:
            return
        left_hz = self._viewport_center_hz - self._visible_span_hz / 2
        clicked_freq = left_hz + (event.x / width) * self._visible_span_hz
        from tui.widgets.frequency_timeline import FrequencyTimeline
        self.post_message(FrequencyTimeline.TuneRequest(clicked_freq))

    # ── API publica ──────────────────────────────────────────────────────────

    def update_data(
        self,
        freqs_mhz: np.ndarray,
        psd_db: np.ndarray,
        capture_center_hz: float,
    ) -> None:
        """Recibe datos del worker RX. freqs_mhz son relativas al centro."""
        self._psd = psd_db.copy()
        # Convertir frecuencias relativas MHz a absolutas Hz
        self._freqs_abs_hz = freqs_mhz * 1e6 + capture_center_hz
        self.refresh()

    def set_viewport(self, center_hz: float, span_hz: float) -> None:
        """Actualiza parametros del viewport para alineacion."""
        self._viewport_center_hz = center_hz
        self._visible_span_hz = span_hz
        self.refresh()

    # ── Rendering ────────────────────────────────────────────────────────────

    def render(self) -> Text:
        width = self.size.width
        height = self.size.height
        if width < 5 or height < 2:
            return Text("...")

        if self._psd is None or self._freqs_abs_hz is None:
            # Pantalla de espera
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

        # Mapear columnas de pantalla a valores PSD con agregación de picos (máxima resolución)
        left_hz = self._viewport_center_hz - self._visible_span_hz / 2
        hz_per_col = self._visible_span_hz / max(width, 1)
        col_values = np.full(width, np.nan)

        for col in range(width):
            f_start = left_hz + col * hz_per_col
            f_end = left_hz + (col + 1) * hz_per_col

            if self._freqs_abs_hz is not None and len(self._freqs_abs_hz) > 0:
                # Encontrar rango de bins FFT correspondientes a esta columna
                idx_start = np.searchsorted(self._freqs_abs_hz, f_start)
                idx_end = np.searchsorted(self._freqs_abs_hz, f_end)

                if idx_start < idx_end:
                    # Múltiples bins en esta columna -> tomamos el máximo absoluto
                    col_values[col] = np.max(self._psd[idx_start:idx_end])
                else:
                    # Zoom muy alto -> interpolamos con el vecino más cercano
                    idx = min(idx_start, len(self._psd) - 1)
                    col_values[col] = self._psd[idx]

        # Normalizar valores validos
        valid_mask = ~np.isnan(col_values)
        valid = col_values[valid_mask]
        if len(valid) == 0:
            # Rellenar con patrón si no hay datos visibles
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

        # Construir grafico de barras (de arriba a abajo)
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
                        # Elegir caracter de barra segun exceso
                        excess = (norm - threshold) * max(height - 1, 1)
                        bar_idx = min(
                            int(excess * 2), len(self.BARS) - 1
                        )
                        ch = self.BARS[bar_idx]
                        # Color segun intensidad
                        color = self._intensity_color(norm)
                        line.append(ch, color)
                    else:
                        line.append(" ")
            result.append(line)
            if row > 0:
                result.append("\n")

        return result

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _intensity_color(norm: float) -> str:
        """Devuelve color Rich basado en intensidad normalizada [0,1]."""
        if norm > 0.85:
            return "bold #ff4444"   # rojo fuerte
        elif norm > 0.7:
            return "#ff8844"       # naranja
        elif norm > 0.5:
            return "#ffcc00"       # amarillo
        elif norm > 0.3:
            return "#44ff44"       # verde brillante
        else:
            return "#34d399"       # verde tenue
