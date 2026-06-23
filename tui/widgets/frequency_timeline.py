"""
xyz-sdr | tui/widgets/frequency_timeline.py
Regla horizontal de frecuencias con cursor de sintonia.
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


class FrequencyTimeline(Widget):
    """Regla de frecuencias horizontal con cursor de sintonia."""

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
    hover_col: reactive[Optional[int]] = reactive(None)

    # ── Mensajes personalizados ──────────────────────────────────────────────

    class ScrollRequest(Message):
        """Peticion para desplazar la sintonia."""
        def __init__(self, direction: int) -> None:
            self.direction = direction
            super().__init__()

    class TuneRequest(Message):
        """Peticion para sintonizar una frecuencia especifica."""
        def __init__(self, frequency_hz: float) -> None:
            self.frequency_hz = frequency_hz
            super().__init__()

    class ZoomRequest(Message):
        """Peticion para cambiar el nivel de zoom (span visible)."""
        def __init__(self, direction: int) -> None:
            self.direction = direction
            super().__init__()

    # ── Eventos de Raton ─────────────────────────────────────────────────────

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        """Desplazar hacia la derecha (frecuencia arriba) o zoom in si se presiona Ctrl."""
        event.stop()
        if event.ctrl:
            self.post_message(self.ZoomRequest(direction=-1))  # Zoom In (ver menos frecuencias)
        else:
            self.post_message(self.ScrollRequest(direction=1))

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        """Desplazar hacia la izquierda (frecuencia abajo) o zoom out si se presiona Ctrl."""
        event.stop()
        if event.ctrl:
            self.post_message(self.ZoomRequest(direction=1))   # Zoom Out (ver mas frecuencias)
        else:
            self.post_message(self.ScrollRequest(direction=-1))

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Sintonizar directamente a la posicion cliqueada."""
        event.stop()
        width = self.size.width
        if width <= 0:
            return
        left_hz = self.viewport_center_hz - self.visible_span_hz / 2
        # Calcular frecuencia correspondiente a la columna X
        clicked_freq = left_hz + (event.x / width) * self.visible_span_hz
        self.post_message(self.TuneRequest(clicked_freq))

    def on_mouse_move(self, event: events.MouseMove) -> None:
        """Rastrear posicion del raton para mostrar frecuencia hover."""
        self.hover_col = event.x

    def on_mouse_leave(self, event: events.MouseLeave) -> None:
        """Quitar frecuencia hover al salir."""
        self.hover_col = None

    # ── Rendering ────────────────────────────────────────────────────────────

    def render(self) -> Text:
        width = self.size.width
        if width < 10:
            return Text("...")

        left_hz = self.viewport_center_hz - self.visible_span_hz / 2
        right_hz = self.viewport_center_hz + self.visible_span_hz / 2

        tick_spacing = self._nice_tick_spacing(width)

        # ── Fila 1: indicador del cursor y frecuencia digital ──
        cursor_col = self._freq_to_col(self.tuned_freq_hz, width)
        
        # Generar lista de caracteres y estilos
        chars = [" "] * width
        styles = [None] * width

        # Colocar cursor sintonizado
        if 0 <= cursor_col < width:
            chars[cursor_col] = "\u25bc"  # ▼
            styles[cursor_col] = "bold #ff6b6b"

        # Colocar cursor hover
        if self.hover_col is not None and 0 <= self.hover_col < width:
            if self.hover_col != cursor_col:
                chars[self.hover_col] = "\u25bd"  # ▽
                styles[self.hover_col] = "bold #38bdf8"

        # Añadir readout digital
        digital_text = ""
        digital_style = ""
        if self.hover_col is not None and 0 <= self.hover_col < width:
            hover_freq = left_hz + (self.hover_col / width) * self.visible_span_hz
            digital_text = f" ▽ {hover_freq / 1e6:.6f} MHz "
            digital_style = "bold #38bdf8"
        else:
            digital_text = f" ▼ {self.tuned_freq_hz / 1e6:.6f} MHz "
            digital_style = "bold #ff6b6b"

        if digital_text:
            text_len = len(digital_text)
            # Posicionamiento adaptativo: si el cursor principal esta a la derecha,
            # colocamos el texto a la izquierda, y viceversa.
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

        # ── Fila 2: marcas de graduacion ──
        tick_cols = set()
        first_tick = math.ceil(left_hz / tick_spacing) * tick_spacing
        t = first_tick
        while t <= right_hz:
            col = self._freq_to_col(t, width)
            if 0 <= col < width:
                tick_cols.add(col)
            t += tick_spacing

        row_ticks = Text()
        for c in range(width):
            if c == cursor_col:
                row_ticks.append("\u2502", "bold #ff6b6b")  # │ coloreado
            elif self.hover_col is not None and c == self.hover_col:
                row_ticks.append("\u2502", "bold #38bdf8")  # │ hover
            elif c in tick_cols:
                row_ticks.append("\u2502", "bold #7c3aed")  # │ tick
            else:
                row_ticks.append("\u2500", "#3b2570")        # ─

        # ── Fila 3: etiquetas de frecuencia ──
        row_labels = self._build_label_row(
            width, left_hz, right_hz, tick_spacing, first_tick
        )

        # Combinar
        result = Text()
        result.append(row_cursor)
        result.append("\n")
        result.append(row_ticks)
        result.append("\n")
        result.append(row_labels)
        return result

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _freq_to_col(self, freq_hz: float, width: int) -> int:
        """Convierte frecuencia absoluta a columna de pantalla."""
        left_hz = self.viewport_center_hz - self.visible_span_hz / 2
        if self.visible_span_hz <= 0:
            return width // 2
        col = int((freq_hz - left_hz) / self.visible_span_hz * width)
        return max(-1, min(col, width))  # permitir -1 y width para fuera de rango

    def _nice_tick_spacing(self, width: int) -> float:
        """Calcula un espaciado 'bonito' para los ticks (1, 2, 5 x 10^n)."""
        target_ticks = max(3, width // 14)
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
        """Formatea frecuencia para etiqueta. Precision adaptativa al zoom."""
        mhz = freq_hz / 1e6
        if self.visible_span_hz >= 50e6:
            return f"{mhz:.0f}M"
        elif self.visible_span_hz >= 5e6:
            return f"{mhz:.1f}M"
        elif self.visible_span_hz >= 500e3:
            return f"{mhz:.2f}M"
        else:
            return f"{mhz:.3f}M"

    def _build_label_row(
        self,
        width: int,
        left_hz: float,
        right_hz: float,
        tick_spacing: float,
        first_tick: float,
    ) -> Text:
        """Construye la fila de etiquetas evitando solapamientos."""
        chars = [" "] * width
        placed: list[tuple[int, int]] = []  # (start, end) de etiquetas colocadas

        t = first_tick
        while t <= right_hz:
            col = self._freq_to_col(t, width)
            label = self._format_freq(t)
            start = col - len(label) // 2
            end = start + len(label)

            if start >= 0 and end <= width:
                # Solapamiento con padding minimo de 1 caracter para colocar mas marcas
                overlap = any(
                    start < pe + 1 and end > ps - 1 for ps, pe in placed
                )
                if not overlap:
                    for i, ch in enumerate(label):
                        chars[start + i] = ch
                    placed.append((start, end))
            t += tick_spacing

        row = Text()
        row.append("".join(chars), "#fcd34d")  # Usamos amarillo brillante para excelente contraste
        return row

    # ── Watchers ─────────────────────────────────────────────────────────────

    def watch_viewport_center_hz(self, value: float) -> None:
        self.refresh()

    def watch_visible_span_hz(self, value: float) -> None:
        self.refresh()

    def watch_tuned_freq_hz(self, value: float) -> None:
        self.refresh()

    def watch_hover_col(self, value: Optional[int]) -> None:
        self.refresh()
