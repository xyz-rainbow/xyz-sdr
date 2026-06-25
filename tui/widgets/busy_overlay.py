"""
xyz-sdr | tui/widgets/busy_overlay.py
Overlay de carga estilo splash para operaciones largas en la TUI.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label, Static


def _progress_bar_text(percent: int, width: int = 40) -> str:
    percent = max(0, min(100, percent))
    filled = int((percent / 100) * width)
    empty = width - filled
    return f"[{'█' * filled}{'░' * empty}] {percent:3d}%"


class BusyOverlay(Widget):
    """Barra de progreso indeterminada sobre fondo semitransparente."""

    DEFAULT_CSS = """
    BusyOverlay {
        width: 100%;
        height: 100%;
        align: center middle;
        background: rgba(9, 13, 22, 0.92);
    }

    #busy_card {
        width: 56;
        max-width: 90%;
        height: auto;
        background: #0b0f19;
        border: round #6366f1;
        padding: 1 2;
    }

    #busy_label {
        color: #c084fc;
        text-style: bold;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }

    #busy_bar {
        color: #22d3ee;
        text-align: center;
        width: 100%;
        height: 1;
    }
    """

    label = reactive("Cargando…")
    percent = reactive(0)

    def compose(self) -> ComposeResult:
        with Container(id="busy_card"):
            with Vertical():
                yield Label("", id="busy_label")
                yield Static("", id="busy_bar")

    def watch_label(self, value: str) -> None:
        try:
            self.query_one("#busy_label", Label).update(value)
        except Exception:
            pass

    def watch_percent(self, value: int) -> None:
        try:
            bar = _progress_bar_text(value)
            color = "#22d3ee" if value < 50 else "#84cc16"
            self.query_one("#busy_bar", Static).update(f"[{color}]{bar}[/]")
        except Exception:
            pass

    def on_mount(self) -> None:
        self.watch_label(self.label)
        self.watch_percent(self.percent)
