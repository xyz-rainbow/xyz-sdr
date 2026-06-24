"""
xyz-sdr | tui/widgets/frequency_timeline.py
Regla horizontal de frecuencias con cursor de sintonia y banda audible.
Comparte el eje X con SpectrumGraph y WaterfallTimeline.
"""

from __future__ import annotations

import math
from typing import Optional

from rich.text import Text
from textual.widget import Widget
from textual.reactive import reactive
from textual.message import Message
from textual import events

from core.passband import freq_to_col
from tui.widgets.passband_messages import PassbandDragMixin


class FrequencyTimeline(PassbandDragMixin, Widget):
    """Regla de frecuencias horizontal con cursor de sintonia y banda audible."""

    DEFAULT_CSS = """
    FrequencyTimeline {
        height: 3;
        background: #0a0a14;
        color: #a78bfa;
    }
    """

    viewport_center_hz: reactive[float] = reactive(100_600_000.0)
    visible_span_hz: reactive[float] = reactive(2_048_000.0)
    tuned_freq_hz: reactive[float] = reactive(100_600_000.0)
    passband_center_hz: reactive[float] = reactive(100_600_000.0)
    passband_width_hz: reactive[float] = reactive(200_000.0)
    passband_preview_width_hz: reactive[Optional[float]] = reactive(None)
    hover_col: reactive[Optional[int]] = reactive(None)

    class ScrollRequest(Message):
        """Peticion para desplazar la sintonia."""

        def __init__(self, direction: int) -> None:
            self.direction = direction
            super().__init__()

    class ZoomRequest(Message):
        """Peticion para cambiar el nivel de zoom (span visible)."""

        def __init__(self, direction: int) -> None:
            self.direction = direction
            super().__init__()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        event.stop()
        if event.ctrl:
            self.post_message(self.ZoomRequest(direction=-1))
        else:
            self.post_message(self.ScrollRequest(direction=1))

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        event.stop()
        if event.ctrl:
            self.post_message(self.ZoomRequest(direction=1))
        else:
            self.post_message(self.ScrollRequest(direction=-1))

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self.hover_col != event.x:
            self.hover_col = event.x
        PassbandDragMixin.on_mouse_move(self, event)

    def on_mouse_leave(self, event: events.MouseLeave) -> None:
        self.hover_col = None

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
            viewport_center_hz=self.viewport_center_hz,
            visible_span_hz=self.visible_span_hz,
        )
        col_r = freq_to_col(
            right_hz,
            widget_width=width,
            viewport_center_hz=self.viewport_center_hz,
            visible_span_hz=self.visible_span_hz,
        )
        return min(col_l, col_r), max(col_l, col_r)

    def render(self) -> Text:
        width = self.size.width
        if width < 10:
            return Text("...")

        left_hz = self.viewport_center_hz - self.visible_span_hz / 2
        tick_spacing = self._nice_tick_spacing(width)
        cursor_col = self._freq_to_col(self.tuned_freq_hz, width)
        passband_cols = self._passband_cols(width)

        chars = [" "] * width
        styles: list[str | None] = [None] * width

        if passband_cols:
            pb_l, pb_r = passband_cols
            for c in range(max(0, pb_l), min(width, pb_r + 1)):
                chars[c] = "\u2593"  # ▓
                styles[c] = "#166534"

        if 0 <= cursor_col < width:
            chars[cursor_col] = "\u25bc"
            styles[cursor_col] = "bold #ff6b6b"

        if self.hover_col is not None and 0 <= self.hover_col < width:
            if self.hover_col != cursor_col and not self._passband_drag_active:
                chars[self.hover_col] = "\u25bd"
                styles[self.hover_col] = "bold #38bdf8"

        band_w = self._effective_passband_width()
        if self.hover_col is not None and 0 <= self.hover_col < width and not self._passband_drag_active:
            hover_freq = left_hz + (self.hover_col / width) * self.visible_span_hz
            if self.visible_span_hz >= 500e3:
                digital_text = f" \u25bd {hover_freq / 1e6:.6f} MHz "
            elif self.visible_span_hz >= 50e3:
                digital_text = f" \u25bd {hover_freq / 1e6:.7f} MHz "
            else:
                digital_text = f" \u25bd {hover_freq / 1e6:.8f} MHz "
            digital_style = "bold #38bdf8"
        else:
            freq_mhz = self.passband_center_hz / 1e6
            if band_w and band_w >= 1000:
                bw_label = f"{band_w / 1000:.0f} kHz"
            elif band_w:
                bw_label = f"{band_w:.0f} Hz"
            else:
                bw_label = ""
            if self.visible_span_hz >= 500e3:
                freq_part = f"{freq_mhz:.6f} MHz"
            elif self.visible_span_hz >= 50e3:
                freq_part = f"{freq_mhz:.7f} MHz"
            else:
                freq_part = f"{freq_mhz:.8f} MHz"
            digital_text = f" \u25bc {freq_part}"
            if bw_label:
                digital_text += f" | {bw_label} "
            else:
                digital_text += " "
            digital_style = "bold #ff6b6b"

        if digital_text:
            text_len = len(digital_text)
            ref_col = cursor_col if self.hover_col is None else self.hover_col
            if ref_col < width // 2:
                start_idx = width - text_len - 1
            else:
                start_idx = 1
            if start_idx > 0 and start_idx + text_len < width:
                can_place = True
                for i in range(text_len):
                    idx = start_idx + i
                    if idx == cursor_col or idx == self.hover_col:
                        can_place = False
                        break
                if can_place:
                    for i, ch in enumerate(digital_text):
                        chars[start_idx + i] = ch
                        styles[start_idx + i] = digital_style

        row_cursor = Text()
        for c in range(width):
            row_cursor.append(chars[c], styles[c] or "")

        tick_cols = set()
        first_tick = math.ceil(left_hz / tick_spacing) * tick_spacing
        t = first_tick
        right_hz = self.viewport_center_hz + self.visible_span_hz / 2
        while t <= right_hz:
            col = self._freq_to_col(t, width)
            if 0 <= col < width:
                tick_cols.add(col)
            t += tick_spacing

        row_ticks = Text()
        for c in range(width):
            in_band = passband_cols and passband_cols[0] <= c <= passband_cols[1]
            if c == cursor_col:
                row_ticks.append("\u2502", "bold #ff6b6b")
            elif self.hover_col is not None and c == self.hover_col:
                row_ticks.append("\u2502", "bold #38bdf8")
            elif in_band:
                row_ticks.append("\u2502", "bold #22c55e")
            elif c in tick_cols:
                row_ticks.append("\u2502", "bold #7c3aed")
            else:
                row_ticks.append("\u2500", "#3b2570")

        row_labels = self._build_label_row(
            width, left_hz, right_hz, tick_spacing, first_tick
        )

        result = Text()
        result.append(row_cursor)
        result.append("\n")
        result.append(row_ticks)
        result.append("\n")
        result.append(row_labels)
        return result

    def _freq_to_col(self, freq_hz: float, width: int) -> int:
        return freq_to_col(
            freq_hz,
            widget_width=width,
            viewport_center_hz=self.viewport_center_hz,
            visible_span_hz=self.visible_span_hz,
        )

    def _nice_tick_spacing(self, width: int) -> float:
        target_ticks = max(5, width // 8)
        raw = self.visible_span_hz / target_ticks
        if raw <= 0:
            return 1000.0
        mag = 10 ** math.floor(math.log10(raw))
        nice_steps = [1.0, 2.0, 5.0, 10.0]
        norm = raw / mag
        best_fit = 10.0
        for step in nice_steps:
            if norm < step * 1.3:
                best_fit = step
                break
        return best_fit * mag

    def _format_freq(self, freq_hz: float) -> str:
        mhz = freq_hz / 1e6
        if self.visible_span_hz >= 50e6:
            return f"{mhz:.0f}M"
        if self.visible_span_hz >= 5e6:
            return f"{mhz:.1f}M"
        if self.visible_span_hz >= 500e3:
            return f"{mhz:.2f}M"
        if self.visible_span_hz >= 50e3:
            return f"{mhz:.3f}M"
        if self.visible_span_hz >= 10e3:
            return f"{mhz:.4f}M"
        return f"{mhz:.5f}M"

    def _build_label_row(
        self,
        width: int,
        left_hz: float,
        right_hz: float,
        tick_spacing: float,
        first_tick: float,
    ) -> Text:
        chars = [" "] * width
        placed: list[tuple[int, int]] = []

        t = first_tick
        while t <= right_hz:
            col = self._freq_to_col(t, width)
            label = self._format_freq(t)
            start = col - len(label) // 2
            end = start + len(label)
            if start >= 0 and end <= width:
                overlap = any(start < pe + 1 and end > ps - 1 for ps, pe in placed)
                if not overlap:
                    for i, ch in enumerate(label):
                        chars[start + i] = ch
                    placed.append((start, end))
            t += tick_spacing

        row = Text()
        row.append("".join(chars), "#fcd34d")
        return row

    def watch_viewport_center_hz(self, value: float) -> None:
        self.refresh()

    def watch_visible_span_hz(self, value: float) -> None:
        self.refresh()

    def watch_tuned_freq_hz(self, value: float) -> None:
        self.refresh()

    def watch_passband_center_hz(self, value: float) -> None:
        self.refresh()

    def watch_passband_width_hz(self, value: float) -> None:
        self.refresh()

    def watch_passband_preview_width_hz(self, value: Optional[float]) -> None:
        self.refresh()

    def watch_hover_col(self, value: Optional[int]) -> None:
        self.refresh()
