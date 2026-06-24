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
from core.passband import freq_to_col
from core.input_modifiers import is_shift_pressed
from tui.widgets.display_palette import cell_background, compute_auto_levels, normalize_per_column, plot_content_width


NO_DATA_COLOR = "#08080f"
_NORM_BLEND = 0.22  # EMA al actualizar rango dB (evita flash al cambiar zoom)


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
    passband_center_hz: reactive[float] = reactive(100_600_000.0)
    passband_width_hz: reactive[float] = reactive(200_000.0)
    passband_preview_width_hz: reactive[float | None] = reactive(None)
    waterfall_speed: reactive[int] = reactive(10)
    waterfall_auto_level: reactive[bool] = reactive(True)

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

    class HistoryScrollRequest(Message):
        """Desplaza la ventana vertical sobre el historial almacenado."""

        def __init__(self, direction: int) -> None:
            self.direction = direction
            super().__init__()

    def __init__(
        self,
        max_history: int = 100,
        history_buffer_ratio: float = 2 / 3,
        *,
        waterfall_auto_level: bool = True,
        level_low_pct: float = 5.0,
        level_high_pct: float = 99.0,
        min_range_db: float = 6.0,
        manual_norm_min: float = -80.0,
        manual_norm_max: float = -20.0,
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
        self._level_low_pct = float(level_low_pct)
        self._level_high_pct = float(level_high_pct)
        self._min_range_db = float(min_range_db)
        self._manual_norm_min = float(manual_norm_min)
        self._manual_norm_max = float(manual_norm_max)
        self._column_floors: np.ndarray | None = None
        self._column_ceilings: np.ndarray | None = None
        self._norm_last_update: float = 0.0
        self._frequency_columns: int = 0
        self._levels_from_app: bool = False
        self._slice_cache: np.ndarray | None = None
        self._slice_cache_rows: int = 0
        self._slice_cache_width: int = 0
        self._rich_visual_cache: Text | None = None
        self._rich_visual_cache_key: tuple | None = None
        self._row_text_cache: dict[tuple, Text] = {}
        self.waterfall_auto_level = waterfall_auto_level

    @property
    def allow_vertical_scroll(self) -> bool:
        """Evita que Textual consuma Shift+rueda como scroll nativo del widget."""
        return False

    @property
    def allow_horizontal_scroll(self) -> bool:
        return False

    def set_frequency_columns(self, width: int) -> None:
        width = max(int(width), 1)
        if width == self._frequency_columns:
            return
        self._frequency_columns = width
        self._rebuild_slice_cache()
        self._invalidate_rich_cache()

    def set_column_levels(self, floors: np.ndarray, ceilings: np.ndarray) -> None:
        self._column_floors = np.asarray(floors, dtype=np.float64).reshape(-1).copy()
        self._column_ceilings = np.asarray(ceilings, dtype=np.float64).reshape(-1).copy()
        self._levels_from_app = True
        self._invalidate_rich_cache()

    def set_level_range(self, level_min: float, level_max: float) -> None:
        width = self._column_width()
        self.set_column_levels(
            np.full(width, float(level_min)),
            np.full(width, float(level_max)),
        )

    def get_level_history(self, max_rows: int | None = None) -> np.ndarray | None:
        """Filas visibles del slice_cache para estimar suelo/techo por columna."""
        if self._slice_cache is None or self._slice_cache.size == 0:
            return None
        rows = self._slice_cache
        if max_rows is not None and rows.shape[0] > max_rows:
            rows = rows[:max_rows]
        return rows

    def _levels_for_width(self, width: int) -> tuple[np.ndarray, np.ndarray]:
        if self._column_floors is not None and self._column_ceilings is not None:
            floors = np.asarray(self._column_floors, dtype=np.float64).reshape(-1)
            ceilings = np.asarray(self._column_ceilings, dtype=np.float64).reshape(-1)
            if len(floors) < width:
                floors = np.pad(floors, (0, width - len(floors)), constant_values=self._manual_norm_min)
            if len(ceilings) < width:
                ceilings = np.pad(ceilings, (0, width - len(ceilings)), constant_values=self._manual_norm_max)
            return floors[:width], ceilings[:width]
        return (
            np.full(width, self._manual_norm_min, dtype=np.float64),
            np.full(width, self._manual_norm_max, dtype=np.float64),
        )

    def _column_width(self) -> int:
        if self._frequency_columns > 0:
            return self._frequency_columns
        return plot_content_width(self)

    def _view_width(self) -> int:
        return self._column_width()

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
        self._history.append(
            _WaterfallRow(frame.center_hz, frame.sample_rate, frame.band_cols),
        )
        self._history_offset = min(self._history_offset, self._max_history_offset())

        if self._history_offset == 0:
            self._prepend_slice_row(frame)
        else:
            self._rebuild_slice_cache()

        if not self._levels_from_app:
            self._update_normalization()
        self._invalidate_rich_cache()
        self.refresh()

    def _prepend_slice_row(self, frame: BandFrame) -> None:
        """Actualiza caché slice en O(ancho); fila nueva al inicio (arriba en pantalla)."""
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
        if not self._levels_from_app:
            self._update_normalization(force=True)
        self._invalidate_rich_cache()
        self.refresh()

    def _history_rows_for_viewport(self, rows_to_show: int) -> list[_WaterfallRow]:
        total = len(self._history)
        end = max(0, total - self._history_offset)
        start = max(0, end - rows_to_show)
        return list(islice(self._history, start, end))

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
        sliced = slice_band_history_to_viewport(
            row_tuples,
            self._viewport_center_hz,
            self._visible_span_hz,
            width,
        )
        if sliced is None:
            self._slice_cache = None
            self._slice_cache_rows = 0
            self._slice_cache_width = 0
            return

        # Índice 0 = fila más reciente (top-down en pantalla).
        self._slice_cache = sliced[::-1]
        self._slice_cache_rows = rows_to_show
        self._slice_cache_width = width

    def _normalization_values(self) -> np.ndarray | None:
        if self._slice_cache is not None and self._slice_cache.size > 0:
            return self._slice_cache.ravel()
        return None

    def _compute_auto_levels(self, values: np.ndarray) -> tuple[float, float]:
        return compute_auto_levels(
            values,
            low_pct=self._level_low_pct,
            high_pct=self._level_high_pct,
            min_range_db=self._min_range_db,
            fallback=(self._manual_norm_min, self._manual_norm_max),
        )

    def _update_normalization(self, *, force: bool = False) -> None:
        if not self.waterfall_auto_level:
            width = self._column_width()
            self.set_column_levels(
                np.full(width, self._manual_norm_min),
                np.full(width, self._manual_norm_max),
            )
            return

        now = time.time()
        if not force and now - self._norm_last_update < 0.5:
            return

        values = self._normalization_values()
        if values is None:
            return

        new_min, new_max = self._compute_auto_levels(values)
        width = self._column_width()
        floors, ceilings = self._levels_for_width(width)

        if self._norm_last_update <= 0.0:
            floors = np.full(width, new_min)
            ceilings = np.full(width, new_max)
        else:
            blend = _NORM_BLEND if force else _NORM_BLEND * 0.5
            floors = (1.0 - blend) * floors + blend * new_min
            ceilings = (1.0 - blend) * ceilings + blend * new_max

        self.set_column_levels(floors, ceilings)
        self._levels_from_app = False
        self._norm_last_update = now
        self._invalidate_rich_cache()

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

        if not self._levels_from_app:
            self._update_normalization()

        floors, ceilings = self._levels_for_width(width)
        cache_key = (
            id(self._slice_cache),
            floors.tobytes(),
            ceilings.tobytes(),
            width,
            height,
            self._slice_cache_rows,
            self._history_offset,
            self.passband_center_hz,
            self.passband_width_hz,
            self.passband_preview_width_hz,
            self.waterfall_auto_level,
        )
        if self._rich_visual_cache is not None and cache_key == self._rich_visual_cache_key:
            return self._rich_visual_cache

        rows_to_show = self._slice_cache_rows

        result = Text()
        for row_idx in range(height):
            if row_idx < rows_to_show and self._slice_cache is not None:
                row_data = self._slice_cache[row_idx]
                line = self._render_row_cached(row_data, width, floors, ceilings)
            else:
                line = Text("░" * width, f"#1e1b4b on {NO_DATA_COLOR}")

            result.append(line)
            if row_idx < height - 1:
                result.append("\n")

        self._rich_visual_cache = result
        self._rich_visual_cache_key = cache_key
        return result

    def _row_cache_key(
        self,
        col_values: np.ndarray,
        width: int,
        floors: np.ndarray,
        ceilings: np.ndarray,
    ) -> tuple:
        digest = col_values.tobytes() if col_values is not None else b""
        return (digest, floors.tobytes(), ceilings.tobytes(), width, self.waterfall_auto_level)

    def _render_row_cached(
        self,
        col_values: np.ndarray,
        width: int,
        floors: np.ndarray,
        ceilings: np.ndarray,
    ) -> Text:
        key = self._row_cache_key(col_values, width, floors, ceilings)
        cached = self._row_text_cache.get(key)
        if cached is not None:
            return cached

        line = self._render_row_from_cache(col_values, width, floors, ceilings)
        if len(self._row_text_cache) > max(width, 64):
            self._row_text_cache.clear()
        self._row_text_cache[key] = line
        return line

    def _cell_background(self, norm: float, *, in_band: bool) -> str:
        return cell_background(norm, in_band=in_band)

    def _render_row_from_cache(
        self,
        col_values: np.ndarray,
        width: int,
        floors: np.ndarray,
        ceilings: np.ndarray,
    ) -> Text:
        passband_cols = self._passband_cols(width)
        line = Text()
        norms = normalize_per_column(col_values[:width], floors, ceilings)
        for col in range(width):
            in_band = passband_cols and passband_cols[0] <= col <= passband_cols[1]
            if col >= len(norms) or np.isnan(norms[col]):
                bg = NO_DATA_COLOR if in_band else "#050508"
                line.append("░", f"#1e1b4b on {bg}")
            else:
                norm = float(norms[col])
                bg = self._cell_background(norm, in_band=in_band)
                line.append(" ", f"on {bg}")
        return line

    def watch_passband_center_hz(self, value: float) -> None:
        self._invalidate_rich_cache()
        self.refresh()

    def watch_passband_width_hz(self, value: float) -> None:
        self._invalidate_rich_cache()
        self.refresh()

    def watch_passband_preview_width_hz(self, value: float | None) -> None:
        self._invalidate_rich_cache()
        self.refresh()

    def watch_waterfall_auto_level(self, value: bool) -> None:
        self._norm_last_update = 0.0
        self._update_normalization(force=True)
        self._invalidate_rich_cache()
        self.refresh()
