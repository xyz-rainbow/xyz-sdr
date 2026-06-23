"""
xyz-sdr | tui/widgets/waterfall_timeline.py
Espectrograma en cascada (waterfall) con alineacion dinamica por frecuencia.
Cada fila almacena band_cols pre-proyectados sobre el BW de captura.
"""

from __future__ import annotations

import time
from collections import deque
from contextlib import suppress
from itertools import islice

import numpy as np
from rich.text import Text
from textual.widget import Widget
from textual.reactive import reactive
from textual.message import Message
from textual import events

from core.band_buffer import BandFrame, slice_band_history_to_viewport, slice_band_to_viewport
from core.input_modifiers import is_shift_pressed


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

    class HistoryScrollRequest(Message):
        """Desplaza la ventana vertical sobre el historial almacenado."""

        def __init__(self, direction: int) -> None:
            self.direction = direction
            super().__init__()

    def __init__(
        self,
        max_history: int = 100,
        history_buffer_ratio: float = 2 / 3,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._history: deque[_WaterfallRow] = deque(maxlen=max(1, int(max_history)))
        self._max_history = max(1, int(max_history))
        self._history_buffer_ratio = max(0.0, float(history_buffer_ratio))
        self._layout_height: int = 1
        self._viewport_center_hz: float = 100_600_000.0
        self._visible_span_hz: float = 2_048_000.0
        self._history_offset: int = 0
        self._last_row_time: float = 0.0
        self._norm_min: float = -80.0
        self._norm_max: float = -20.0
        self._norm_last_update: float = 0.0
        self._slice_cache: np.ndarray | None = None
        self._slice_cache_rows: int = 0
        self._slice_cache_width: int = 0
        self._rich_visual_cache: Text | None = None
        self._rich_visual_cache_key: tuple | None = None
        self._row_text_cache: dict[tuple, Text] = {}

    @property
    def allow_vertical_scroll(self) -> bool:
        """Evita que Textual consuma Shift+rueda como scroll nativo del widget."""
        return False

    @property
    def allow_horizontal_scroll(self) -> bool:
        return False

    def _view_width(self) -> int:
        try:
            width = int(self.content_region.width)
            if width > 0:
                return width
        except Exception:
            pass
        return max(int(self.size.width) - 2, 1)

    def _view_height(self) -> int:
        try:
            height = int(self.content_region.height)
            if height > 0:
                return height
        except Exception:
            pass
        return max(int(self.size.height) - 2, 1)

    @property
    def history_offset(self) -> int:
        return self._history_offset

    def _max_history_offset(self) -> int:
        height = max(self._layout_height, self._view_height(), 1)
        return max(0, len(self._history) - height)

    def scroll_history(self, direction: int, *, steps: int = 1) -> bool:
        """
        Desplaza la ventana vertical del historial.

        direction > 0 → filas más antiguas; direction < 0 → más recientes.
        """
        if steps < 1:
            steps = 1
        moved = False
        for _ in range(steps):
            prev = self._history_offset
            self._history_offset = max(
                0,
                min(self._max_history_offset(), self._history_offset + direction),
            )
            if self._history_offset != prev:
                moved = True
            else:
                break

        if not moved:
            return False

        self._rebuild_slice_cache()
        self._invalidate_rich_cache()
        self.refresh()
        return True

    @staticmethod
    def _wheel_steps(event: events.MouseEvent) -> int:
        delta_y = getattr(event, "delta_y", 0)
        if delta_y == 0:
            return 1
        return max(1, abs(int(delta_y)))

    def _handle_wheel(self, event: events.MouseEvent, *, scroll_up: bool) -> None:
        """Rueda en cascada: Shift+scroll = historial vertical; Ctrl+scroll = zoom horizontal."""
        event.stop()
        with suppress(Exception):
            event.prevent_default()

        if event.ctrl:
            from tui.widgets.frequency_timeline import FrequencyTimeline
            zoom_dir = -1 if scroll_up else 1
            self.post_message(FrequencyTimeline.ZoomRequest(direction=zoom_dir))
            return

        if is_shift_pressed(event_shift=event.shift):
            history_dir = -1 if scroll_up else 1
            steps = self._wheel_steps(event)
            if self.scroll_history(history_dir, steps=steps):
                self.post_message(self.HistoryScrollRequest(history_dir))
            return

        from tui.widgets.frequency_timeline import FrequencyTimeline
        freq_dir = 1 if scroll_up else -1
        self.post_message(FrequencyTimeline.ScrollRequest(direction=freq_dir))

    def _on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self._handle_wheel(event, scroll_up=True)

    def _on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self._handle_wheel(event, scroll_up=False)

    def on_mouse_down(self, event: events.MouseDown) -> None:
        event.stop()
        self.app.set_focus(None)

    def on_resize(self, event: events.Resize) -> None:
        self._layout_height = max(self._view_height(), 1)
        self._ensure_history_maxlen()
        self._history_offset = min(self._history_offset, self._max_history_offset())
        self._invalidate_rich_cache()

    def _invalidate_rich_cache(self) -> None:
        self._rich_visual_cache = None
        self._rich_visual_cache_key = None
        self._row_text_cache.clear()

    def _effective_max_history(self) -> int:
        """Tope de filas en memoria — usa waterfall_history del config para scroll."""
        return self._max_history

    def _ensure_history_maxlen(self) -> None:
        maxlen = self._effective_max_history()
        if self._history.maxlen != maxlen:
            self._history = deque(self._history, maxlen=maxlen)
        self._history_offset = min(self._history_offset, self._max_history_offset())

    def add_band_row(self, frame: BandFrame) -> None:
        """Agrega fila desde BandFrame pre-proyectado (throttle por waterfall_speed)."""
        now = time.time()
        interval = 1.0 / max(1, self.waterfall_speed)
        if now - self._last_row_time < interval:
            return

        self._last_row_time = now
        self._ensure_history_maxlen()
        self._history.appendleft(
            _WaterfallRow(frame.center_hz, frame.sample_rate, frame.band_cols),
        )
        self._history_offset = min(self._history_offset, self._max_history_offset())
        self._update_normalization()

        if self._history_offset == 0:
            self._prepend_slice_row(frame)
        else:
            self._rebuild_slice_cache()

        self._invalidate_rich_cache()
        self.refresh()

    def _prepend_slice_row(self, frame: BandFrame) -> None:
        """Actualiza caché slice en O(ancho) en lugar de re-slicear todo el historial."""
        width = self._view_width()
        height = self._view_height()
        if width < 5 or height < 1:
            return

        new_row = slice_band_to_viewport(
            frame.band_cols,
            frame.center_hz,
            frame.sample_rate,
            self._viewport_center_hz,
            self._visible_span_hz,
            width,
        ).reshape(1, -1)

        if (
            self._slice_cache is not None
            and self._slice_cache_width == width
            and self._slice_cache.shape[1] == width
        ):
            combined = np.vstack([new_row, self._slice_cache])
            self._slice_cache = combined[:height]
        else:
            self._rebuild_slice_cache()
            return

        self._slice_cache_rows = self._slice_cache.shape[0]
        self._slice_cache_width = width

    def clear_history(self) -> None:
        """Invalida historial (p. ej. al cambiar bandwidth)."""
        self._history.clear()
        self._history_offset = 0
        self._last_row_time = 0.0
        self._slice_cache = None
        self._invalidate_rich_cache()
        self.refresh()

    def set_viewport(self, center_hz: float, span_hz: float) -> None:
        """Actualiza viewport horizontal (zoom freq). No altera el offset vertical del historial."""
        if (
            abs(self._viewport_center_hz - center_hz) < 0.5
            and abs(self._visible_span_hz - span_hz) < 0.5
            and self._slice_cache is not None
        ):
            return

        self._viewport_center_hz = center_hz
        self._visible_span_hz = span_hz
        self._rebuild_slice_cache()
        self._invalidate_rich_cache()
        self.refresh()

    def _history_rows_for_viewport(self, rows_to_show: int) -> list[_WaterfallRow]:
        return list(
            islice(self._history, self._history_offset, self._history_offset + rows_to_show)
        )

    def _rebuild_slice_cache(self) -> None:
        width = self._view_width()
        height = self._view_height()
        available = max(0, len(self._history) - self._history_offset)
        rows_to_show = min(available, height)

        if rows_to_show <= 0 or width < 5:
            self._slice_cache = None
            self._slice_cache_rows = 0
            self._slice_cache_width = 0
            return

        visible_rows = self._history_rows_for_viewport(rows_to_show)
        row_tuples = [(r.center_hz, r.sample_rate, r.band_cols) for r in visible_rows]
        self._slice_cache = slice_band_history_to_viewport(
            row_tuples,
            self._viewport_center_hz,
            self._visible_span_hz,
            width,
        )
        self._slice_cache_rows = rows_to_show
        self._slice_cache_width = width

    def render(self) -> Text:
        width = self._view_width()
        height = self._view_height()
        if width < 5 or height < 1:
            return Text("...")

        expected_rows = min(max(0, len(self._history) - self._history_offset), height)
        if (
            self._slice_cache is None
            or self._slice_cache_width != width
            or self._slice_cache_rows != expected_rows
        ):
            self._rebuild_slice_cache()

        cache_key = (
            id(self._slice_cache),
            self._norm_min,
            self._norm_max,
            width,
            height,
            self._slice_cache_rows,
            self._history_offset,
        )
        if self._rich_visual_cache is not None and cache_key == self._rich_visual_cache_key:
            return self._rich_visual_cache

        rows_to_show = self._slice_cache_rows
        rng = self._norm_max - self._norm_min
        if rng <= 0:
            rng = 1.0

        result = Text()
        for row_idx in range(height):
            if row_idx < rows_to_show and self._slice_cache is not None:
                row_data = self._slice_cache[row_idx]
                line = self._render_row_cached(row_data, width, rng)
            else:
                line = Text("░" * width, f"#1e1b4b on {NO_DATA_COLOR}")

            result.append(line)
            if row_idx < height - 1:
                result.append("\n")

        self._rich_visual_cache = result
        self._rich_visual_cache_key = cache_key
        return result

    def _row_cache_key(self, col_values: np.ndarray, width: int, rng: float) -> tuple:
        digest = col_values.tobytes() if col_values is not None else b""
        return (digest, self._norm_min, self._norm_max, width, rng)

    def _render_row_cached(self, col_values: np.ndarray, width: int, rng: float) -> Text:
        key = self._row_cache_key(col_values, width, rng)
        cached = self._row_text_cache.get(key)
        if cached is not None:
            return cached

        line = self._render_row_from_cache(col_values, width, rng)
        if len(self._row_text_cache) > max(width, 64):
            self._row_text_cache.clear()
        self._row_text_cache[key] = line
        return line

    def _render_row_from_cache(self, col_values: np.ndarray, width: int, rng: float) -> Text:
        line = Text()
        for col in range(width):
            val = col_values[col] if col < len(col_values) else np.nan
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
        now = time.time()
        if now - self._norm_last_update < 0.5:
            return

        height = max(self._layout_height, self._view_height(), 1)
        visible = self._history_rows_for_viewport(min(len(self._history), height))
        if not visible:
            return

        all_vals = np.concatenate([r.band_cols for r in visible])
        self._norm_min = float(np.percentile(all_vals, 5))
        self._norm_max = float(np.percentile(all_vals, 99))
        self._norm_last_update = now
        self._invalidate_rich_cache()
