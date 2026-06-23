"""
xyz-sdr | tui/widgets/waterfall_timeline.py
Espectrograma en cascada (waterfall) con alineacion dinamica por frecuencia.
Cada fila almacena band_cols pre-proyectados sobre el BW de captura.
"""

from __future__ import annotations

import time

import numpy as np
from rich.text import Text
from textual.widget import Widget
from textual.reactive import reactive
from textual import events

from core.band_buffer import BandFrame, slice_band_to_viewport


WATERFALL_GRADIENT = [
    "#000000",
    "#01010b",
    "#020216",
    "#040422",
    "#060630",
    "#080840",
    "#0a0a52",
    "#0d0d66",
    "#10107c",
    "#111193",
    "#0d36a8",
    "#0a5dbd",
    "#0683d1",
    "#00aeff",
    "#00c2db",
    "#00d6b0",
    "#00eb82",
    "#00ff4c",
    "#5dfc30",
    "#a3f915",
    "#e2f600",
    "#ffff00",
    "#ffd000",
    "#ffa000",
    "#ff6a00",
    "#ff3700",
    "#ff0000",
    "#e6004c",
    "#cc007c",
    "#d900b3",
    "#ff00ff",
    "#ffffff",
]

NO_DATA_COLOR = "#08080f"


class _WaterfallRow:
    """Una fila del historial de waterfall."""
    __slots__ = ("center_hz", "sample_rate", "band_cols")

    def __init__(self, center_hz: float, sample_rate: float, band_cols: np.ndarray):
        self.center_hz = center_hz
        self.sample_rate = sample_rate
        self.band_cols = band_cols


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
        self._norm_min: float = -80.0
        self._norm_max: float = -20.0

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

    def on_mouse_down(self, event: events.MouseDown) -> None:
        event.stop()
        self.app.set_focus(None)

    def add_band_row(self, frame: BandFrame) -> None:
        """Agrega fila desde BandFrame pre-proyectado (throttle por waterfall_speed)."""
        now = time.time()
        interval = 1.0 / max(1, self.waterfall_speed)
        if now - self._last_row_time < interval:
            return

        self._last_row_time = now
        self._history.insert(
            0,
            _WaterfallRow(frame.center_hz, frame.sample_rate, frame.band_cols),
        )
        if len(self._history) > self._max_history:
            self._history.pop()
        self._update_normalization()
        self.refresh()

    def clear_history(self) -> None:
        """Invalida historial (p. ej. al cambiar bandwidth)."""
        self._history.clear()
        self._last_row_time = 0.0
        self.refresh()

    def set_viewport(self, center_hz: float, span_hz: float) -> None:
        """Actualiza viewport; re-slicea desde band_cols en render."""
        self._viewport_center_hz = center_hz
        self._visible_span_hz = span_hz
        self.refresh()

    def render(self) -> Text:
        width = self.size.width
        height = self.size.height
        if width < 5 or height < 1:
            return Text("...")

        rows_to_show = min(len(self._history), height)
        rng = self._norm_max - self._norm_min
        if rng <= 0:
            rng = 1.0

        result = Text()
        for row_idx in range(height):
            if row_idx < rows_to_show:
                line = self._render_row(self._history[row_idx], width, rng)
            else:
                line = Text("░" * width, f"#1e1b4b on {NO_DATA_COLOR}")

            result.append(line)
            if row_idx < height - 1:
                result.append("\n")

        return result

    def _render_row(self, row: _WaterfallRow, width: int, rng: float) -> Text:
        line = Text()
        col_values = slice_band_to_viewport(
            row.band_cols,
            row.center_hz,
            row.sample_rate,
            self._viewport_center_hz,
            self._visible_span_hz,
            width,
        )

        for col in range(width):
            val = col_values[col]
            if np.isnan(val):
                line.append("░", f"#1e1b4b on {NO_DATA_COLOR}")
            else:
                norm = max(0.0, min(1.0, (val - self._norm_min) / rng))
                color_idx = min(
                    int(norm * (len(WATERFALL_GRADIENT) - 1)),
                    len(WATERFALL_GRADIENT) - 1,
                )
                line.append(" ", f"on {WATERFALL_GRADIENT[color_idx]}")

        return line

    def _update_normalization(self) -> None:
        height = max(self.size.height, 20)
        visible = self._history[:height]
        if not visible:
            return

        all_vals = np.concatenate([r.band_cols for r in visible])
        self._norm_min = float(np.percentile(all_vals, 5))
        self._norm_max = float(np.percentile(all_vals, 99))
