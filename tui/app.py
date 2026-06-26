"""
xyz-sdr | tui/app.py
Aplicacion principal Textual — TUI del controlador SDR.
v2: Timeline + Espectro + Waterfall con navegacion por teclado.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
import numpy as np
from typing import Optional

from rich.text import Text

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Container, VerticalGroup
from textual.widgets import (
    Header, Static, Label, Button,
    Select, Input, Log,
)
from textual.reactive import reactive
from textual import work, events

from core.device import (
    BANDWIDTH_PRESETS,
    HardwareInitializationError,
    SAFE_START_SAMPLE_RATE,
    SDRDevice,
    SampleRateError,
    _format_bandwidth_hz,
)
from core.config_store import persist_band_profile
from core.auto_demod import resolve_auto_demod_mode
from core.band_profiles import list_band_profiles, load_band_profile, merge_configs
from core.band_buffer import BandFrameMailbox
from core.stream_stats import StreamStats
from core.dsp import (
    apply_squelch_with_state,
    apply_fm_agc,
    estimate_snr_at_freq,
    SquelchGate,
    AudioAgc,
    FmDemodState,
)
from core.dsp_profiles import (
    profile_for_sample_rate,
    is_mode_recommended,
)
from core.audio_effects import AudioEffects
from core.audio_output import AudioOutputQueue
from core.recorder import SDRRecorder  # type: ignore  # legacy: re-export alias

from core.passband import (
    PASSBAND_KEYBOARD_STEP,
    clamp_passband_width,
    default_passband_width,
    freq_to_col,
)
from tui.rx_worker import run_rx_iteration
from tui.bandwidth import validate_sample_rate
from tui.widgets.passband_messages import PassbandPreview, PassbandSelectRequest
from tui.widgets.frequency_timeline import FrequencyTimeline
from tui.widgets.spectrum_graph import SpectrumGraph
from tui.widgets.waterfall_timeline import WaterfallTimeline
from core.display_levels import ColumnLevelTracker
from tui.widgets.display_palette import compute_auto_levels, plot_content_width

logger = logging.getLogger(__name__)


def _is_valid_select(value) -> bool:
    """Ignora valores vacíos o eventos espurios (Select.BLANK / Select.NULL)."""
    if value is None:
        return False
    blank = getattr(Select, "BLANK", object())
    if value is blank:
        return False
    null = getattr(Select, "NULL", None)
    if null is not None and value is null:
        return False
    type_name = type(value).__name__
    if type_name == "NoSelection" or str(value).startswith("Select."):
        return False
    return True


# ─── Constantes ──────────────────────────────────────────────────────────────

# Pasos de scroll predefinidos (Hz)
SCROLL_STEPS = [
    1_000, 5_000, 10_000, 25_000, 50_000,
    100_000, 500_000, 1_000_000, 5_000_000,
]
DEFAULT_STEP_INDEX = 5  # 100 kHz

# Pasos de zoom base (Hz) — se filtran y completan hasta sample_rate
ZOOM_SPAN_STEPS = [
    10_000,
    25_000,
    50_000,
    100_000,
    200_000,
    500_000,
    1_000_000,
    2_000_000,
    4_000_000,
]

# Velocidades de cascada (FPS)
WATERFALL_SPEEDS = [1, 2, 3, 5, 10, 25, 50]
WATERFALL_SPD_BTN_HEIGHT = 3
from tui.viewport import VIEWPORT_DEBOUNCE_S

# Limites de frecuencia del hardware
FREQ_MIN_HZ = 0.0
FREQ_MAX_HZ = 2_000_000_000.0  # 2 GHz (RSP1)

# Presets de emisoras
PRESETS = [
    ("RNE Radio Nacional",     100_600_000, "wbfm"),
    ("Cadena SER",             105_400_000, "wbfm"),
    ("Radio 3",                104_300_000, "wbfm"),
    ("40 Principales",          98_000_000, "wbfm"),
    ("Aviacion Barcelona APP", 120_900_000, "nbfm"),
    ("PMR Canal 1",            446_006_250, "nbfm"),
    ("Tiempo (HF LSB)",          4_855_000, "lsb"),
]


# ─── StatusBar ───────────────────────────────────────────────────────────────

class StatusBar(Static):
    """Barra inferior unificada: metricas en tiempo real + atajos de teclado."""

    _hints_text: Text | None = None

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        max-height: 1;
        background: #0f172a;
        color: #e2e8f0;
        text-style: bold;
        padding: 0 1;
        overflow: hidden;
        text-wrap: nowrap;
    }
    """

    @staticmethod
    def _append_key_hints(text) -> None:
        """Atajos compactos en la misma linea que las metricas."""
        dim = "#64748b"
        key = "bold #38bdf8"

        text.append(" ┃ ", "#475569")
        text.append("←→", key)
        text.append("Freq ", dim)
        text.append("↑↓", key)
        text.append("Step ", dim)
        text.append("^←→", key)
        text.append("Zoom ", dim)
        text.append("-/+", key)
        text.append("Zoom ", dim)
        text.append("Esc", key)
        text.append(" Ajustes ", dim)
        text.append("S", key)
        text.append(" RX ", dim)
        text.append("M", key)
        text.append(" Mod ", dim)
        text.append("F", key)
        text.append(" Freq ", dim)
        text.append("B", key)
        text.append(" BW ", dim)
        text.append("[", key)
        text.append("]", key)
        text.append(" PASS ", dim)
        text.append("G", key)
        text.append(" Gain ", dim)
        text.append("V", key)
        text.append(" Vol ", dim)
        text.append("R", key)
        text.append(" Rec ", dim)
        text.append("Shift+Wheel", key)
        text.append(" WF hist ", dim)
        text.append("Ctrl+Wheel", key)
        text.append(" WF zoom ", dim)
        text.append("Q", key)
        text.append(" Salir", dim)

    def update_status(
        self,
        freq: float,
        gain: float,
        volume: float,
        mode: str,
        snr: float,
        step: float,
        span: float,
        bandwidth: float,
        passband_width: float,
        device: str,
        *,
        squelch_enabled: bool = False,
        squelch_open: bool = True,
        recording: bool = False,
        stream_drop_rate: float = 0.0,
        stream_overflows: int = 0,
        sdrplay_blocked: bool = False,
    ) -> None:
        step_str = _format_hz(step)
        span_str = _format_hz(span)
        bw_str = _format_hz(bandwidth)
        pass_str = _format_hz(passband_width)
        
        # Uso de colores ricos y estructura limpia
        from rich.text import Text
        text = Text()
        text.append(" FREQ ", "bold #c084fc")
        text.append(f"{freq/1e6:.4f} MHz", "bold #ffffff")
        text.append(" ┃ ", "#475569")
        
        text.append("STEP ", "bold #a78bfa")
        text.append(f"{step_str}", "bold #ffffff")
        text.append(" ┃ ", "#475569")
        
        text.append("ZOOM ", "bold #818cf8")
        text.append(f"{span_str}", "bold #ffffff")
        text.append(" ┃ ", "#475569")

        text.append("BW ", "bold #22d3ee")
        text.append(f"{bw_str}", "bold #ffffff")
        text.append(" ┃ ", "#475569")

        text.append("PASS ", "bold #22c55e")
        text.append(f"{pass_str}", "bold #ffffff")
        text.append(" ┃ ", "#475569")
        
        text.append("GAIN ", "bold #fbbf24")
        text.append(f"{gain:.0f} dB", "bold #ffffff")
        text.append(" ┃ ", "#475569")

        text.append("VOL ", "bold #fb923c")
        text.append(f"{volume:.0f}%", "bold #ffffff")
        text.append(" ┃ ", "#475569")
        
        text.append("MODE ", "bold #f472b6")
        text.append(f"{mode.upper()}", "bold #ffffff")
        text.append(" ┃ ", "#475569")
        
        text.append("SNR ", "bold #34d399")
        text.append(f"{snr:.1f} dB", "bold #ffffff")
        text.append(" ┃ ", "#475569")

        if squelch_enabled:
            text.append("SQ ", "bold #a78bfa")
            sq_label = "OPEN" if squelch_open else "MUTE"
            sq_color = "#34d399" if squelch_open else "#f87171"
            text.append(sq_label, f"bold {sq_color}")
            text.append(" ┃ ", "#475569")

        if recording:
            text.append("REC ", "bold #ef4444")
            text.append("●", "bold #ef4444")
            text.append(" ┃ ", "#475569")

        if stream_overflows > 0 or stream_drop_rate >= 0.005:
            text.append("DROP ", "bold #f87171")
            drop_pct = stream_drop_rate * 100.0
            drop_label = f"{drop_pct:.1f}%" if stream_drop_rate >= 0.001 else f"ov{stream_overflows}"
            text.append(drop_label, "bold #fca5a5")
            text.append(" ┃ ", "#475569")
        
        text.append("DEV ", "bold #38bdf8")
        dev_label = device.upper()
        if sdrplay_blocked:
            dev_label = "SIM·BLOCK"
            text.append(dev_label, "bold #fbbf24")
        else:
            text.append(dev_label, "bold #ffffff")

        if StatusBar._hints_text is None:
            StatusBar._hints_text = Text()
            StatusBar._append_key_hints(StatusBar._hints_text)
        text.append_text(StatusBar._hints_text)

        self.update(text)


# ─── App Principal ───────────────────────────────────────────────────────────

class XyzSDRApp(App):
    """xyz-sdr Terminal SDR Controller v2."""

    CSS = """
    /* ── Tokens UI (Fase 0 — Outline, sin tint) ────────────────────────
     * PANEL_BG:      #0b0f19  sidebar (#controls)
     * DISPLAY_BG:    #090d16  espectro / cascada / barra velocidad
     * ACCENT_INDIGO: #4338ca  borde default
     * ACCENT_VIOLET: #6d28d9  borde alterno
     * ACCENT_GREEN:  #10b981  activo / éxito
     * ACCENT_FOCUS:  #818cf8  foco
     * Regla round: background = fondo del padre; sin tint ni fill sólido.
     * Ver docs/customization.md
     * ─────────────────────────────────────────────────────────────────── */

    Screen {
        background: #090d16;
    }

    Header {
        background: #0f172a;
        color: #c084fc;
        text-style: bold;
        border-bottom: solid #6366f1;
    }

    /* ── Layout principal ── */

    #main_area {
        height: 1fr;
    }

    #controls {
        width: 32;
        background: #0b0f19;
        padding: 0 1;
        overflow-y: auto;
        scrollbar-size: 0 0;
        border-right: round #1e293b;
    }

    #controls Label {
        color: #a78bfa;
        margin-top: 1;
        text-style: bold;
    }

    #controls Input {
        background: #0b0f19;
        border: round #4338ca;
        color: #e0e7ff;
        padding: 0 1;
    }

    #controls Input:hover {
        background: #0b0f19;
        border: round #4338ca;
        color: #e0e7ff;
    }

    #controls Input:focus {
        border: round #818cf8;
        background: #0b0f19;
    }

    #controls Select {
        background: #0b0f19;
        border: none;
        padding: 0;
        margin: 0;
        height: auto;
    }

    #controls Select > SelectCurrent {
        background: #0b0f19;
        background-tint: transparent;
        border: round #4338ca;
        border-top: round #4338ca;
        border-bottom: round #4338ca;
        color: #e0e7ff;
        padding: 0;
        width: 100%;
        height: 3;
    }

    #controls Select:hover > SelectCurrent {
        background: #0b0f19;
        background-tint: transparent;
        border: round #4338ca;
        border-top: round #4338ca;
        border-bottom: round #4338ca;
        color: #e0e7ff;
    }

    #controls Select > SelectCurrent Static#label {
        background: transparent;
        height: 1fr;
        padding: 0 1;
        content-align: left middle;
    }

    #controls Select > SelectCurrent .arrow {
        background: transparent;
        height: 1fr;
        padding: 0 1 0 0;
        content-align: center middle;
    }

    #controls Select:focus > SelectCurrent,
    #controls Select.-expanded > SelectCurrent,
    #controls Select > SelectCurrent:focus {
        border: round #4338ca;
        border-top: round #4338ca;
        border-bottom: round #4338ca;
        background: #0b0f19;
        background-tint: transparent;
    }

    #controls Select:focus > SelectCurrent Static#label,
    #controls Select:focus > SelectCurrent .arrow,
    #controls Select.-expanded > SelectCurrent Static#label,
    #controls Select.-expanded > SelectCurrent .arrow,
    #controls Select > SelectCurrent:focus Static#label,
    #controls Select > SelectCurrent:focus .arrow {
        background: transparent;
    }

    #controls Select:focus,
    #controls Select.-expanded,
    #controls Select:focus-within {
        background: #0b0f19;
        background-tint: transparent;
    }

    #controls Select > SelectOverlay {
        background: #0b0f19;
        background-tint: transparent;
        border: round #4338ca;
        border-top: round #4338ca;
        border-bottom: round #4338ca;
    }

    #controls Select > SelectOverlay:focus {
        background: #0b0f19;
        background-tint: transparent;
    }

    #controls Select > SelectOverlay .option-list--option {
        background: #0b0f19;
        background-tint: transparent;
    }

    #controls Select > SelectOverlay .option-list--option-highlighted {
        background: #1e293b;
        background-tint: transparent;
        color: #e0e7ff;
    }

    .gain-volume-row {
        layout: horizontal;
        height: auto;
        min-height: 3;
        align: left middle;
        grid-gutter: 1 0;
        margin-bottom: 0;
        background: transparent;
        border: none;
        padding: 0;
    }

    .gain-volume-row Select {
        width: 1fr;
        min-width: 0;
        padding: 0;
        margin: 0;
        background: transparent;
        background-tint: transparent;
    }

    .gain-volume-row Select:focus,
    .gain-volume-row Select.-expanded,
    .gain-volume-row Select:focus-within {
        background: transparent;
        background-tint: transparent;
    }

    .gain-volume-row Select > SelectCurrent Static#label {
        padding: 0;
        content-align: center middle;
        text-align: center;
    }

    .gain-volume-row Select > SelectCurrent:focus,
    .gain-volume-row Select:focus > SelectCurrent,
    .gain-volume-row Select.-expanded > SelectCurrent {
        border: round #4338ca;
        border-top: round #4338ca;
        border-bottom: round #4338ca;
        background: #0b0f19;
        background-tint: transparent;
    }

    .gain-volume-row Select > SelectCurrent .arrow {
        display: none;
        width: 0;
        min-width: 0;
        padding: 0;
    }

    #sel_preset {
        width: 100%;
    }

    #controls Button {
        width: 100%;
        margin-top: 1;
        background: #0b0f19;
        color: #e9d5ff;
        border: round #7c3aed;
        border-top: round #7c3aed;
        border-bottom: round #7c3aed;
        height: 3;
    }

    #controls Button:hover,
    #controls Button:focus,
    #controls Button.-active,
    #controls Button.-highlight {
        background: #0b0f19;
        background-tint: transparent;
    }

    #controls Button:hover {
        color: #e9d5ff;
        border: round #7c3aed;
        border-top: round #7c3aed;
        border-bottom: round #7c3aed;
    }

    #controls Button.-primary {
        background: #0b0f19;
        color: #a3e635;
        border: round #10b981;
        border-top: round #10b981;
        border-bottom: round #10b981;
    }

    #controls Button.-primary:hover,
    #controls Button.-primary:focus {
        background: #0b0f19;
        color: #a3e635;
        border: round #10b981;
        border-top: round #10b981;
        border-bottom: round #10b981;
    }

    #controls Button.-success {
        background: #0b0f19;
        color: #a3e635;
        border: round #10b981;
        border-top: round #10b981;
        border-bottom: round #10b981;
    }

    #controls Button.-success:hover,
    #controls Button.-success:focus {
        background: #0b0f19;
        color: #a3e635;
        border: round #10b981;
        border-top: round #10b981;
        border-bottom: round #10b981;
    }

    #controls Button.-warning {
        background: #0b0f19;
        color: #fbbf24;
        border: round #f59e0b;
        border-top: round #f59e0b;
        border-bottom: round #f59e0b;
    }

    #controls Button.-warning:hover,
    #controls Button.-warning:focus {
        background: #0b0f19;
        color: #fbbf24;
        border: round #f59e0b;
        border-top: round #f59e0b;
        border-bottom: round #f59e0b;
    }

    #controls Button.-error {
        background: #0b0f19;
        color: #fecaca;
        border: round #dc2626;
        border-top: round #dc2626;
        border-bottom: round #dc2626;
    }

    #controls Button.-error:hover,
    #controls Button.-error:focus {
        background: #0b0f19;
        color: #fecaca;
        border: round #dc2626;
        border-top: round #dc2626;
        border-bottom: round #dc2626;
    }

    #controls #btn_rx,
    #controls #btn_rec,
    #controls #btn_scan {
        margin-top: 0;
        margin-bottom: 0;
    }

    #controls .action-btns {
        layout: vertical;
        height: auto;
        grid-gutter: 0 0;
        margin: 1 0 0 0;
        padding: 0;
    }

    #controls .action-btns Button {
        margin-top: 0;
        margin-bottom: 0;
    }

    #lbl_demod {
        margin-top: 0;
    }

    #lbl_presets {
        margin-top: 1;
    }

    /* ── Matriz 3x3 de modos demod ── */
    .mode-grid {
        layout: grid;
        grid-size: 3 3;
        grid-columns: 1fr 1fr 1fr;
        grid-rows: 3 3 3;
        grid-gutter: 0 1;
        height: 9;
        margin-top: 1;
        margin-bottom: 0;
        min-height: 9;
        background: transparent;
        border: none;
        padding: 0;
    }

    .mode-grid Static {
        width: 100%;
        height: 3;
        padding: 0;
        margin: 0;
        background: #0b0f19;
        color: #a5b4fc;
        border: round #4338ca;
        content-align: center middle;
        text-style: bold;
    }

    .mode-grid Static:hover {
        background: #0b0f19;
        color: #e0e7ff;
        border: round #6366f1;
    }

    .mode-grid Static.active-mode {
        background: #0b0f19;
        color: #a3e635;
        border: round #10b981;
        text-style: bold;
    }

    .mode-grid Static.active-mode:hover {
        background: #0b0f19;
        color: #a3e635;
        border: round #10b981;
    }

    #display_area {
        width: 1fr;
    }

    /* ── Widgets de visualizacion ── */

    FrequencyTimeline {
        height: 3;
        background: #0f172a;
        border-bottom: tall #6366f1;
    }

    SpectrumGraph {
        height: 10;
        background: #090d16;
        border: round #10b981;
    }

    #waterfall_speed_row {
        height: 3;
        min-height: 3;
        max-height: 3;
        width: 100%;
        layout: horizontal;
        background: #090d16;
        border-left: round #6366f1;
        border-right: round #6366f1;
        padding: 0;
        margin: 0;
        grid-gutter: 0 0;
    }

    #waterfall_speed_row Button.spd-btn {
        width: 1fr;
        height: 3;
        min-height: 3;
        max-height: 3;
        min-width: 0;
        margin: 0;
        padding: 0;
        text-style: none;
        text-align: center;
        content-align: center middle;
        box-sizing: border-box;
        background: #090d16;
        border: round #4338ca;
    }

    #waterfall_speed_row Button.spd-btn:hover,
    #waterfall_speed_row Button.spd-btn:focus,
    #waterfall_speed_row Button.spd-btn.-active,
    #waterfall_speed_row Button.spd-btn.-highlight {
        background: #090d16;
        background-tint: transparent;
        border: round #4338ca;
    }

    #waterfall_speed_row Button.spd-a {
        color: #818cf8;
        border: round #4338ca;
    }

    #waterfall_speed_row Button.spd-b {
        color: #c084fc;
        border: round #6d28d9;
    }

    #waterfall_speed_row Button.spd-a:hover,
    #waterfall_speed_row Button.spd-a:focus {
        color: #818cf8;
        border: round #4338ca;
    }

    #waterfall_speed_row Button.spd-b:hover,
    #waterfall_speed_row Button.spd-b:focus {
        color: #c084fc;
        border: round #6d28d9;
    }

    #waterfall_speed_row Button.spd-btn.active-spd,
    #waterfall_speed_row Button.spd-btn.active-spd:hover,
    #waterfall_speed_row Button.spd-btn.active-spd:focus,
    #waterfall_speed_row Button.spd-btn.active-spd.-active,
    #waterfall_speed_row Button.spd-btn.active-spd.-highlight {
        background: #090d16;
        background-tint: transparent;
        color: #a3e635;
        border: round #10b981;
    }

    WaterfallTimeline {
        width: 100%;
        height: 1fr;
        min-height: 0;
        overflow: hidden;
        background: #090d16;
        border: round #6366f1;
    }

    #log_panel {
        width: 100%;
        border: round #38bdf8;
        background: #0f172a;
        height: auto;
        max-height: 5;
        min-height: 1;
        padding: 0 1;
        margin-bottom: 0;
        overflow-x: hidden;
        overflow-y: auto;
        scrollbar-size: 0 0;
        background-tint: transparent;
    }

    #log_panel:focus {
        background: #0f172a;
        background-tint: transparent;
    }

    StatusBar {
        height: 1;
        max-height: 1;
        background: #0f172a;
        color: #e2e8f0;
        overflow: hidden;
        text-wrap: nowrap;
    }

    .sep { color: #374151; }
    """

    BINDINGS = [
        ("left",        "scroll_left",   "Freq -"),
        ("right",       "scroll_right",  "Freq +"),
        ("up",          "step_up",       "Step +"),
        ("down",        "step_down",     "Step -"),
        ("ctrl+left",   "zoom_in",       "Zoom In"),
        ("ctrl+right",  "zoom_out",      "Zoom Out"),
        ("minus",       "zoom_out",      "Zoom -"),
        ("equals",      "zoom_in",       "Zoom +"),
        ("space",       "center_view",   "Centrar"),
        ("s",           "toggle_rx",     "Start/Stop"),
        ("m",           "cycle_mode",    "Modo"),
        ("f",           "focus_freq",    "Freq"),
        ("[",           "passband_narrow", "PASS -"),
        ("]",           "passband_widen",  "PASS +"),
        ("b",           "focus_bandwidth", "BW"),
        ("g",           "focus_gain",    "Gain"),
        ("v",           "focus_volume",  "Volumen"),
        ("shift+up",    "scroll_history_newer", "WF ↑"),
        ("shift+down",  "scroll_history_older", "WF ↓"),
        ("r",           "record",        "Grabar"),
        ("escape",      "show_settings", "Ajustes"),
        ("q",             "quit",          "Salir"),
        ("ctrl+q",        "quit",          "Salir"),
        ("ctrl+c",        "quit",          "Salir"),
    ]

    TITLE = "xyz-sdr -- Terminal SDR Controller"
    SUB_TITLE = "SDRplay RSP1"

    DEMOD_MODES = ["wbfm", "nbfm", "am", "usb", "lsb", "cw", "dsb", "raw", "auto"]
    GAIN_OPTIONS = [0, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60]
    VOLUME_OPTIONS = [0, 10, 20, 30, 40, 50, 60, 70, 75, 80, 90, 100]
    SQUELCH_THRESHOLD_OPTIONS = [5, 10, 12, 15, 18, 20, 25, 30, 35, 40]
    FM_DEEMPHASIS_OPTIONS = [50, 75]

    # ── Inicializacion ───────────────────────────────────────────────────────

    def __init__(
        self,
        driver: str = "sdrplay",
        center_freq: float = 100_600_000,
        gain: float = 40.0,
        volume: float = 75.0,
        demod_mode: str = "wbfm",
        config: dict = None,
        config_path: str = "config/defaults.toml",
        debug_mode: bool = False,
        startup_logs: list[str] | None = None,
        band_profile: str | None = None,
        enumerated_devices: list[dict] | None = None,
        previous_session_marker: dict | None = None,
        strict: bool = False,
        ai_enabled: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._startup_logs: list[str] = list(startup_logs or [])
        self._previous_session_marker: dict | None = previous_session_marker
        self.driver = driver
        self.demod_mode = demod_mode
        self.config = config or {}
        self.config_path = config_path
        self.debug_mode = debug_mode
        self.band_profile = band_profile
        self.strict = strict
        # AI: opt-in vía CLI (--ai) o [ai] del config. Combinado en ai.is_enabled().
        self.ai_enabled = ai_enabled
        self._project_root = Path(config_path).resolve().parent.parent
        # ScannerEngine: la lógica de escaneo vive ahora en core/scanner.py.
        # XyzSDRApp implementa ScannerHost vía propiedades y métodos.
        from core.scanner import ScannerEngine
        self._scanner = ScannerEngine(self)
        self._device: Optional[SDRDevice] = None
        self._hardware_ready = False
        self._pending_band_profile: str | None = None
        self._cached_sdr_devices: list[dict] = list(enumerated_devices or [])
        self._rx_warmup_iters_left = 0
        self._rx_active = False
        self._recording = False
        self._recorder: Optional[SDRRecorder] = None
        # scanning/paused: propiedades delegadas a ScannerEngine (no asignar aquí)
        self._scan_pause_below_since = 0.0
        self._scan_tuned_time = 0.0
        self._scan_last_signal_time = 0.0
        self._squelch_open = True
        self._audio_output: Optional[AudioOutputQueue] = None
        self._audio_started = False
        self._sdrplay_preflight_done = False
        self._sdrplay_preflight_ok = False
        self._sdrplay_rx_blocked = False
        self._sdrplay_rx_blocked_notified = False
        self.audio_effects = AudioEffects()
        # StorageController: grabación, bookmarks y persistencia de config
        # viven ahora en tui/storage.py. XyzSDRApp implementa StorageHost
        # vía propiedades y métodos delegantes.
        from tui.storage import StorageController
        self._storage = StorageController(self, self.audio_effects, PRESETS)

        # ── Estado del viewport ──
        self.tuned_frequency: float = float(center_freq)
        self.viewport_center: float = float(center_freq)
        dsp_cfg_init = self.config.get("dsp", {})
        self.passband_center_hz: float = float(center_freq)
        self.passband_width_hz: float = self._load_passband_width_for_mode(
            demod_mode, dsp_cfg_init
        )
        self._passband_preview_width: float | None = None
        self._passband_preview_sync_at: float = 0.0
        self.fm_deemphasis_us: float = float(dsp_cfg_init.get("fm_deemphasis_us", 50))
        self.fm_agc_enabled: bool = bool(dsp_cfg_init.get("fm_agc_enabled", True))
        initial_rate = float(self.config.get("device", {}).get("sample_rate", 2_048_000))
        self.sample_rate: float = initial_rate
        self.visible_spans: list[float] = build_visible_spans(initial_rate)
        self.visible_span: float = float(self.visible_spans[-1])
        self.scroll_step: float = float(SCROLL_STEPS[DEFAULT_STEP_INDEX])
        self.step_index: int = DEFAULT_STEP_INDEX
        self.zoom_index: int = len(self.visible_spans) - 1
        self.gain_value: float = float(gain)
        self.volume_value: float = float(volume)
        self._last_snr: float = 0.0
        self._graceful_shutdown = False
        self._shutting_down = False
        self._bandwidth_changing = False
        self._driver_changing = False
        self._rx_stop_event = threading.Event()
        self._rx_stop_event.set()
        self._display_width: int = 120
        self._band_mailbox = BandFrameMailbox()
        self._display_sequence: int = 0
        self._rx_worker_token: int = 0

        # Instrumentación --debug
        self._debug_lock = threading.Lock()
        self._debug_rx_proc_ms: list[float] = []
        self._debug_rx_iter_count: int = 0
        self._debug_display_frames: int = 0
        self._debug_ui_proc_ms: list[float] = []
        self._debug_frame_latency_ms: list[float] = []
        self._debug_last_viewport_ms: float = 0.0
        self._debug_chunk_samples: list[int] = []
        self._debug_chunk_duration_ms: list[float] = []
        self._debug_demod_ms: list[float] = []
        self._debug_audio_samples: list[int] = []
        self._debug_report_window_start: float = time.time()
        self._stream_stats_snapshot = StreamStats()
        self._viewport_debounce_timer = None
        self._status_last_update: float = 0.0

        dsp_cfg = self.config.get("dsp", {})
        self.squelch_enabled = bool(dsp_cfg.get("squelch_enabled", False))
        raw_squelch = dsp_cfg.get("squelch_threshold", dsp_cfg.get("squelch_db", 15))
        squelch_int = int(float(raw_squelch))
        if squelch_int not in self.SQUELCH_THRESHOLD_OPTIONS or squelch_int < 0:
            squelch_int = 15
        self.squelch_threshold = float(squelch_int)
        self.squelch_hang_ms = float(dsp_cfg.get("squelch_hang_ms", 500))
        self._squelch_gate = SquelchGate(
            threshold_db=self.squelch_threshold,
            hang_ms=self.squelch_hang_ms,
        )
        audio_rate = float(dsp_cfg.get("audio_rate", 48_000))
        self._audio_rate = int(audio_rate)
        self._fm_agc = AudioAgc()
        self._fm_agc_sample_rate = audio_rate
        self._fm_demod_state = FmDemodState()

        rec_cfg = self.config.get("recorder", {})
        self._bookmarks = self._storage.bookmarks  # alias legacy (StorageController es owner)
        # Legacy state — StorageController es el owner real; estos atributos
        # se mantienen por compatibilidad con código externo que los lee.
        self._recordings_dir: Path | None = None
        self._recorder: object | None = None

        display_cfg_init = self.config.get("display", {})
        self.waterfall_auto_level = bool(display_cfg_init.get("waterfall_auto_level", True))
        self.display_level_mode = str(display_cfg_init.get("display_level_mode", "per_column"))
        self._tracker_viewport_span: float | None = None
        self._level_tracker = ColumnLevelTracker(
            width=max(self._display_width, 1),
            floor_pct=float(display_cfg_init.get("column_floor_pct", 10)),
            ceiling_pct=float(display_cfg_init.get("column_ceiling_pct", 99)),
            min_range_db=float(display_cfg_init.get("waterfall_min_range_db", 6.0)),
            attack=float(display_cfg_init.get("column_ema_attack", 0.35)),
            release=float(display_cfg_init.get("column_ema_release", 0.08)),
            smooth_bins=int(display_cfg_init.get("column_smooth_bins", 3)),
            history_rows=int(display_cfg_init.get("column_history_rows", 32)),
        )
        span_ratio = self.visible_span / max(self.sample_rate, 1.0)
        self._level_tracker.set_span_ratio(span_ratio)

    def _load_passband_width_for_mode(self, mode: str, dsp_cfg: dict | None = None) -> float:
        cfg = dsp_cfg or self.config.get("dsp", {})
        key_map = {
            "wbfm": "wbfm_bandwidth",
            "nbfm": "nbfm_bandwidth",
            "am": "am_bandwidth",
        }
        key = key_map.get(mode)
        if key and key in cfg:
            return float(cfg[key])
        return default_passband_width(mode)

    def _sync_passband_widgets(self) -> None:
        preview = self._passband_preview_width
        try:
            timeline = self.query_one("#timeline", FrequencyTimeline)
            timeline.passband_center_hz = self.passband_center_hz
            timeline.passband_width_hz = self.passband_width_hz
            timeline.passband_preview_width_hz = preview
        except Exception:
            pass
        try:
            spectrum = self.query_one("#spectrum", SpectrumGraph)
            spectrum.passband_center_hz = self.passband_center_hz
            spectrum.passband_width_hz = self.passband_width_hz
            spectrum.passband_preview_width_hz = preview
        except Exception:
            pass
        try:
            waterfall = self.query_one("#waterfall", WaterfallTimeline)
            waterfall.passband_center_hz = self.passband_center_hz
            waterfall.passband_width_hz = self.passband_width_hz
            waterfall.passband_preview_width_hz = preview
            waterfall.waterfall_auto_level = self.waterfall_auto_level
        except Exception:
            pass

    def _persist_display_config(self, *, waterfall_auto_level: bool | None = None) -> None:
        """DEPRECATED: usa _storage.persist_config('display', ...)."""
        self._persist_config(
            "display",
            waterfall_auto_level=waterfall_auto_level,
        )

    def _persist_passband_width(self) -> None:
        mode = self._passband_mode()
        kwargs: dict = {}
        if mode == "wbfm":
            kwargs["wbfm_bandwidth"] = self.passband_width_hz
        elif mode == "nbfm":
            kwargs["nbfm_bandwidth"] = self.passband_width_hz
        elif mode == "am":
            kwargs["am_bandwidth"] = self.passband_width_hz
        if kwargs:
            self._storage.persist_config("dsp", **kwargs)

    def _passband_mode(self) -> str:
        """Modo usado para límites PASS (resuelve AUTO)."""
        if self.demod_mode == "auto":
            return self.active_demod_mode
        return self.demod_mode

    def _apply_passband_selection(self, center_hz: float, width_hz: float) -> None:
        center_hz = max(FREQ_MIN_HZ, min(FREQ_MAX_HZ, float(center_hz)))
        pb_mode = self._passband_mode()
        if width_hz <= 0:
            width_hz = self._load_passband_width_for_mode(pb_mode)
        width_hz = clamp_passband_width(pb_mode, width_hz)

        self.passband_center_hz = center_hz
        self.passband_width_hz = width_hz
        self.tuned_frequency = center_hz
        self._passband_preview_width = None

        self._apply_tuning()
        self._sync_passband_widgets()
        self._persist_passband_width()
        self._log(
            f"Banda: {center_hz / 1e6:.4f} MHz | {_format_hz(width_hz)}"
        )

    def _adjust_passband_width(self, delta_hz: float) -> None:
        pb_mode = self._passband_mode()
        if pb_mode not in PASSBAND_KEYBOARD_STEP:
            return
        new_width = clamp_passband_width(
            pb_mode,
            self.passband_width_hz + delta_hz,
        )
        if abs(new_width - self.passband_width_hz) < 1.0:
            return
        self.passband_width_hz = new_width
        self._sync_passband_widgets()
        self._persist_passband_width()
        self._update_status()
        self._log(f"Ancho audible: {_format_hz(new_width)}")

    def _closest_preset_rate(self, rate_hz: float, rates: list[float] | None = None) -> float:
        """Elige el preset de bandwidth más cercano a rate_hz."""
        candidates = rates or list(BANDWIDTH_PRESETS)
        if not candidates:
            return rate_hz
        return min(candidates, key=lambda candidate: abs(candidate - rate_hz))

    def _refresh_bandwidth_select(self) -> None:
        """Actualiza opciones y valor del selector según el dispositivo."""
        if not self._device:
            return
        try:
            rates = self._device.get_supported_sample_rates()
            select = self.query_one("#sel_bandwidth", Select)
            select.set_options(bandwidth_select_options(rates))
            select.value = self._closest_preset_rate(self.sample_rate, rates)
        except Exception:
            pass

    def _sync_bandwidth_select_value(self) -> None:
        """Revierte el selector al bandwidth activo (p. ej. tras error)."""
        if not self._device:
            return
        try:
            rates = self._device.get_supported_sample_rates()
            self.query_one("#sel_bandwidth", Select).value = self._closest_preset_rate(
                self.sample_rate, rates
            )
        except Exception:
            pass

    # ── Layout ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        display_cfg = self.config.get("display", {})
        waterfall_max_history = int(display_cfg.get("waterfall_history", 100))
        waterfall_buffer_ratio = float(display_cfg.get("waterfall_history_buffer_ratio", 2 / 3))
        waterfall_auto_level = bool(display_cfg.get("waterfall_auto_level", True))
        waterfall_level_low_pct = float(display_cfg.get("waterfall_level_low_pct", 5))
        waterfall_level_high_pct = float(display_cfg.get("waterfall_level_high_pct", 99))
        waterfall_min_range_db = float(display_cfg.get("waterfall_min_range_db", 6.0))

        yield Header()

        with Horizontal(id="main_area"):
            # Panel izquierdo — controles
            with Vertical(id="controls"):
                yield Label("-- FRECUENCIA (MHz) --")
                yield Input(
                    value=f"{self.tuned_frequency / 1e6:.4f}",
                    placeholder="MHz",
                    id="inp_freq",
                )

                yield Label("-- BANDWIDTH --")
                yield Select(
                    bandwidth_select_options(list(BANDWIDTH_PRESETS)),
                    value=self._closest_preset_rate(self.sample_rate),
                    id="sel_bandwidth",
                )

                yield Label("[ Ganancia (dB) - Volumen ]")
                with Horizontal(classes="gain-volume-row"):
                    yield Select(
                        [(f"{g}", g) for g in self.GAIN_OPTIONS],
                        value=int(self.gain_value) if int(self.gain_value) in self.GAIN_OPTIONS else self.GAIN_OPTIONS[-1],
                        id="sel_gain",
                    )
                    yield Select(
                        [(f"{v}", v) for v in self.VOLUME_OPTIONS],
                        value=int(self.volume_value) if int(self.volume_value) in self.VOLUME_OPTIONS else 75,
                        id="sel_volume",
                    )

                yield Label("-- MODO DEMOD --", id="lbl_demod")
                with Container(classes="mode-grid"):
                    for m in self.DEMOD_MODES:
                        yield Static(m.upper(), id=f"btn_mode_{m}")

                with VerticalGroup(classes="action-btns"):
                    yield Button(">> INICIAR RX", id="btn_rx", variant="success", classes="-textual-compact")
                    yield Button("(o) GRABAR IQ", id="btn_rec", variant="warning", classes="-textual-compact")
                    yield Button("🔍 ESCANEAR BANDA", id="btn_scan", variant="primary", classes="-textual-compact")

                yield Label("-- PRESETS --", id="lbl_presets")
                yield Select(
                    [(name, f"{freq}:{mode}") for name, freq, mode in self._storage.bookmarks],
                    prompt="Emisora...",
                    id="sel_preset",
                )
                yield Button("📌 Guardar Bookmark", id="btn_save_bookmark", classes="-textual-compact")

                band_profiles = list_band_profiles()
                if band_profiles:
                    yield Label("-- BANDA --", id="lbl_band_profiles")
                    band_options = [(label, profile_id) for profile_id, label in band_profiles]
                    band_select_kwargs: dict = {
                        "prompt": "Perfil de banda...",
                        "id": "sel_band",
                    }
                    if self.band_profile and self.band_profile in dict(band_options):
                        band_select_kwargs["value"] = self.band_profile
                    yield Select(band_options, **band_select_kwargs)

            # Panel derecho — visualizacion
            with Vertical(id="display_area"):
                yield FrequencyTimeline(id="timeline")
                yield SpectrumGraph(id="spectrum")
                with Horizontal(id="waterfall_speed_row"):
                    for i, spd in enumerate(WATERFALL_SPEEDS):
                        yield Button(
                            str(spd),
                            id=f"btn_spd_{spd}",
                            classes=f"spd-btn spd-{'a' if i % 2 == 0 else 'b'}",
                        )
                yield WaterfallTimeline(
                    id="waterfall",
                    max_history=waterfall_max_history,
                    history_buffer_ratio=waterfall_buffer_ratio,
                    waterfall_auto_level=waterfall_auto_level,
                    level_low_pct=waterfall_level_low_pct,
                    level_high_pct=waterfall_level_high_pct,
                    min_range_db=waterfall_min_range_db,
                )
                yield Log(id="log_panel", max_lines=200)

        yield StatusBar(id="status")

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._device = None

        self._sync_viewport(immediate=True)
        self._sync_passband_widgets()
        self._update_mode_ui()
        self._set_waterfall_speed(10)

        log = self.query_one("#log_panel", Log)
        for line in self._startup_logs:
            if line.strip():
                log.write_line(f"[BOOT] {line}")
        log.write_line("[INFO] Abriendo dispositivo SDR...")

        self._update_status()
        self.call_after_refresh(self._update_display_width)

        display_fps = float(self.config.get("dsp", {}).get("display_fps", 20))
        self.set_interval(1.0 / max(1.0, display_fps), self._flush_display_frames)
        if self.debug_mode:
            self.set_interval(3.0, self._report_debug_metrics)

        self._init_hardware_async()

    @work(thread=True)
    def _init_hardware_async(self) -> None:
        """Abre el SDR en segundo plano para no bloquear el primer frame de Textual.

        Cuando ``self.strict`` es True, NO se hace fallback a simulated en caso de
        error; se propaga la excepción al hilo principal vía _on_hardware_ready.
        """
        from core.session_log import log_breadcrumb

        log_breadcrumb(f"hardware.init start driver={self.driver!r}")
        preflight_msg: str | None = None
        skip_pf = os.environ.get("XYZ_SDR_SKIP_SDRPLAY_PREFLIGHT", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if self.driver == "sdrplay" and not skip_pf:
            from core.sdrplay_enumerate import recover_sdrplay_enumeration
            from core.sdrplay_preflight import (
                apply_preflight_strategy,
                per_path_timeout,
                preflight_user_message,
                resolve_preflight_timeout,
                run_preflight,
            )
            from core.sdrplay_service import restart_sdrplay_service

            has_cached_sdrplay = any(
                str(dev.get("driver", "")).lower() == "sdrplay"
                for dev in (self._cached_sdr_devices or [])
            )
            if not has_cached_sdrplay:
                recover_sdrplay_enumeration(restart_if_missing=True, log=log_breadcrumb)

            # Arranque TUI: solo minimal (CS16→CF32) para no bloquear ~2 min
            startup_timeout = min(resolve_preflight_timeout(), 50.0)
            per = per_path_timeout(startup_timeout)
            result = run_preflight("minimal", per_path_timeout_s=per, stream_format="CS16")
            if not result.ok:
                result = run_preflight("minimal", per_path_timeout_s=per, stream_format="CF32")
            if result.segfault:
                restart_sdrplay_service()
                result = run_preflight("minimal", per_path_timeout_s=per, stream_format="CS16")
                if not result.ok:
                    result = run_preflight(
                        "minimal", per_path_timeout_s=per, stream_format="CF32"
                    )
            self._sdrplay_preflight_done = True
            self._sdrplay_preflight_ok = result.ok
            if result.ok:
                apply_preflight_strategy(result)
                log_breadcrumb(
                    f"hardware.preflight ok path={result.path} fmt={result.stream_format}"
                )
            elif self.strict:
                preflight_msg = preflight_user_message(result)
                log_breadcrumb(
                    f"hardware.preflight FAIL strict step={result.last_step}"
                )
                self.call_from_thread(
                    self._on_hardware_complete,
                    (None, f"[STRICT] {preflight_msg or result.detail}", False),
                )
                return
            else:
                preflight_msg = preflight_user_message(result)
                log_breadcrumb(
                    f"hardware.preflight FAIL segfault={result.segfault} step={result.last_step}"
                )
                device = SDRDevice(driver="simulated")
                device.open()
                self.call_from_thread(
                    self._on_hardware_complete,
                    (device, preflight_msg or "SDRplay preflight RX failed", True),
                )
                return

        device = SDRDevice(driver=self.driver)
        hw_open_error: str | None = None
        used_fallback = False
        try:
            device.open()
        except HardwareInitializationError as exc:
            hw_open_error = str(exc)
            log_breadcrumb(f"hardware.init FAIL: {exc}")
            if self.strict:
                # --strict: propagar el error sin fallback a simulated
                self.call_from_thread(
                    self._on_hardware_ready,
                    None,
                    f"[STRICT] {exc}",
                )
                return
            # Fallback silencioso a simulated (modo por defecto)
            device = SDRDevice(driver="simulated")
            device.open()
            used_fallback = True
        else:
            log_breadcrumb(f"hardware.init ok simulated={device.is_simulated}")

        # Una sola llamada: entrega resultado consolidado al main thread.
        self.call_from_thread(
            self._on_hardware_complete,
            (device, hw_open_error, used_fallback),
        )

    def _apply_simulated_fallback(self) -> None:
        """DEPRECATED: la lógica está consolidada en _on_hardware_complete."""
        self.driver = "simulated"

    def _on_hardware_complete(
        self,
        payload: tuple[SDRDevice | None, str | None, bool],
    ) -> None:
        """Callback unificado desde _init_hardware_async.

        Args:
            payload: tupla ``(device, hw_open_error, used_fallback)``.
                - ``device``: el SDRDevice ya abierto (o None en --strict fail).
                - ``hw_open_error``: mensaje de error si lo hubo.
                - ``used_fallback``: True si se cayó a simulated.
        """
        device, hw_open_error, used_fallback = payload
        
        # Sincronizar el resultado del preflight asíncrono al hilo de la TUI
        if device is not None and not device.is_simulated and device.driver == "sdrplay":
            # Si el arranque completó con éxito, se preserva el estado del preflight
            self._sdrplay_preflight_done = True
            self._sdrplay_preflight_ok = not used_fallback

        if used_fallback:
            self.driver = "simulated"
        if device is None:
            # --strict y falló la apertura: notificar y dejar la app en estado error
            self._log(f"[FATAL] --strict: {hw_open_error}")
            return
        # Reusar la lógica existente
        self._on_hardware_ready(device, hw_open_error)

    def _on_hardware_ready(
        self,
        device: SDRDevice,
        hw_open_error: str | None,
    ) -> None:
        self._device = device
        self._sync_simulated_device_state()
        self._device.set_frequency(self.tuned_frequency)
        self._device.set_gain(self.gain_value)
        self.sample_rate = self._device.sample_rate

        cfg_rate = self.config.get("device", {}).get("sample_rate")
        if cfg_rate is not None:
            cfg_rate = float(cfg_rate)
            if abs(cfg_rate - self.sample_rate) > 1.0:
                if self._device.is_sample_rate_supported(cfg_rate):
                    if not self.change_bandwidth(cfg_rate):
                        self._log(
                            f"[WARN] Bandwidth objetivo {_format_bandwidth_hz(cfg_rate)} no aplicado; "
                            f"usando {_format_bandwidth_hz(self.sample_rate)}"
                        )
                else:
                    self._log(
                        f"[WARN] Bandwidth {_format_bandwidth_hz(cfg_rate)} no soportado; "
                        f"usando {_format_bandwidth_hz(self.sample_rate)}"
                    )
                    self._rebuild_zoom_levels()
                    self._adapt_viewport_to_bandwidth()
            else:
                self._rebuild_zoom_levels()
                self._adapt_viewport_to_bandwidth()
        else:
            self._rebuild_zoom_levels()
            self._adapt_viewport_to_bandwidth()

        self._refresh_bandwidth_select()

        device_label = "SIMULACION" if self._device.is_simulated else self.driver.upper()
        self.sub_title = f"{device_label} | {self.tuned_frequency / 1e6:.3f} MHz"

        log = self.query_one("#log_panel", Log)
        if hw_open_error:
            log.write_line(f"[ERR]  Hardware no disponible: {hw_open_error}")
            log.write_line("[WARN] Modo SIMULACION activado")
            if (
                not self._device.is_simulated
                and self._sdrplay_preflight_done
                and not self._sdrplay_preflight_ok
                and self.driver == "sdrplay"
            ):
                self._sdrplay_rx_blocked = True
                log.write_line(
                    "[BLOCK] RX SDRplay REAL bloqueado — segfault en SoapySDRPlay3 al abrir stream"
                )
                log.write_line(
                    "[INFO] RX en SIMULACION disponible (IQ sintetico) para probar UI y controles"
                )
                log.write_line(
                    "[INFO] Evidencia: .\\scripts\\sdrplay_stream_matrix.ps1 -EnableWer "
                    "-SingleRow minimal,CF32"
                )
                log.write_line("[INFO] Diagnostico: .\\scripts\\diagnose_sdrplay.ps1 --no-probe")
            elif "sdrplay" in hw_open_error.lower():
                log.write_line("[INFO] SDRplay: SoapySDRUtil --find=driver=sdrplay debe listar tu RSP")
                log.write_line("[INFO] Cierra SDRuno, verifica SDRplayAPIService, .\\setup\\install_drivers.ps1")
            else:
                log.write_line("[INFO] Para restaurar RX real: cierra otras apps SDR y reinicia la app")
        elif self._device.is_simulated:
            log.write_line("[WARN] Hardware no detectado -- Modo SIMULACION activado")
            log.write_line("[INFO] Para usar hardware real instala PothosSDR + SDRplay API")
        else:
            log.write_line(f"[OK]   Dispositivo abierto: driver={self.driver}")
            if self.driver == "sdrplay" and not self._device.is_simulated:
                log.write_line(
                    "[INFO] SDRplay: preflight OK — frecuencia/BW al pulsar INICIAR RX "
                    "(formato vía XYZ_SDR_SDRPLAY_STREAM_FORMAT)"
                )

        log.write_line("[INFO] Pulsa [S] o el boton para iniciar recepcion")
        log.write_line(f"[INFO] Controles: <-/-> scroll | up/dn step | ctrl+<-/-> zoom | B bandwidth | [ ] ancho PASS")
        log.write_line("[INFO] Ratón: clic+arrastre en timeline/espectro = banda audible simétrica")
        if self.debug_mode:
            log.write_line("[DEBUG] Instrumentación activa (FPS/latencia en panel cada ~3s con RX)")
        self._hardware_ready = True
        pending = self._pending_band_profile
        self._pending_band_profile = None
        if pending:
            self._apply_band_profile(pending)
        self._update_status()

    def _invalidate_band_cache(self) -> None:
        """Limpia caché espectral al cambiar bandwidth o reiniciar RX."""
        self._band_mailbox.clear()
        self._display_sequence = 0
        try:
            self.query_one("#spectrum", SpectrumGraph).clear()
        except Exception:
            pass
        try:
            self.query_one("#waterfall", WaterfallTimeline).clear_history()
        except Exception:
            pass

    def _resolve_band_profile_id(self, value: str) -> str | None:
        """Normaliza id o etiqueta del Select de perfiles de banda."""
        raw = str(value).strip()
        if not raw:
            return None
        profiles = list_band_profiles()
        by_id = {profile_id: label for profile_id, label in profiles}
        if raw in by_id:
            return raw
        for profile_id, label in profiles:
            if raw == label:
                return profile_id
        return raw

    def _apply_band_profile(self, profile_id: str) -> None:
        """Aplica un perfil TOML de config/bands/ (frecuencia, modo, BW IQ, display)."""
        resolved = self._resolve_band_profile_id(profile_id)
        if not resolved:
            return
        if not self._hardware_ready:
            self._pending_band_profile = resolved
            return
        try:
            profile = load_band_profile(resolved)
        except FileNotFoundError as exc:
            self._log(f"[ERROR] {exc}")
            self.audio_effects.play_error()
            return

        self.config = merge_configs(self.config, profile)
        self.band_profile = resolved
        dev = profile.get("device", {})
        dsp = profile.get("dsp", {})
        display = profile.get("display", {})

        if "center_freq" in dev:
            freq = float(dev["center_freq"])
            self.tuned_frequency = freq
            self.viewport_center = freq
            self.passband_center_hz = freq

        if "gain" in dev:
            self.gain_value = float(dev["gain"])
            if self._device:
                self._device.set_gain(self.gain_value)

        if "demod_mode" in dsp:
            self.demod_mode = str(dsp["demod_mode"])
            self.passband_width_hz = self._load_passband_width_for_mode(self.demod_mode, dsp)
            self._update_mode_ui()

        if "volume" in dsp:
            self.volume_value = float(dsp["volume"])

        if dsp.get("squelch_enabled") is not None:
            self.squelch_enabled = bool(dsp["squelch_enabled"])
        if "squelch_threshold" in dsp:
            val = int(float(dsp["squelch_threshold"]))
            if val in self.SQUELCH_THRESHOLD_OPTIONS:
                self.squelch_threshold = float(val)

        if display.get("display_level_mode"):
            self.display_level_mode = str(display["display_level_mode"])

        if "freq_span_mhz" in display:
            span_hz = float(display["freq_span_mhz"]) * 1_000_000
            if 0 < span_hz <= self.sample_rate:
                self.visible_span = span_hz
                self.zoom_index = find_zoom_index(span_hz, self.visible_spans)

        rate = float(dev.get("sample_rate", self.sample_rate))
        if abs(rate - self.sample_rate) > 1.0:
            self.change_bandwidth(rate)

        if self._device:
            self._device.set_frequency(self.tuned_frequency)

        self._apply_tuning()
        self._sync_bandwidth_select_value()
        self._sync_passband_widgets()
        self._update_status()
        try:
            persist_band_profile(self.config_path, resolved, profile)
        except Exception as exc:
            logger.warning("No se pudo persistir perfil de banda: %s", exc)
        self._log(f"[BAND] Perfil {resolved} aplicado (guardado en {self.config_path})")
        self.audio_effects.play_chime()

    def _compute_column_levels(
        self,
        cols: np.ndarray,
        display_cfg: dict,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Calcula suelo/techo por columna (per-column o global)."""
        width = len(cols)
        min_range_db = float(display_cfg.get("waterfall_min_range_db", 6.0))
        low_pct = float(display_cfg.get("waterfall_level_low_pct", 5))
        high_pct = float(display_cfg.get("waterfall_level_high_pct", 99))

        if not self.waterfall_auto_level:
            return np.full(width, -80.0), np.full(width, -20.0)

        if self.display_level_mode == "per_column":
            if self._level_tracker.width != width:
                self._level_tracker.reconfigure(width, reset=True)
            self._level_tracker.push_viewport_row(cols)
            self._level_tracker.update(cols)
            return self._level_tracker.floors, self._level_tracker.ceilings

        level_min, level_max = compute_auto_levels(
            cols,
            low_pct=low_pct,
            high_pct=high_pct,
            min_range_db=min_range_db,
        )
        return np.full(width, level_min), np.full(width, level_max)

    def _flush_display_frames(self) -> None:
        """Coalescing: aplica el frame más reciente al espectro y waterfall."""
        if not self._rx_active:
            return

        try:
            frame, snr, seq = self._band_mailbox.consume_if_new(self._display_sequence)
        except Exception as exc:
            logger.exception("Error leyendo frame espectral: %s", exc)
            return

        if frame is None:
            return

        try:
            self._apply_display_frame(frame, snr, seq)
        except Exception as exc:
            logger.exception("Error actualizando espectro/cascada: %s", exc)

    def _apply_display_frame(self, frame, snr: float, seq: int) -> None:
        """Renderiza un frame en widgets de visualización (hilo principal)."""

        self._display_sequence = seq
        self._last_snr = snr

        ui_t0 = time.perf_counter()
        display_cfg = self.config.get("display", {})
        cols = slice_band_to_viewport(
            frame.band_cols,
            frame.center_hz,
            frame.sample_rate,
            self.viewport_center,
            self.visible_span,
            self._display_width,
        )

        floors, ceilings = self._compute_column_levels(cols, display_cfg)

        if self._scanner.scanning:
            self._handle_scanner_step(frame, snr, floors, ceilings)

        try:
            spectrum = self.query_one("#spectrum", SpectrumGraph)
            spectrum.set_column_levels(floors, ceilings)
            spectrum.set_band_frame(frame, force=True)
        except Exception:
            pass

        try:
            waterfall = self.query_one("#waterfall", WaterfallTimeline)
            waterfall.set_column_levels(floors, ceilings)
            waterfall.add_band_row(frame)
        except Exception as exc:
            logger.exception("Error actualizando waterfall: %s", exc)

        now = time.time()
        if now - self._status_last_update >= 0.2:
            self._update_status()
            self._status_last_update = now

        if self.debug_mode:
            ui_ms = (time.perf_counter() - ui_t0) * 1000.0
            latency_ms = max(0.0, (time.time() - frame.timestamp) * 1000.0)
            with self._debug_lock:
                self._debug_display_frames += 1
                self._debug_ui_proc_ms.append(ui_ms)
                self._debug_frame_latency_ms.append(latency_ms)
                if len(self._debug_ui_proc_ms) > 120:
                    self._debug_ui_proc_ms.pop(0)
                if len(self._debug_frame_latency_ms) > 120:
                    self._debug_frame_latency_ms.pop(0)

    def _report_debug_metrics(self) -> None:
        """Escribe métricas de rendimiento en el panel de log (--debug)."""
        if not self.debug_mode:
            return

        now = time.time()
        window_s = max(now - self._debug_report_window_start, 0.001)

        with self._debug_lock:
            rx_iters = self._debug_rx_iter_count
            rx_proc = list(self._debug_rx_proc_ms)
            ui_frames = self._debug_display_frames
            ui_proc = list(self._debug_ui_proc_ms)
            latencies = list(self._debug_frame_latency_ms)
            viewport_ms = self._debug_last_viewport_ms
            chunk_samples = list(self._debug_chunk_samples)
            chunk_ms = list(self._debug_chunk_duration_ms)
            demod_ms = list(self._debug_demod_ms)
            audio_out = list(self._debug_audio_samples)
            underruns = 0
            dropped = 0
            if self._audio_output:
                underruns = self._audio_output.underrun_count
                dropped = self._audio_output.dropped_chunks

            self._debug_rx_iter_count = 0
            self._debug_display_frames = 0
            self._debug_chunk_samples.clear()
            self._debug_chunk_duration_ms.clear()
            self._debug_demod_ms.clear()
            self._debug_audio_samples.clear()
            self._debug_report_window_start = now

        if not self._rx_active:
            return

        rx_rate = rx_iters / window_s
        ui_fps = ui_frames / window_s

        parts = [f"[DEBUG] perf {window_s:.1f}s"]
        if rx_iters:
            avg_rx = sum(rx_proc) / len(rx_proc) if rx_proc else 0.0
            p95_rx = float(np.percentile(rx_proc, 95)) if rx_proc else 0.0
            parts.append(f"RX {rx_rate:.1f} iter/s proc {avg_rx:.1f}ms p95 {p95_rx:.1f}ms")
        if ui_frames:
            avg_ui = sum(ui_proc) / len(ui_proc) if ui_proc else 0.0
            avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
            p95_lat = float(np.percentile(latencies, 95)) if latencies else 0.0
            parts.append(f"UI {ui_fps:.1f} fps draw {avg_ui:.1f}ms lat {avg_lat:.0f}ms p95 {p95_lat:.0f}ms")
        if viewport_ms > 0:
            parts.append(f"viewport {viewport_ms:.1f}ms")
        if chunk_samples:
            avg_chunk = int(sum(chunk_samples) / len(chunk_samples))
            avg_dur = sum(chunk_ms) / len(chunk_ms) if chunk_ms else 0.0
            parts.append(f"iq {avg_chunk} smp {avg_dur:.0f}ms")
        if demod_ms:
            avg_demod = sum(demod_ms) / len(demod_ms)
            parts.append(f"demod {avg_demod:.1f}ms")
        if audio_out:
            avg_audio = int(sum(audio_out) / len(audio_out))
            parts.append(f"audio {avg_audio} smp/iter")
        if underruns or dropped:
            parts.append(f"audio u/d {underruns}/{dropped}")

        if self._device and not self._device.is_simulated:
            current_stats = self._device.stream_stats
            stream_delta = StreamStats.delta(self._stream_stats_snapshot, current_stats)
            self._stream_stats_snapshot = current_stats
            if stream_delta.samples_requested:
                parts.append(
                    f"iq drop {stream_delta.drop_rate * 100:.1f}%"
                    f" ov {stream_delta.overflows} to {stream_delta.timeouts}"
                )

        if len(parts) > 1:
            self._log(" | ".join(parts))

    def on_resize(self, event: events.Resize) -> None:
        self._update_display_width()

    def _update_display_width(self) -> None:
        """Ancho de referencia compartido espectro/waterfall."""
        try:
            spectrum = self.query_one("#spectrum", SpectrumGraph)
            waterfall = self.query_one("#waterfall", WaterfallTimeline)
            width = plot_content_width(spectrum)
            if width > 0:
                if width != self._display_width:
                    self._level_tracker.reconfigure(width)
                self._display_width = width
                spectrum.set_frequency_columns(width)
                waterfall.set_frequency_columns(width)
                spectrum.set_viewport(self.viewport_center, self.visible_span)
                waterfall.set_viewport(self.viewport_center, self.visible_span)
        except Exception:
            pass

    def on_unmount(self) -> None:
        if not self._shutting_down:
            if self._rx_active:
                self._abort_rx_worker()
            elif self._audio_output:
                self._audio_output.stop()
                self._audio_output = None
        if self._device:
            self._device.close()
        self._restore_console()

    def _prepare_for_exit(self) -> None:
        """Detiene RX/audio y timers antes de que Textual desmonte la app."""
        if self._shutting_down:
            return
        self._shutting_down = True

        if self._viewport_debounce_timer is not None:
            try:
                self._viewport_debounce_timer.stop()
            except Exception:
                pass
            self._viewport_debounce_timer = None

        self._abort_rx_worker()
        if self._audio_output:
            try:
                self._audio_output.stop()
            except Exception:
                pass
            self._audio_output = None

    def _abort_rx_worker(self) -> None:
        """Detiene RX sin bloquear la TUI (cancela I/O Soapy pendiente)."""
        self._rx_active = False
        self._rx_worker_token += 1
        try:
            from core.sdr_io import shutdown_sdr_io

            shutdown_sdr_io()
        except Exception:
            pass
        if not self._rx_stop_event.wait(timeout=0.75):
            self._rx_stop_event.set()
        try:
            btn = self.query_one("#btn_rx", Button)
            btn.label = ">> INICIAR RX"
            btn.variant = "success"
        except Exception:
            pass

    def _recover_sdrplay_service_for_rx(self, *, from_worker: bool = False) -> bool:
        """Reinicia SDRplay API si el servicio no responde antes de activateStream."""
        if not self._device or self._device.is_simulated or self._device.driver != "sdrplay":
            return True
        from core.soapy_runtime import is_sdrplay_api_fault
        from core.sdrplay_service import restart_sdrplay_service

        def _emit(message: str) -> None:
            if from_worker:
                self.call_from_thread(self._log, message)
            else:
                self._log(message)

        if not is_sdrplay_api_fault(timeout=8.0):
            return True
        _emit("[WARN] SDRplay API no responde — reiniciando servicio...")
        ok, msg = restart_sdrplay_service(stop_wait_s=8.0, start_wait_s=6.0)
        _emit(f"{'[OK]' if ok else '[ERR]'} SDRplay API: {msg}")
        return ok

    def _on_sdrplay_stream_start_failed(self, detail: str) -> None:
        from core.soapy_runtime import message_indicates_sdrplay_api_fault
        from core.sdrplay_service import restart_sdrplay_service

        short = detail.strip().replace("\n", " ")[:160]
        self._log(f"[ERR] Stream RX: {short}")
        if message_indicates_sdrplay_api_fault(detail):
            self._log("[INFO] Reiniciando SDRplay API tras fallo de stream...")
            ok, msg = restart_sdrplay_service(stop_wait_s=8.0, start_wait_s=6.0)
            level = "[OK]" if ok else "[WARN]"
            self._log(f"{level} {msg}")
        self._on_rx_worker_crashed()

    def _restore_console(self) -> None:
        try:
            from core.console_utf8 import restore_terminal_after_tui

            restore_terminal_after_tui()
        except Exception:
            pass

    # ── Zoom dinámico / bandwidth viewport ───────────────────────────────────

    def _rebuild_zoom_levels(self) -> None:
        """Regenera niveles de zoom según el sample_rate actual."""
        self.visible_spans = build_visible_spans(self.sample_rate)

    def _adapt_viewport_to_bandwidth(self) -> tuple[float, float]:
        """Adapta zoom al bandwidth IQ sin mover frecuencia ni centro del viewport."""
        previous_span = float(self.visible_span)

        if not self.visible_spans:
            self._rebuild_zoom_levels()

        max_span = float(self.visible_spans[-1])

        if self.visible_span > max_span:
            self.visible_span = max_span
            self.zoom_index = len(self.visible_spans) - 1
        elif any(abs(span - self.visible_span) < 1.0 for span in self.visible_spans):
            self.zoom_index = find_zoom_index(self.visible_span, self.visible_spans)
        else:
            narrower = [span for span in self.visible_spans if span <= self.visible_span + 1.0]
            self.visible_span = float(narrower[-1] if narrower else self.visible_spans[0])
            self.zoom_index = find_zoom_index(self.visible_span, self.visible_spans)

        return previous_span, float(self.visible_span)

    # ── Sincronizacion del Viewport ──────────────────────────────────────────

    def _sync_viewport(self, *, immediate: bool = False) -> None:
        """Propaga viewport: timeline al instante; espectro/waterfall con debounce."""
        try:
            timeline = self.query_one("#timeline", FrequencyTimeline)
            timeline.viewport_center_hz = self.viewport_center
            timeline.visible_span_hz = self.visible_span
            timeline.tuned_freq_hz = self.tuned_frequency
            timeline.passband_center_hz = self.passband_center_hz
            timeline.passband_width_hz = self.passband_width_hz
            timeline.passband_preview_width_hz = self._passband_preview_width
        except Exception:
            pass

        if immediate:
            if self._viewport_debounce_timer is not None:
                self._viewport_debounce_timer.stop()
                self._viewport_debounce_timer = None
            self._apply_display_viewport()
            return

        if self._viewport_debounce_timer is None:
            self._viewport_debounce_timer = self.set_timer(
                VIEWPORT_DEBOUNCE_S,
                self._on_viewport_debounce,
            )

    def _on_viewport_debounce(self) -> None:
        self._viewport_debounce_timer = None
        self._apply_display_viewport()

    def _apply_display_viewport(self) -> None:
        """Actualiza espectro y waterfall (re-slice desde caché de banda)."""
        vp_t0 = time.perf_counter() if self.debug_mode else 0.0

        span_ratio = self.visible_span / max(self.sample_rate, 1.0)
        self._level_tracker.set_span_ratio(span_ratio)
        if (
            self._tracker_viewport_span is None
            or abs(self._tracker_viewport_span - self.visible_span) > 1.0
        ):
            self._level_tracker.reconfigure(self._display_width, reset=True)
            self._tracker_viewport_span = float(self.visible_span)

        try:
            spectrum = self.query_one("#spectrum", SpectrumGraph)
            spectrum.set_viewport(self.viewport_center, self.visible_span)
            spectrum.passband_center_hz = self.passband_center_hz
            spectrum.passband_width_hz = self.passband_width_hz
            spectrum.passband_preview_width_hz = self._passband_preview_width
        except Exception:
            pass

        try:
            waterfall = self.query_one("#waterfall", WaterfallTimeline)
            waterfall.set_viewport(self.viewport_center, self.visible_span)
            waterfall.passband_center_hz = self.passband_center_hz
            waterfall.passband_width_hz = self.passband_width_hz
            waterfall.passband_preview_width_hz = self._passband_preview_width
        except Exception:
            pass

        if self.debug_mode:
            self._debug_last_viewport_ms = (time.perf_counter() - vp_t0) * 1000.0

    # ── Acciones de Scroll (← →) ─────────────────────────────────────────────

    def action_scroll_left(self) -> None:
        """Desplaza la frecuencia sintonizada a la izquierda."""
        self.tuned_frequency = max(
            FREQ_MIN_HZ, self.tuned_frequency - self.scroll_step
        )
        self.passband_center_hz = self.tuned_frequency
        # Auto-paginacion suave con margen 10%
        left_edge = self.viewport_center - self.visible_span / 2
        margin = self.visible_span * 0.1
        if self.tuned_frequency < left_edge + margin:
            self.viewport_center = (
                self.tuned_frequency + self.visible_span / 2 - margin
            )
            # Clamp: no mostrar frecuencias negativas
            self.viewport_center = max(
                self.visible_span / 2, self.viewport_center
            )
        self._apply_tuning()

    def action_scroll_right(self) -> None:
        """Desplaza la frecuencia sintonizada a la derecha."""
        self.tuned_frequency = min(
            FREQ_MAX_HZ, self.tuned_frequency + self.scroll_step
        )
        self.passband_center_hz = self.tuned_frequency
        # Auto-paginacion suave con margen 10%
        right_edge = self.viewport_center + self.visible_span / 2
        margin = self.visible_span * 0.1
        if self.tuned_frequency > right_edge - margin:
            self.viewport_center = (
                self.tuned_frequency - self.visible_span / 2 + margin
            )
        self._apply_tuning()

    # ── Acciones de Step (↑ ↓) ───────────────────────────────────────────────

    def action_step_up(self) -> None:
        """Aumenta el paso de scroll al siguiente valor predefinido."""
        if self.step_index < len(SCROLL_STEPS) - 1:
            self.step_index += 1
            self.scroll_step = float(SCROLL_STEPS[self.step_index])
            self._log(f"Step: {_format_hz(self.scroll_step)}")
            self._update_status()

    def action_step_down(self) -> None:
        """Disminuye el paso de scroll al valor predefinido anterior."""
        if self.step_index > 0:
            self.step_index -= 1
            self.scroll_step = float(SCROLL_STEPS[self.step_index])
            self._log(f"Step: {_format_hz(self.scroll_step)}")
            self._update_status()

    # ── Acciones de Zoom (Ctrl+← Ctrl+→ / = -) ──────────────────────────────

    def action_zoom_in(self) -> None:
        """Zoom in: muestra menos ancho de banda (mayor resolucion)."""
        if self.zoom_index > 0:
            self.zoom_index -= 1
            self.visible_span = float(self.visible_spans[self.zoom_index])
            self._sync_viewport()
            self._log(f"Zoom: {_format_hz(self.visible_span)}")
            self._update_status()

    def action_zoom_out(self) -> None:
        """Zoom out: muestra mas ancho de banda (menor resolucion)."""
        if self.zoom_index < len(self.visible_spans) - 1:
            self.zoom_index += 1
            self.visible_span = float(self.visible_spans[self.zoom_index])
            self._sync_viewport()
            self._log(f"Zoom: {_format_hz(self.visible_span)}")
            self._update_status()

    # ── Centrado (Espacio) ───────────────────────────────────────────────────

    def action_center_view(self) -> None:
        """Centra el viewport en la frecuencia sintonizada actual."""
        self.viewport_center = self.tuned_frequency
        self._sync_viewport(immediate=True)
        self._log("Vista centrada")

    # ── RX Start/Stop ────────────────────────────────────────────────────────

    def action_toggle_rx(self) -> None:
        if self._rx_active:
            self._stop_rx()
        else:
            self._start_rx()

    def _maybe_restart_sdrplay_before_rx(self) -> None:
        """Reinicia SDRplayAPIService si la sesión anterior crasheó o env lo pide."""
        import os

        from core.sdrplay_service import (
            previous_session_needs_service_restart,
            restart_sdrplay_service,
        )

        if os.name != "nt":
            return
        if not self._device or self._device.driver != "sdrplay" or self._device.is_simulated:
            return
        force = os.environ.get("XYZ_SDR_SDRPLAY_RESTART", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if not force and not previous_session_needs_service_restart(self._previous_session_marker):
            return
        ok, msg = restart_sdrplay_service()
        if ok:
            self._log("[INFO] SDRplayAPIService reiniciado antes de RX")
        else:
            self._log(f"[WARN] Reinicio SDRplayAPIService: {msg}")

    def _ensure_sdrplay_rx_preflight(self) -> bool:
        """Preflight RX en subproceso; evita segfault nativo en el proceso TUI."""
        from core.session_log import log_breadcrumb

        if not self._device or self._device.is_simulated or self._device.driver != "sdrplay":
            return True

        if self._sdrplay_preflight_done:
            return self._sdrplay_preflight_ok

        # Dispositivo abierto sin preflight previo → no activar RX in-process (segfault).
        if self._device._sdr is not None:
            log_breadcrumb("sdrplay preflight missing: device already open in parent")
            self._log(
                "[ERR] Preflight RX no ejecutado antes de abrir el RSP; "
                "reinicia la app (no uses XYZ_SDR_SKIP_SDRPLAY_PREFLIGHT)"
            )
            self._sdrplay_preflight_done = True
            self._sdrplay_preflight_ok = False
            return False

        from core.sdrplay_preflight import (
            apply_preflight_strategy,
            preflight_user_message,
            resolve_preflight_timeout,
            run_preflight_best,
        )
        from core.sdrplay_service import restart_sdrplay_service

        timeout = resolve_preflight_timeout()
        result = run_preflight_best(timeout=timeout)
        if result.segfault:
            restart_sdrplay_service()
            result = run_preflight_best(timeout=timeout)

        self._sdrplay_preflight_done = True
        self._sdrplay_preflight_ok = result.ok
        if result.ok:
            apply_preflight_strategy(result)
        if not result.ok:
            msg = preflight_user_message(result)
            if msg:
                self._log(msg)
            if result.detail:
                self._log(
                    f"[ERR] Preflight ({result.path}, {result.last_step}): "
                    f"{result.detail[:240]}"
                )
        return result.ok

    def ensure_audio_output(self) -> None:
        """Inicia audio tras la primera lectura IQ (worker RX)."""
        if self._audio_output is not None or not self._rx_active:
            return
        self.call_from_thread(self._start_audio_output_main)

    def _start_audio_output_main(self) -> None:
        if self._audio_output is not None or not self._rx_active:
            return
        try:
            self._audio_output = AudioOutputQueue(sample_rate=self._audio_rate)
            self._audio_output.set_volume(self.volume_value / 100.0)
            self._audio_output.start()
            self._audio_started = True
            self._log(f"[OK]   Salida de audio iniciada ({self._audio_rate} Hz, callback)")
        except Exception as e:
            self._audio_output = None
            self._log(f"[WARN] Sin salida de audio: {e}")

    def _start_rx(self) -> None:
        if self._rx_active:
            return

        if self._driver_changing:
            self._log("[WARN] Cambio de driver en curso; espera antes de iniciar RX")
            return

        if not self._hardware_ready:
            self._log("[WARN] Hardware aún inicializándose; espera unos segundos")
            return

        if not self._device:
            self._log("[ERROR] Dispositivo SDR no inicializado — reinicia la app")
            return

        if not self._rx_stop_event.is_set():
            if not self._rx_stop_event.wait(timeout=3.0):
                self._log("[WARN] Worker RX previo no finalizó; continuando")
                self._rx_stop_event.set()

        self._rx_active = True
        self._rx_stop_event.clear()

        from core.rx_warmup import RX_WARMUP_ITERS

        self._rx_warmup_iters_left = RX_WARMUP_ITERS
        self._audio_started = False
        self._audio_output = None

        self._maybe_restart_sdrplay_before_rx()

        try:
            btn = self.query_one("#btn_rx", Button)
            btn.label = "|| DETENER RX"
            btn.variant = "error"
        except Exception:
            pass
        self._log("RX iniciado")
        if (
            self._device
            and not self._device.is_simulated
            and self._device.driver == "sdrplay"
            and self.sample_rate > SAFE_START_SAMPLE_RATE
        ):
            self._log(
                f"[INFO] SDRplay: arranque a {_format_bandwidth_hz(SAFE_START_SAMPLE_RATE)} "
                f"→ {_format_bandwidth_hz(self.sample_rate)} tras warmup"
            )
        self._stream_stats_snapshot = StreamStats()
        self._invalidate_band_cache()
        self._fm_demod_state.reset()
        self._fm_agc.reset()
        self._rx_worker_token += 1
        token = self._rx_worker_token
        self._rx_worker(token)

    def _stop_rx(self) -> None:
        if not self._rx_active and self._rx_stop_event.is_set():
            return

        self._rx_active = False
        self._rx_worker_token += 1

        if self._device and not self._device.is_simulated:
            try:
                self._device.stop_stream(timeout=3.0)
            except Exception:
                try:
                    from core.sdr_io import shutdown_sdr_io

                    shutdown_sdr_io()
                except Exception:
                    pass

        if not self._rx_stop_event.wait(timeout=3.0):
            self._log("[WARN] Timeout esperando fin del worker RX")
            try:
                from core.sdr_io import shutdown_sdr_io

                shutdown_sdr_io()
            except Exception:
                pass
            self._rx_stop_event.set()

        if self._audio_output:
            try:
                self._audio_output.stop()
            except Exception:
                pass
            self._audio_output = None
            self._audio_started = False
            self._log("[INFO] Salida de audio detenida")

        try:
            btn = self.query_one("#btn_rx", Button)
            btn.label = ">> INICIAR RX"
            btn.variant = "success"
        except Exception:
            pass
        self._log("RX detenido")
        if self._recording:
            self._stop_recording(log_stopped=False)

    def action_scroll_history_newer(self) -> None:
        """Desplaza el waterfall hacia filas más recientes."""
        try:
            wf = self.query_one("#waterfall", WaterfallTimeline)
            if wf.scroll_history(-1):
                self._log(f"Waterfall hist: offset {wf.history_offset}")
        except Exception:
            pass

    def action_scroll_history_older(self) -> None:
        """Desplaza el waterfall hacia filas más antiguas."""
        try:
            wf = self.query_one("#waterfall", WaterfallTimeline)
            if wf.scroll_history(1):
                self._log(f"Waterfall hist: offset {wf.history_offset}")
        except Exception:
            pass

    # ── Otras acciones ───────────────────────────────────────────────────────

    def action_passband_narrow(self) -> None:
        step = PASSBAND_KEYBOARD_STEP.get(self._passband_mode(), 10_000.0)
        self._adjust_passband_width(-step)

    def action_passband_widen(self) -> None:
        step = PASSBAND_KEYBOARD_STEP.get(self._passband_mode(), 10_000.0)
        self._adjust_passband_width(step)

    def action_focus_freq(self) -> None:
        self.query_one("#inp_freq", Input).focus()

    def action_focus_bandwidth(self) -> None:
        self.query_one("#sel_bandwidth", Select).focus()

    def action_focus_gain(self) -> None:
        self.query_one("#sel_gain", Select).focus()

    def action_focus_volume(self) -> None:
        self.query_one("#sel_volume", Select).focus()

    def action_cycle_mode(self) -> None:
        idx = self.DEMOD_MODES.index(self.demod_mode)
        self.demod_mode = self.DEMOD_MODES[(idx + 1) % len(self.DEMOD_MODES)]
        if self.demod_mode == "auto":
            self.passband_width_hz = self._load_passband_width_for_mode(self.active_demod_mode)
        else:
            self.passband_width_hz = self._load_passband_width_for_mode(self.demod_mode)
        self._fm_demod_state.reset()
        self._sync_passband_widgets()
        self._update_mode_ui()
        self._log(f"Modo: {self.demod_mode.upper()}")
        self._update_status()

    def action_record(self) -> None:
        """Toggle recording via StorageController."""
        self._storage.toggle_recording()

    def _start_recording(self) -> None:
        """DEPRECATED: delega a StorageController.start_recording()."""
        self._storage.start_recording()

    def _stop_recording(self, *, log_stopped: bool = True) -> None:
        """DEPRECATED: delega a StorageController.stop_recording()."""
        self._storage.stop_recording(log_stopped=log_stopped)

    def action_show_settings(self) -> None:
        """Abre el panel modal de Ajustes de Hardware SDR."""
        from tui.widgets.settings_menu import SettingsScreen

        try:
            self.push_screen(SettingsScreen())
        except Exception as exc:
            logger.exception("No se pudo abrir ajustes: %s", exc)
            self._log(f"[ERROR] No se pudo abrir ajustes: {exc}")

    def sdrplay_wizard_lines(self, *, attempt_recover: bool = False) -> list[str]:
        """Líneas de estado para el wizard SDRplay (página Hardware)."""
        from core.sdrplay_wizard import collect_sdrplay_wizard_snapshot, format_wizard_lines

        preflight_ok: bool | None = None
        if getattr(self, "_sdrplay_preflight_done", False):
            preflight_ok = bool(getattr(self, "_sdrplay_preflight_ok", False))
        snapshot = collect_sdrplay_wizard_snapshot(
            attempt_recover=attempt_recover,
            preflight_ok=preflight_ok,
        )
        cached = getattr(self, "_cached_sdr_devices", None) or []
        sdrplay_cached = sum(
            1 for d in cached if str(d.get("driver", "")).lower() == "sdrplay"
        )
        return format_wizard_lines(snapshot, cached_sdrplay=sdrplay_cached)

    @work(thread=True)
    def _refresh_sdrplay_wizard_async(self, *, attempt_recover: bool = False) -> None:
        try:
            from core.sdrplay_enumerate import recover_sdrplay_enumeration

            if attempt_recover:
                recover_sdrplay_enumeration(restart_if_missing=True)
            self.call_from_thread(self._on_sdrplay_wizard_refreshed)
        except Exception as exc:
            self.call_from_thread(self._on_sdrplay_wizard_failed, str(exc))

    def _on_sdrplay_wizard_refreshed(self) -> None:
        self._refresh_enumerated_devices_if_safe()
        screen = self.screen
        if hasattr(screen, "_refresh_hardware_page"):
            screen._refresh_hardware_page(attempt_recover=False)
        if hasattr(screen, "hide_busy"):
            screen.hide_busy()
        self._log("[OK] Diagnóstico SDRplay actualizado")

    def _on_sdrplay_wizard_failed(self, message: str) -> None:
        screen = self.screen
        if hasattr(screen, "hide_busy"):
            screen.hide_busy()
        self._log(f"[ERROR] Actualizar diagnóstico: {message}")

    @work(thread=True)
    def _restart_sdrplay_service_async(self) -> None:
        from core.sdrplay_enumerate import recover_sdrplay_enumeration

        found, msg, _status = recover_sdrplay_enumeration(restart_if_missing=True)
        self.call_from_thread(self._on_sdrplay_service_recovered, found, msg)

    def _on_sdrplay_service_recovered(self, found: bool, message: str) -> None:
        self._refresh_enumerated_devices_if_safe()
        level = "[OK]" if found else "[WARN]"
        self._log(f"{level} SDRplay API: {message}")
        screen = self.screen
        if hasattr(screen, "_refresh_hardware_page"):
            screen._refresh_hardware_page(attempt_recover=False)
        if hasattr(screen, "hide_busy"):
            screen.hide_busy()

    @work(thread=True)
    def _run_sdrplay_diagnose_async(self) -> None:
        from core.diagnose_sdrplay import collect_diagnose_report, format_diagnose_report, write_diagnose_report

        report = collect_diagnose_report(run_stream_test=False, run_probe=False)
        text = format_diagnose_report(report)
        out_path = write_diagnose_report(report)
        summary = text.splitlines()[:18]
        self.call_from_thread(self._on_sdrplay_diagnose_done, "\n".join(summary), str(out_path), report.issues)

    def _on_sdrplay_diagnose_done(self, summary: str, out_path: str, issues: list[str]) -> None:
        self._log("[INFO] Diagnóstico SDRplay (rápido, sin stream):")
        for line in summary.splitlines():
            if line.strip():
                self._log(f"  {line}")
        if issues:
            self._log(f"[WARN] {len(issues)} issue(s) — ver informe completo")
        self._log(f"[INFO] Informe: {out_path}")
        screen = self.screen
        if hasattr(screen, "_refresh_hardware_page"):
            screen._refresh_hardware_page(attempt_recover=False)
        if hasattr(screen, "hide_busy"):
            screen.hide_busy()

    def action_quit(self) -> None:
        """Salida limpia con pantalla de cierre."""
        try:
            if self._recording:
                self._stop_recording(log_stopped=False)
            self._prepare_for_exit()
        finally:
            self._graceful_shutdown = True
            self.exit()

    def _persist_config(self, section: str, **updates) -> bool:
        """Unificado: delega a StorageController.persist_config().

        Mantenido como wrapper para tests legacy. La forma preferida es
        llamar directamente a ``self._storage.persist_config(section, **updates)``.
        """
        return self._storage.persist_config(section, **updates)

    def _persist_device_config(
        self,
        *,
        driver: str | None = None,
        sample_rate: float | None = None,
    ) -> None:
        """DEPRECATED: usa _storage.persist_config('device', ...)."""
        # Mantenemos side-effects legacy: center_freq y gain siempre se persisten
        self._persist_config(
            "device",
            driver=driver,
            sample_rate=sample_rate,
            center_freq=self.tuned_frequency,
            gain=self.gain_value,
        )

    def _persist_dsp_config(
        self,
        *,
        squelch_enabled: bool | None = None,
        squelch_threshold: float | None = None,
        squelch_hang_ms: float | None = None,
        volume: float | None = None,
        fm_deemphasis_us: float | None = None,
        fm_agc_enabled: bool | None = None,
    ) -> None:
        """DEPRECATED: usa _storage.persist_config('dsp', ...)."""
        self._persist_config(
            "dsp",
            squelch_enabled=squelch_enabled,
            squelch_threshold=squelch_threshold,
            squelch_hang_ms=squelch_hang_ms,
            volume=volume,
            fm_deemphasis_us=fm_deemphasis_us,
            fm_agc_enabled=fm_agc_enabled,
        )

    def _persist_recorder_config(
        self,
        *,
        record_iq: bool | None = None,
        record_audio: bool | None = None,
    ) -> None:
        """DEPRECATED: usa _storage.persist_config('recorder', ...)."""
        self._persist_config(
            "recorder",
            record_iq=record_iq,
            record_audio=record_audio,
        )

    def _persist_scanner_config(
        self,
        *,
        freq_start: float | None = None,
        freq_end: float | None = None,
        freq_step: float | None = None,
        dwell_ms: float | None = None,
        min_snr_db: float | None = None,
        pause_on_signal: bool | None = None,
        pause_resume_snr_db: float | None = None,
    ) -> None:
        """DEPRECATED: usa _storage.persist_config('scanner', ...)."""
        self._persist_config(
            "scanner",
            freq_start=freq_start,
            freq_end=freq_end,
            freq_step=freq_step,
            dwell_ms=dwell_ms,
            min_snr_db=min_snr_db,
            pause_on_signal=pause_on_signal,
            pause_resume_snr_db=pause_resume_snr_db,
        )

    def _bookmarks_path(self) -> Path:
        """DEPRECATED: usa _storage.bookmarks_path()."""
        return self._storage.bookmarks_path()

    def _resolve_bookmark_io_path(self, path_str: str) -> Path:
        """DEPRECATED: ya no es necesario (StorageController resuelve internamente)."""
        return self._storage._resolve_bookmark_io_path(path_str)

    def _refresh_preset_select(self) -> None:
        try:
            sel = self.query_one("#sel_preset", Select)
            options = [(name, f"{freq}:{mode}") for name, freq, mode in self._storage.bookmarks]
            sel.update(options)
        except Exception as exc:
            logger.debug("No se pudo actualizar sel_preset: %s", exc)

    def export_bookmarks_to_path(self, path_str: str) -> bool:
        """DEPRECATED: usa _storage.export_bookmarks_to()."""
        return self._storage.export_bookmarks_to(path_str)

    def import_bookmarks_from_path(self, path_str: str, merge: bool) -> bool:
        """DEPRECATED: usa _storage.import_bookmarks_from()."""
        return self._storage.import_bookmarks_from(path_str, merge=merge)

    def action_toggle_scan(self) -> None:
        """Inicia, pausa/reanuda o detiene el escáner de banda."""
        if self._scanner.scanning and self._scanner.paused:
            self._resume_scanning()
        elif self._scanner.scanning:
            self._stop_scanning()
        else:
            self._start_scanning()

    def _update_scan_button_label(self) -> None:
        try:
            btn = self.query_one("#btn_scan", Button)
            if not self._scanner.scanning:
                btn.label = "🔍 ESCANEAR BANDA"
                btn.variant = "primary"
            elif self._scanner.paused:
                btn.label = "▶ CONTINUAR ESCANEO"
                btn.variant = "warning"
            else:
                btn.label = "■ DETENER ESCANEO"
                btn.variant = "error"
        except Exception:
            pass

    # ── Métodos legacy que delegan a ScannerEngine ─────────────────────────
    # Mantenidos para compatibilidad con cualquier llamador externo.

    @property
    def _scanning(self) -> bool:
        return self._scanner.scanning

    @property
    def _scan_paused(self) -> bool:
        return self._scanner.paused

    def _start_scanning(self) -> None:
        if not self._rx_active:
            self.audio_effects.play_error()
            self._log("[ERROR] Inicia RX antes de escanear")
            return
        # Delegar al engine
        scan_cfg = self.config.get("scanner", {})
        self._scanner.configure(scan_cfg)
        self._scanner.start()
        # Sync legacy state for any external reads
        self._scan_start_hz = float(scan_cfg.get("freq_start", 88_000_000))
        self._scan_end_hz = float(scan_cfg.get("freq_end", 108_000_000))
        self._scan_step_hz = float(scan_cfg.get("freq_step", 200_000))
        self._scan_dwell_s = float(scan_cfg.get("dwell_ms", 500)) / 1000.0
        self._scan_min_snr = float(scan_cfg.get("min_snr_db", 10.0))
        self._scan_pause_on_signal = bool(scan_cfg.get("pause_on_signal", True))
        self._scan_pause_resume_snr = float(scan_cfg.get("pause_resume_snr_db", 7.0))
        self._update_scan_button_label()

    def _stop_scanning(self) -> None:
        self._scanner.stop()
        self._update_scan_button_label()

    def _pause_scan_on_signal(self, passband_snr: float) -> None:
        self._scanner.pause(passband_snr)
        self._update_scan_button_label()

    def _resume_scanning(self) -> None:
        self._scanner.resume()
        self._update_scan_button_label()

    def _step_scanner(self) -> None:
        """Avanza a la siguiente freq. Mantiene guard de recursión."""
        self._is_scanner_stepping = True
        try:
            self._scanner.step()
        finally:
            self._is_scanner_stepping = False

    def _handle_scanner_step(self, frame, snr: float, floors: np.ndarray, ceilings: np.ndarray) -> None:
        """Delegado a ScannerEngine.on_frame(). Mantenido por compat."""
        self._scanner.on_frame(frame.center_hz, floors, ceilings)

    # ── ScannerHost protocol: callbacks delegan a la app ───────────────────

    def set_tuned_frequency(self, freq_hz: float) -> None:
        """Callback del ScannerEngine: sincroniza freq + passband + viewport."""
        self._is_scanner_stepping = True
        try:
            self.tuned_frequency = freq_hz
            self.passband_center_hz = freq_hz
            self.viewport_center = freq_hz
            self._apply_tuning()
        finally:
            self._is_scanner_stepping = False

    def host_log(self, message: str) -> None:
        """Callback del ScannerEngine / StorageController (no usar `log`: reservado por Textual)."""
        self._log(message)

    def play_chime(self) -> None:
        """Callback del ScannerEngine / StorageController."""
        self.audio_effects.play_chime()

    def play_error(self) -> None:
        """Callback del ScannerEngine / StorageController."""
        self.audio_effects.play_error()

    @property
    def display_width(self) -> int:
        """Alias del ScannerHost protocol (la app usa _display_width)."""
        return self._display_width

    # ── StorageHost protocol: callbacks delegan a la app ───────────────────

    @property
    def project_root(self) -> Path:
        return self._project_root

    def refresh_preset_select(self) -> None:
        """Callback del StorageController tras import_bookmarks_from."""
        self._refresh_preset_select()

    def _sync_simulated_device_state(self) -> None:
        """Alinea driver/preflight cuando el backend es SimulatedSDR."""
        if self._device and self._device.is_simulated:
            self.driver = "simulated"
            self._sdrplay_preflight_done = True
            self._sdrplay_preflight_ok = True
            self._sdrplay_rx_blocked = False

    def _apply_desired_rx_state(self, desired_rx: bool | None) -> None:
        """Honra el interruptor RX del menú Ajustes sin reabrir el driver."""
        if desired_rx is None or self._driver_changing or not self._hardware_ready:
            return
        if desired_rx:
            if not self._rx_active:
                self._start_rx()
        elif self._rx_active:
            self._stop_rx()

    def change_device(self, device_kwargs: dict, *, desired_rx: bool | None = None) -> bool:
        """Abre un dispositivo Soapy concreto por kwargs (label/serial únicos)."""
        kwargs = dict(device_kwargs)
        driver = str(kwargs.get("driver", "")).lower()
        if driver in ("simulated", "sim"):
            return self.change_device_driver("simulated", desired_rx=desired_rx)
        if self._device and self._device.same_device_as(kwargs):
            self._apply_desired_rx_state(desired_rx)
            return True
        self.driver = driver or self.driver
        return self._schedule_reopen_device(
            device_kwargs=kwargs,
            desired_rx=desired_rx,
        )

    def change_device_driver(
        self,
        new_driver: str,
        *,
        desired_rx: bool | None = None,
    ) -> bool:
        """Cambia dinámicamente el driver del dispositivo SDR en tiempo real."""
        if new_driver == "sim":
            new_driver = "simulated"

        if new_driver == "simulated":
            if self._device and self._device.is_simulated:
                self.driver = "simulated"
                self._sync_simulated_device_state()
                self._apply_desired_rx_state(desired_rx)
                return True
        elif (
            new_driver == self.driver
            and self._device
            and self._device._device_kwargs
        ):
            self._apply_desired_rx_state(desired_rx)
            return True

        self.driver = new_driver
        return self._schedule_reopen_device(desired_rx=desired_rx)

    def _schedule_reopen_device(
        self,
        *,
        device_kwargs: dict | None = None,
        desired_rx: bool | None = None,
    ) -> bool:
        """Programa cambio de driver en hilo worker (no bloquea la TUI)."""
        if self._driver_changing:
            self._log("[WARN] Cambio de driver ya en curso; espera a que termine")
            return False

        previous_driver = self.driver
        previous_kwargs = (
            dict(self._device._device_kwargs)
            if self._device and self._device._device_kwargs
            else None
        )
        was_active = self._rx_active
        if was_active:
            self._stop_rx()

        target_label = (
            str(device_kwargs.get("label", previous_driver))
            if device_kwargs
            else previous_driver
        )
        target_driver = self.driver
        self._driver_changing = True
        self._log(f"[INFO] Cambiando driver a {target_label}…")

        device_to_close = self._device
        self._device = None

        self._reopen_device_async(
            target_driver=target_driver,
            device_kwargs=device_kwargs,
            device_to_close=device_to_close,
            previous_driver=previous_driver,
            previous_kwargs=previous_kwargs,
            was_active=was_active,
            desired_rx=desired_rx,
            tuned_frequency=self.tuned_frequency,
            gain_value=self.gain_value,
        )
        return True

    @work(thread=True)
    def _reopen_device_async(
        self,
        *,
        target_driver: str,
        device_kwargs: dict | None,
        device_to_close: SDRDevice | None,
        previous_driver: str,
        previous_kwargs: dict | None,
        was_active: bool,
        desired_rx: bool | None,
        tuned_frequency: float,
        gain_value: float,
    ) -> None:
        """Cierra y abre SDR fuera del hilo UI (enumerate/open pueden tardar o crashear)."""
        device: SDRDevice | None = None
        error: str | None = None
        restored_previous = False
        resolved_driver = target_driver

        if device_to_close:
            try:
                device_to_close.close()
            except Exception as exc:
                logger.warning("Error cerrando dispositivo previo: %s", exc)

        try:
            device = SDRDevice(driver=target_driver)
            if device_kwargs:
                device.open(device_kwargs)
            else:
                device.open()
            resolved_driver = device.driver
            device.set_frequency(tuned_frequency)
            device.set_gain(gain_value)
        except HardwareInitializationError as exc:
            error = str(exc)
            self.call_from_thread(self._log, f"[ERR]  {error}")
            self.call_from_thread(self.audio_effects.play_error)
            fallback_driver = previous_driver or "simulated"
            try:
                device = SDRDevice(driver=fallback_driver)
                if previous_kwargs and fallback_driver not in ("simulated", "sim"):
                    device.open(previous_kwargs)
                else:
                    device.open()
                resolved_driver = device.driver
                device.set_frequency(tuned_frequency)
                device.set_gain(gain_value)
                restored_previous = True
                fb_label = "SIMULACION" if device.is_simulated else resolved_driver.upper()
                self.call_from_thread(
                    self._log,
                    f"[INFO] Restaurado driver: {fb_label}",
                )
            except Exception as restore_exc:
                device = None
                self.call_from_thread(
                    self._log,
                    f"[ERR]  No se pudo restaurar el driver: {restore_exc}",
                )
        except Exception as exc:
            error = str(exc)
            logger.exception("Cambio de driver falló: %s", exc)

        self.call_from_thread(
            self._on_driver_reopen_complete,
            device,
            resolved_driver,
            error,
            was_active,
            desired_rx,
            restored_previous,
        )

    def _on_driver_reopen_complete(
        self,
        device: SDRDevice | None,
        resolved_driver: str,
        error: str | None,
        was_active: bool,
        desired_rx: bool | None,
        restored_previous: bool,
    ) -> None:
        """Hilo principal: sincroniza UI tras cambio de driver async."""
        self._driver_changing = False
        self._device = device
        self.driver = resolved_driver if device is not None else self.driver

        if device is not None:
            self._sync_simulated_device_state()

        # Resetear preflight al cambiar de driver (simulación no requiere preflight SDRplay).
        if device is not None and device.is_simulated:
            self._sdrplay_preflight_done = True
            self._sdrplay_preflight_ok = True
        else:
            self._sdrplay_preflight_done = False
            self._sdrplay_preflight_ok = False

        if device is None:
            self._update_status()
            return

        if error is None and not restored_previous:
            self._persist_device_config(driver=self.driver, sample_rate=device.sample_rate)

        self._apply_driver_change(was_active=False)

        if desired_rx is not None:
            if desired_rx and not self._rx_active:
                self._start_rx()
            elif not desired_rx and self._rx_active:
                self._stop_rx()
        elif was_active and error is None:
            self._start_rx()

        if error is None:
            self.audio_effects.play_chime()

        if error is not None and restored_previous:
            try:
                from core.device import build_driver_select_options

                active_kwargs = device._device_kwargs if device._device_kwargs else None
                _, _, selected = build_driver_select_options(
                    getattr(self, "_cached_sdr_devices", None),
                    current_driver=self.driver,
                    active_kwargs=active_kwargs,
                )
                self.query_one("#set_driver", Select).value = selected
            except Exception:
                pass

    def _reopen_device(self, open_fn) -> bool:
        """Legacy sync path (tests); producción usa _schedule_reopen_device."""
        previous_driver = self.driver
        previous_kwargs = (
            dict(self._device._device_kwargs)
            if self._device and self._device._device_kwargs
            else None
        )
        was_active = self._rx_active
        if was_active:
            self._stop_rx()

        if self._device:
            self._device.close()
            self._device = None

        try:
            self._device = SDRDevice(driver=self.driver)
            open_fn(self._device)
            self.driver = self._device.driver
            self._device.set_frequency(self.tuned_frequency)
            self._device.set_gain(self.gain_value)
        except HardwareInitializationError as exc:
            self._log(f"[ERR]  {exc}")
            self.audio_effects.play_error()
            fallback_driver = previous_driver or "simulated"
            try:
                self._device = SDRDevice(driver=fallback_driver)
                if previous_kwargs and fallback_driver not in ("simulated", "sim"):
                    self._device.open(previous_kwargs)
                else:
                    self._device.open()
                self.driver = self._device.driver
                self._device.set_frequency(self.tuned_frequency)
                self._device.set_gain(self.gain_value)
                fb_label = "SIMULACION" if self._device.is_simulated else self.driver.upper()
                self._log(f"[INFO] Restaurado driver: {fb_label}")
            except Exception as restore_exc:
                self._device = None
                self._log(f"[ERR]  No se pudo restaurar el driver: {restore_exc}")
                return False

            self._apply_driver_change(was_active)
            return False

        self._apply_driver_change(was_active)
        self._persist_device_config(driver=self.driver, sample_rate=self.sample_rate)
        return True

    def _refresh_enumerated_devices_if_safe(self) -> None:
        """Re-enumerar Soapy solo sin dispositivo abierto (sdrplay crashea si no)."""
        if self._device is not None:
            return
        try:
            from core.device import SDRDevice, filter_sdr_devices

            self._cached_sdr_devices = filter_sdr_devices(SDRDevice.list_devices())
        except Exception as exc:
            logger.debug("No se pudo refrescar lista SDR: %s", exc)

    def _apply_driver_change(self, was_active: bool) -> None:
        """Sincroniza UI y viewport tras abrir un driver."""
        self.sample_rate = self._device.sample_rate

        cfg_rate = self.config.get("device", {}).get("sample_rate")
        if cfg_rate is not None:
            cfg_rate = float(cfg_rate)
            if (
                abs(cfg_rate - self.sample_rate) > 1.0
                and self._device.is_sample_rate_supported(cfg_rate)
            ):
                self.change_bandwidth(cfg_rate)
            else:
                self._rebuild_zoom_levels()
                self._adapt_viewport_to_bandwidth()
        else:
            self._rebuild_zoom_levels()
            self._adapt_viewport_to_bandwidth()

        self._sync_viewport(immediate=True)
        self._refresh_bandwidth_select()

        device_str = "SIMULACION" if self._device.is_simulated else self.driver.upper()
        self.sub_title = f"{device_str} | {self.tuned_frequency / 1e6:.3f} MHz"
        self._log(f"[OK]   Cambiado a driver: {device_str}")

        if was_active:
            self._start_rx()
        else:
            self._update_status()

    def change_bandwidth(self, new_rate: float) -> bool:
        """Cambia el bandwidth IQ (sample rate) preservando sintonía y viewport."""
        if self._bandwidth_changing:
            self._log("[WARN] Cambio de bandwidth ya en curso")
            return False

        if not self._device:
            self._log("[ERR]  Dispositivo SDR no disponible")
            return False

        if abs(self.sample_rate - new_rate) < 1.0:
            return True

        err = validate_sample_rate(self._device, new_rate, self.sample_rate)
        if err:
            self._log(f"[ERR]  {err}")
            return False

        self._bandwidth_changing = True
        was_rx = self._rx_active

        try:
            if was_rx:
                self._stop_rx()

            self._device.set_sample_rate(new_rate)
            self.sample_rate = float(new_rate)
            self._rebuild_zoom_levels()
            previous_span, new_span = self._adapt_viewport_to_bandwidth()

            # Reafirmar sintonía por si el driver resetea parámetros
            self._device.set_frequency(self.tuned_frequency)
            self._sync_viewport(immediate=True)
            self._update_status()

            self._log(f"[OK]   Bandwidth: {_format_bandwidth_hz(new_rate)}")
            profile = profile_for_sample_rate(new_rate)
            if self.demod_mode == "wbfm" and new_rate <= 250_000:
                self._log("[INFO] WBFM @ 250 kHz: PASS limitado; 1–2 MHz recomendado para FM broadcast")
            elif not is_mode_recommended(self.active_demod_mode, profile):
                modes = ", ".join(profile.recommended_modes)
                self._log(f"[INFO] Modo {self.active_demod_mode.upper()}: preset óptimo para {modes}")
            if new_span < previous_span - 1.0:
                self._log(
                    f"[INFO] Zoom adaptado: {_format_hz(previous_span)} -> {_format_hz(new_span)}"
                )

            if was_rx:
                self._start_rx()

            self._persist_device_config(sample_rate=self.sample_rate)
            self._sync_bandwidth_select_value()
            return True

        except SampleRateError as exc:
            self._log(f"[ERR]  {exc}")
            return False
        except Exception as exc:
            logger.exception("Error cambiando bandwidth")
            self._log(f"[ERR]  Error cambiando bandwidth: {exc}")
            return False
        finally:
            self._bandwidth_changing = False

    # ── Eventos UI ───────────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_rx":
            self.audio_effects.play_blip()
            self.action_toggle_rx()
        elif event.button.id == "btn_rec":
            self.audio_effects.play_blip()
            self.action_record()
        elif event.button.id == "btn_save_bookmark":
            self.audio_effects.play_blip()
            self._action_save_bookmark()
        elif event.button.id == "btn_scan":
            self.audio_effects.play_blip()
            self.action_toggle_scan()
        elif event.button.id and event.button.id.startswith("btn_spd_"):
            self.audio_effects.play_blip()
            speed_val = int(event.button.id.replace("btn_spd_", ""))
            self._set_waterfall_speed(speed_val)

    def _action_save_bookmark(self) -> None:
        """DEPRECATED: usa _storage.save_current_as_bookmark().

        Mantenido por compat con event handlers; preserva el formato del nombre
        legacy (e.g. "100.600 MHz (WBFM)") y la lógica de duplicados con
        warning + play_error.
        """
        freq_mhz = self.tuned_frequency / 1e6
        mode = self.demod_mode.upper()
        name = f"{freq_mhz:.3f} MHz ({mode})"

        bookmark = self._storage.save_current_as_bookmark(name=name)
        if bookmark is None:
            # Duplicado
            self._log(f"[WARN] Bookmark ya existe para {freq_mhz:.3f} MHz en modo {mode}")
            self.audio_effects.play_error()
        else:
            self._refresh_preset_select()
            self._log(f"[OK] Guardado bookmark: {bookmark[0]}")

    def _set_waterfall_speed(self, speed: int) -> None:
        """Establece la velocidad de la cascada (FPS) y actualiza los estilos de los botones."""
        try:
            waterfall = self.query_one("#waterfall", WaterfallTimeline)
            waterfall.waterfall_speed = speed
        except Exception:
            pass

        # Actualizar clases CSS activas de los botones de velocidad
        for s in WATERFALL_SPEEDS:
            try:
                btn = self.query_one(f"#btn_spd_{s}", Button)
                if s == speed:
                    btn.add_class("active-spd")
                else:
                    btn.remove_class("active-spd")
            except Exception:
                pass
        self._log(f"Velocidad de cascada: {speed} FPS")

    def on_click(self, event: events.Click) -> None:
        if event.widget and event.widget.id and event.widget.id.startswith("btn_mode_"):
            self.audio_effects.play_blip()
            mode = event.widget.id.replace("btn_mode_", "")
            self.demod_mode = mode
            if mode == "auto":
                self.passband_width_hz = self._load_passband_width_for_mode(self.active_demod_mode)
            else:
                self.passband_width_hz = self._load_passband_width_for_mode(mode)
            self._sync_passband_widgets()
            self._update_mode_ui()
            self._log(f"Modo: {self.demod_mode.upper()}")
            self._update_status()
            return

        w = event.widget
        if w and w.id in ("spectrum", "waterfall", "log_panel"):
            self.set_focus(None)
            event.stop()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "inp_freq":
            try:
                new_freq = float(event.value) * 1e6
                new_freq = max(FREQ_MIN_HZ, min(FREQ_MAX_HZ, new_freq))
                self.tuned_frequency = new_freq
                self.passband_center_hz = new_freq
                self.viewport_center = new_freq
                self._apply_tuning()
                self._log(f"Frecuencia: {self.tuned_frequency / 1e6:.4f} MHz")
            except ValueError:
                self.audio_effects.play_error()
                self._log(f"[ERROR] Frecuencia invalida: {event.value}")

    def on_select_changed(self, event: Select.Changed) -> None:
        if not _is_valid_select(event.value):
            return

        if event.select.id == "sel_gain":
            try:
                self.gain_value = float(event.value)
                if self._device:
                    self._device.set_gain(self.gain_value)
                self.audio_effects.play_blip()
                self._log(f"Ganancia: {self.gain_value:.0f} dB")
                self._update_status()
            except ValueError:
                self.audio_effects.play_error()
                self._log(f"[ERROR] Ganancia invalida: {event.value}")

        elif event.select.id == "sel_volume":
            try:
                self.volume_value = float(event.value)
                if self._audio_output:
                    self._audio_output.set_volume(self.volume_value / 100.0)
                self.audio_effects.play_blip()
                self._log(f"Volumen: {self.volume_value:.0f}%")
                self._update_status()
            except ValueError:
                self.audio_effects.play_error()
                self._log(f"[ERROR] Volumen invalido: {event.value}")

        elif event.select.id == "sel_bandwidth":
            if self._bandwidth_changing:
                self._sync_bandwidth_select_value()
                return
            try:
                new_rate = float(event.value)
                if abs(new_rate - self.sample_rate) < 1.0:
                    return
                if self.change_bandwidth(new_rate):
                    self.audio_effects.play_chime()
                else:
                    self.audio_effects.play_error()
                    self._sync_bandwidth_select_value()
            except (TypeError, ValueError):
                self.audio_effects.play_error()
                self._sync_bandwidth_select_value()
                self._log(f"[ERROR] Bandwidth invalido: {event.value}")

        elif event.select.id == "sel_preset":
            parts = str(event.value).split(":")
            if len(parts) == 2:
                self.tuned_frequency = float(parts[0])
                self.passband_center_hz = self.tuned_frequency
                self.viewport_center = self.tuned_frequency
                self.demod_mode = parts[1]
                self.passband_width_hz = self._load_passband_width_for_mode(self.demod_mode)
                self._update_mode_ui()
                self._apply_tuning()
                self.audio_effects.play_blip()
                self._log(
                    f"Preset: {self.tuned_frequency / 1e6:.3f} MHz"
                    f" {self.demod_mode.upper()}"
                )

        elif event.select.id == "sel_band":
            if event.value:
                self._apply_band_profile(str(event.value))

    def on_passband_preview(self, message: PassbandPreview) -> None:
        self._passband_preview_width = message.width_hz
        now = time.monotonic()
        if now < self._passband_preview_sync_at:
            return
        self._passband_preview_sync_at = now + 0.04
        self._sync_passband_widgets()

    def on_passband_select_request(self, message: PassbandSelectRequest) -> None:
        self._apply_passband_selection(message.center_hz, message.width_hz)

    def on_waterfall_timeline_history_scroll_request(
        self, message: WaterfallTimeline.HistoryScrollRequest
    ) -> None:
        try:
            wf = self.query_one("#waterfall", WaterfallTimeline)
            self._log(f"Waterfall hist: offset {wf.history_offset}")
        except Exception:
            pass

    def on_frequency_timeline_scroll_request(self, message: FrequencyTimeline.ScrollRequest) -> None:
        if message.direction > 0:
            self.action_scroll_right()
        else:
            self.action_scroll_left()

    def on_frequency_timeline_zoom_request(self, message: FrequencyTimeline.ZoomRequest) -> None:
        if message.direction > 0:
            self.action_zoom_out()
        else:
            self.action_zoom_in()

    # ── RX Worker ────────────────────────────────────────────────────────────

    def consume_rx_warmup_samples(self, requested: int) -> int:
        """Limita el chunk IQ durante las primeras iteraciones RX (warmup)."""
        from core.rx_warmup import cap_rx_warmup_samples

        prev_warmup = self._rx_warmup_iters_left
        capped, remaining = cap_rx_warmup_samples(requested, self._rx_warmup_iters_left)
        self._rx_warmup_iters_left = remaining
        if prev_warmup > 0 and remaining == 0 and self._device and not self._device.is_simulated:
            try:
                if self._device.maybe_ramp_sdrplay_sample_rate():
                    self.call_from_thread(
                        self._log,
                        f"[OK]   SDRplay: bandwidth {_format_bandwidth_hz(self.sample_rate)} activo",
                    )
            except Exception as exc:
                logger.warning("SDRplay ramp sample rate: %s", exc)
                self.call_from_thread(self._log, f"[WARN] SDRplay subida BW: {exc}")
        return capped

    def _on_rx_worker_crashed(self) -> None:
        """Restaura la UI del botón RX cuando el worker salió por error (hilo principal)."""
        try:
            btn = self.query_one("#btn_rx", Button)
            btn.label = ">> INICIAR RX"
            btn.variant = "success"
        except Exception:
            pass
        self._log("[WARN] RX detenido por error de hardware — verifica el dispositivo y pulsa INICIAR RX de nuevo")

    @work(thread=True)
    def _rx_worker(self, token: int) -> None:
        """Loop de recepcion en hilo separado."""
        from core.session_log import log_breadcrumb
        from core.startup_io import suppress_startup_output

        if token != self._rx_worker_token:
            self._rx_stop_event.set()
            return

        logger.info("RX worker iniciado")
        log_breadcrumb("rx.worker start")
        stream_started = False
        worker_error_handled = False
        try:
            if self._device and not self._device.is_simulated:
                if not self._ensure_sdrplay_rx_preflight():
                    worker_error_handled = True
                    self.call_from_thread(self._on_rx_worker_crashed)
                    return
                if not self._recover_sdrplay_service_for_rx(from_worker=True):
                    worker_error_handled = True
                    self.call_from_thread(self._on_rx_worker_crashed)
                    return
                if token != self._rx_worker_token or not self._rx_active:
                    return
                try:
                    log_breadcrumb("rx.worker before start_stream")
                    with suppress_startup_output():
                        self._device.start_stream(timeout=20.0)
                    stream_started = True
                    log_breadcrumb("rx.worker start_stream ok")
                except Exception as exc:
                    logger.exception("No se pudo iniciar stream RX: %s", exc)
                    worker_error_handled = True
                    detail = str(exc)
                    self.call_from_thread(self._on_sdrplay_stream_start_failed, detail)
                    return

            while self._rx_active and token == self._rx_worker_token:
                try:
                    run_rx_iteration(self)
                    time.sleep(0.002)
                except Exception as e:
                    if self._bandwidth_changing or not self._rx_active:
                        continue
                    logger.exception("RX error: %s", e)
                    self.call_from_thread(self._log, f"[ERROR] RX: {e}")
                    break
        finally:
            if stream_started and self._device and not self._device.is_simulated:
                try:
                    self._device.stop_stream(timeout=3.0)
                except Exception as exc:
                    logger.warning("Error deteniendo stream RX: %s", exc)
            if self._rx_active and token == self._rx_worker_token:
                self._rx_active = False
                if not worker_error_handled:
                    self.call_from_thread(self._on_rx_worker_crashed)
            self._rx_stop_event.set()
            logger.info("RX worker detenido")

    # ── Helpers ──────────────────────────────────────────────────────────────

    @property
    def active_demod_mode(self) -> str:
        """Modo de demodulación activo actual (resuelve 'auto' si está activo)."""
        if self.demod_mode == "auto":
            return self._resolve_auto_demod_mode(self.tuned_frequency)
        return self.demod_mode

    def _resolve_auto_demod_mode(self, frequency: float) -> str:
        return resolve_auto_demod_mode(frequency)

    def _sync_auto_demod_passband(self) -> None:
        """Actualiza PASS y UI cuando el modo AUTO resuelve otro demod."""
        if self.demod_mode != "auto":
            return
        resolved = self.active_demod_mode
        target_width = self._load_passband_width_for_mode(resolved)
        if abs(target_width - self.passband_width_hz) > 1.0:
            self.passband_width_hz = target_width
            self._sync_passband_widgets()

    def _update_mode_ui(self) -> None:
        """Actualiza la clase CSS activa en los botones de modo."""
        for m in self.DEMOD_MODES:
            try:
                btn = self.query_one(f"#btn_mode_{m}", Static)
                if m == self.demod_mode:
                    btn.add_class("active-mode")
                else:
                    btn.remove_class("active-mode")
            except Exception:
                pass

    def _apply_tuning(self) -> None:
        """Aplica la frecuencia sintonizada al dispositivo y actualiza UI."""
        if self._scanning and not getattr(self, "_is_scanner_stepping", False):
            self._stop_scanning()

        if self._device:
            self._device.set_frequency(self.tuned_frequency)

        # Actualizar input de frecuencia
        try:
            inp = self.query_one("#inp_freq", Input)
            inp.value = f"{self.tuned_frequency / 1e6:.4f}"
        except Exception:
            pass

        # Sincronizar viewport
        self._sync_viewport()
        self._sync_auto_demod_passband()

        # Actualizar subtitulo
        device_str = "SIM" if (self._device and self._device.is_simulated) else self.driver.upper()
        mode_upper = f"AUTO ({self.active_demod_mode.upper()})" if self.demod_mode == "auto" else self.demod_mode.upper()
        self.sub_title = f"{device_str} | {self.tuned_frequency / 1e6:.3f} MHz | {mode_upper}"

        self._update_status()

    def _update_status(self) -> None:
        """Actualiza la barra de estado con los valores actuales."""
        stream_drop_rate = 0.0
        stream_overflows = 0
        if self._rx_active and self._device and not self._device.is_simulated:
            stats = self._device.stream_stats
            stream_drop_rate = stats.drop_rate
            stream_overflows = stats.overflows

        try:
            device_str = "SIM" if (self._device and self._device.is_simulated) else self.driver
            mode_str = f"AUTO ({self.active_demod_mode.upper()})" if self.demod_mode == "auto" else self.demod_mode
            self.query_one("#status", StatusBar).update_status(
                freq=self.tuned_frequency,
                gain=self.gain_value,
                volume=self.volume_value,
                mode=mode_str,
                snr=self._last_snr,
                step=self.scroll_step,
                span=self.visible_span,
                bandwidth=self.sample_rate,
                passband_width=self.passband_width_hz,
                device=device_str,
                squelch_enabled=self.squelch_enabled,
                squelch_open=self._squelch_open,
                recording=self._recording,
                stream_drop_rate=stream_drop_rate,
                stream_overflows=stream_overflows,
            )
        except Exception:
            pass

    def _log(self, msg: str) -> None:
        """Escribe un mensaje en el panel de log con timestamp."""
        ts = time.strftime("%H:%M:%S")
        try:
            log = self.query_one("#log_panel", Log)
            log.write_line(f"[{ts}] {msg}")
        except Exception:
            pass

    def _load_bookmarks(self) -> list[tuple[str, float, str]]:
        """DEPRECATED: usa _storage.bookmarks (StorageController carga al init)."""
        return self._storage.bookmarks


# ─── Utilidades ──────────────────────────────────────────────────────────────

def bandwidth_select_options(rates: list[float]) -> list[tuple[str, float]]:
    """Opciones (etiqueta, valor) para el Select de bandwidth."""
    return [(_format_bandwidth_hz(rate), float(rate)) for rate in rates]


def build_visible_spans(sample_rate: float) -> list[float]:
    """Genera niveles de zoom válidos para un bandwidth IQ dado."""
    if sample_rate <= 0:
        return [100_000.0]

    spans = [float(step) for step in ZOOM_SPAN_STEPS if step <= sample_rate + 1.0]
    max_rate = float(sample_rate)

    if not spans or abs(spans[-1] - max_rate) > 1.0:
        spans.append(max_rate)

    # Ordenar y deduplicar manteniendo el máximo real del hardware
    unique = sorted(set(spans))
    if unique[-1] > max_rate:
        unique[-1] = max_rate
    return unique


def find_zoom_index(span: float, spans: list[float]) -> int:
    """Encuentra el índice de zoom más cercano a un span visible."""
    if not spans:
        return 0
    best_index = 0
    best_diff = float("inf")
    for index, candidate in enumerate(spans):
        diff = abs(candidate - span)
        if diff < best_diff:
            best_diff = diff
            best_index = index
    return best_index


def _format_hz(hz: float) -> str:
    """DEPRECATED: usa core.formatting.format_hz_compact()."""
    from core.formatting import format_hz_compact
    return format_hz_compact(hz)
