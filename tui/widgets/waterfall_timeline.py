"""
xyz-sdr | tui/widgets/waterfall_timeline.py
Espectrograma en cascada (waterfall) con alineacion dinamica por frecuencia.
Cada fila del historial almacena la frecuencia central de captura para permitir
re-alineamiento correcto al hacer scroll o zoom.
"""

from __future__ import annotations

import numpy as np
from rich.text import Text
from textual.widget import Widget
from textual.reactive import reactive
from textual import events


# Gradiente de colores de alta resolución (32 pasos):
# Ruido muy débil se funde a negro absoluto (#000000) simulando opacidad 0%.
# Señales medias pasan por azules, cian, verde y amarillo.
# Señales fuertes brillan intensamente en naranja, rojo, magenta y blanco.
WATERFALL_GRADIENT = [
    "#000000",  # 0: Negro absoluto (piso de ruido, simula opacidad 0%)
    "#01010b",  # 1
    "#020216",  # 2
    "#040422",  # 3
    "#060630",  # 4
    "#080840",  # 5: Azul muy oscuro
    "#0a0a52",  # 6
    "#0d0d66",  # 7
    "#10107c",  # 8
    "#111193",  # 9: Azul medio
    "#0d36a8",  # 10
    "#0a5dbd",  # 11
    "#0683d1",  # 12: Azul brillante / Cian
    "#00aeff",  # 13
    "#00c2db",  # 14
    "#00d6b0",  # 15: Verde-cian
    "#00eb82",  # 16
    "#00ff4c",  # 17: Verde brillante
    "#5dfc30",  # 18
    "#a3f915",  # 19: Verde-amarillo
    "#e2f600",  # 20: Amarillo-verde
    "#ffff00",  # 21: Amarillo puro
    "#ffd000",  # 22
    "#ffa000",  # 23: Naranja claro
    "#ff6a00",  # 24
    "#ff3700",  # 25: Naranja-rojo
    "#ff0000",  # 26: Rojo puro (intensidad alta)
    "#e6004c",  # 27
    "#cc007c",  # 28: Magenta profundo
    "#d900b3",  # 29
    "#ff00ff",  # 30: Magenta eléctrico
    "#ffffff",  # 31: Blanco brillante (saturación máxima de señal)
]

# Color para zonas sin datos de captura
NO_DATA_COLOR = "#08080f"


class _WaterfallRow:
    """Una fila del historial de waterfall."""
    __slots__ = ("center_hz", "sample_rate", "psd")

    def __init__(self, center_hz: float, sample_rate: float, psd: np.ndarray):
        self.center_hz = center_hz
        self.sample_rate = sample_rate
        self.psd = psd


class WaterfallTimeline(Widget):
    """Espectrograma en cascada alineado por frecuencia al viewport."""

    DEFAULT_CSS = """
    WaterfallTimeline {
        height: 1fr;
        background: #050511;
        border: solid #6366f1;
    }
    """

    viewport_center_hz: reactive[float] = reactive(100_600_000.0)
    visible_span_hz: reactive[float] = reactive(2_048_000.0)
    waterfall_speed: reactive[int] = reactive(10)

    def __init__(self, max_history: int = 200, **kwargs):
        super().__init__(**kwargs)
        self._history: list[_WaterfallRow] = []
        self._max_history = max_history
        self._viewport_center_hz: float = 100_600_000.0
        self._visible_span_hz: float = 2_048_000.0
        self._last_row_time: float = 0.0
        # Cache de normalizacion
        self._norm_min: float = -80.0
        self._norm_max: float = -20.0

    # ── Eventos de Raton ─────────────────────────────────────────────────────

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        """Hacer scroll o zoom desde la cascada."""
        event.stop()
        from tui.widgets.frequency_timeline import FrequencyTimeline
        if event.ctrl:
            self.post_message(FrequencyTimeline.ZoomRequest(direction=-1))
        else:
            self.post_message(FrequencyTimeline.ScrollRequest(direction=1))

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        """Hacer scroll o zoom desde la cascada."""
        event.stop()
        from tui.widgets.frequency_timeline import FrequencyTimeline
        if event.ctrl:
            self.post_message(FrequencyTimeline.ZoomRequest(direction=1))
        else:
            self.post_message(FrequencyTimeline.ScrollRequest(direction=-1))

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Sintonizar directamente al hacer clic en la cascada."""
        event.stop()
        width = self.size.width
        if width <= 0:
            return
        left_hz = self._viewport_center_hz - self._visible_span_hz / 2
        clicked_freq = left_hz + (event.x / width) * self._visible_span_hz
        from tui.widgets.frequency_timeline import FrequencyTimeline
        self.post_message(FrequencyTimeline.TuneRequest(clicked_freq))

    # ── API publica ──────────────────────────────────────────────────────────

    def add_row(
        self, center_hz: float, sample_rate: float, psd: np.ndarray
    ) -> None:
        """Agrega una nueva fila PSD al historial del waterfall, regulada por velocidad."""
        import time
        now = time.time()
        # Throttling: limitar adición de filas al intervalo correspondiente a la velocidad (FPS)
        interval = 1.0 / max(1, self.waterfall_speed)
        if now - self._last_row_time < interval:
            return  # Descartar frame para ralentizar velocidad

        self._last_row_time = now
        self._history.insert(0, _WaterfallRow(center_hz, sample_rate, psd.copy()))
        if len(self._history) > self._max_history:
            self._history.pop()
        self._update_normalization()
        self.refresh()

    def set_viewport(self, center_hz: float, span_hz: float) -> None:
        """Actualiza el viewport para re-alineamiento."""
        self._viewport_center_hz = center_hz
        self._visible_span_hz = span_hz
        self.refresh()

    # ── Rendering ────────────────────────────────────────────────────────────

    def render(self) -> Text:
        width = self.size.width
        height = self.size.height
        if width < 5 or height < 1:
            return Text("...")

        left_hz = self._viewport_center_hz - self._visible_span_hz / 2
        hz_per_col = self._visible_span_hz / max(width, 1)
        rows_to_show = min(len(self._history), height)
        rng = self._norm_max - self._norm_min
        if rng <= 0:
            rng = 1.0

        result = Text()
        for row_idx in range(height):
            if row_idx < rows_to_show:
                line = self._render_row(
                    self._history[row_idx],
                    width,
                    left_hz,
                    hz_per_col,
                    rng,
                )
            else:
                # Fila vacia (sin historial aun)
                line = Text("░" * width, f"#1e1b4b on {NO_DATA_COLOR}")

            result.append(line)
            if row_idx < height - 1:
                result.append("\n")

        return result

    def _render_row(
        self,
        row: _WaterfallRow,
        width: int,
        left_hz: float,
        hz_per_col: float,
        rng: float,
    ) -> Text:
        """Renderiza una fila del waterfall mapeando columnas a frecuencias con agregación de picos."""
        line = Text()
        row_left_hz = row.center_hz - row.sample_rate / 2
        row_right_hz = row.center_hz + row.sample_rate / 2
        psd_len = len(row.psd)
        hz_per_bin = row.sample_rate / max(psd_len, 1)

        for col in range(width):
            f_start = left_hz + col * hz_per_col
            f_end = left_hz + (col + 1) * hz_per_col

            # Encontrar solapamiento de la columna con el rango de captura
            overlap_start = max(f_start, row_left_hz)
            overlap_end = min(f_end, row_right_hz)

            if overlap_start < overlap_end:
                # Mapear rango de frecuencias a bins PSD
                bin_start = int((overlap_start - row_left_hz) / hz_per_bin)
                bin_end = int((overlap_end - row_left_hz) / hz_per_bin)
                bin_start = max(0, min(bin_start, psd_len - 1))
                bin_end = max(bin_start + 1, min(bin_end, psd_len))

                # Agregación: tomamos el valor máximo del rango de bins (máxima resolución de picos)
                val = float(np.max(row.psd[bin_start:bin_end]))
                norm = max(0.0, min(1.0, (val - self._norm_min) / rng))
                color_idx = min(
                    int(norm * (len(WATERFALL_GRADIENT) - 1)),
                    len(WATERFALL_GRADIENT) - 1,
                )
                line.append(" ", f"on {WATERFALL_GRADIENT[color_idx]}")
            else:
                # Fuera del rango de captura (rellenar con patrón diagonal)
                line.append("░", f"#1e1b4b on {NO_DATA_COLOR}")

        return line

    # ── Normalizacion ────────────────────────────────────────────────────────

    def _update_normalization(self) -> None:
        """Recalcula limites de normalizacion sobre las filas visibles."""
        height = max(self.size.height, 20)
        visible = self._history[:height]
        if not visible:
            return

        # Usar numpy para velocidad
        all_psd = np.concatenate([r.psd for r in visible])
        self._norm_min = float(np.percentile(all_psd, 5))
        self._norm_max = float(np.percentile(all_psd, 99))
