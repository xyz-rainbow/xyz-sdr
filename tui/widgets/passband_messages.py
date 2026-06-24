"""
xyz-sdr | tui/widgets/passband_messages.py
Mensajes y mixin de arrastre para selección de banda audible.
"""

from __future__ import annotations

from textual import events
from textual.message import Message
from textual.widget import Widget

from core.passband import (
    DRAG_PIXEL_THRESHOLD,
    col_to_freq,
    symmetric_width_from_drag,
)
from tui.widgets.display_palette import plot_content_width


class PassbandPreview(Message):
    """Vista previa en vivo del ancho de banda durante arrastre."""

    def __init__(self, center_hz: float, width_hz: float | None) -> None:
        self.center_hz = center_hz
        self.width_hz = width_hz
        super().__init__()


class PassbandSelectRequest(Message):
    """Confirma centro y ancho de banda audible."""

    def __init__(self, center_hz: float, width_hz: float) -> None:
        self.center_hz = center_hz
        self.width_hz = width_hz
        super().__init__()


class PassbandDragMixin:
    """Arrastre simétrico: mousedown fija centro; move define ancho."""

    _passband_drag_active: bool = False
    _passband_drag_center_hz: float = 0.0
    _passband_drag_start_x: int = 0
    _passband_drag_moved: bool = False

    def _passband_viewport(self) -> tuple[float, float]:
        return (
            float(getattr(self, "viewport_center_hz", getattr(self, "_viewport_center_hz", 0.0))),
            float(getattr(self, "visible_span_hz", getattr(self, "_visible_span_hz", 1.0))),
        )

    def _passband_x_to_freq(self, x: int) -> float:
        center, span = self._passband_viewport()
        return col_to_freq(
            float(x),
            widget_width=max(plot_content_width(self), 1),
            viewport_center_hz=center,
            visible_span_hz=span,
        )

    def on_mouse_down(self, event: events.MouseDown) -> None:
        event.stop()
        width = self.size.width
        if width <= 0:
            return
        self._passband_drag_active = True
        self._passband_drag_start_x = event.x
        self._passband_drag_moved = False
        self._passband_drag_center_hz = self._passband_x_to_freq(event.x)
        self.post_message(PassbandPreview(self._passband_drag_center_hz, None))

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if not self._passband_drag_active:
            return
        if abs(event.x - self._passband_drag_start_x) >= DRAG_PIXEL_THRESHOLD:
            self._passband_drag_moved = True
        cursor_hz = self._passband_x_to_freq(event.x)
        width_hz = symmetric_width_from_drag(self._passband_drag_center_hz, cursor_hz)
        self.post_message(PassbandPreview(self._passband_drag_center_hz, width_hz))

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if not self._passband_drag_active:
            return
        event.stop()
        self._passband_drag_active = False
        center_hz = self._passband_drag_center_hz
        if not self._passband_drag_moved:
            self.post_message(PassbandSelectRequest(center_hz, 0.0))
        else:
            cursor_hz = self._passband_x_to_freq(event.x)
            width_hz = symmetric_width_from_drag(center_hz, cursor_hz)
            self.post_message(PassbandSelectRequest(center_hz, width_hz))
        self.post_message(PassbandPreview(center_hz, None))
