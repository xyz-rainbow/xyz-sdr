"""
xyz-sdr | tui/app.py
Aplicacion principal Textual — TUI del controlador SDR.
v2: Timeline + Espectro + Waterfall con navegacion por teclado.
"""

from __future__ import annotations

import logging
import threading
import time
import numpy as np
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Container, VerticalScroll, VerticalGroup
from textual.widgets import (
    Header, Static, Label, Button,
    Select, Input, Log,
)
from textual.reactive import reactive
from textual import work, events

from core.device import SDRDevice, SampleRateError, BANDWIDTH_PRESETS, HardwareInitializationError, _format_bandwidth_hz
from core.config_store import patch_device_section
from core.band_buffer import BandFrameMailbox, make_band_frame
from core.dsp import average_psd, compute_rx_chunk_samples
from core.audio_effects import AudioEffects
from core.audio_output import AudioOutputQueue

from tui.widgets.frequency_timeline import FrequencyTimeline
from tui.widgets.spectrum_graph import SpectrumGraph
from tui.widgets.waterfall_timeline import WaterfallTimeline

logger = logging.getLogger(__name__)


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
VIEWPORT_DEBOUNCE_S = 0.05  # Coalesce zoom/scroll antes de re-slicear waterfall

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
        text.append("G", key)
        text.append(" Gain ", dim)
        text.append("V", key)
        text.append(" Vol ", dim)
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
        device: str,
    ) -> None:
        step_str = _format_hz(step)
        span_str = _format_hz(span)
        bw_str = _format_hz(bandwidth)
        
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
        
        text.append("DEV ", "bold #38bdf8")
        text.append(f"{device.upper()}", "bold #ffffff")

        self._append_key_hints(text)

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
    #controls #btn_rec {
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

    #waterfall_area {
        height: 1fr;
        layout: horizontal;
        align: left top;
    }

    #waterfall_speed_bar {
        width: 6;
        height: 100%;
        min-height: 0;
        background: transparent;
        border: none;
        border-left: solid #1e293b;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-size: 0 0;
        padding: 0;
        margin: 0;
        offset-x: -1;
    }

    #waterfall_speed_bar .speed-btn-stack {
        layout: vertical;
        height: auto;
        width: 100%;
        grid-gutter: 0 0;
        padding: 0;
        margin: 0;
        align: left top;
    }

    #waterfall_speed_bar Button.spd-btn {
        width: 100%;
        height: 1;
        min-height: 1;
        max-height: 1;
        min-width: 0;
        margin: 0;
        padding: 0;
        text-style: bold;
        text-align: center;
        content-align: center middle;
        box-sizing: content-box;
        background: #090d16;
        border: round #4338ca;
        border-top: round #4338ca;
        border-bottom: round #4338ca;
        border-left: round #4338ca;
        border-right: round #4338ca;
    }

    #waterfall_speed_bar Button.spd-btn:hover,
    #waterfall_speed_bar Button.spd-btn:focus,
    #waterfall_speed_bar Button.spd-btn.-active,
    #waterfall_speed_bar Button.spd-btn.-highlight {
        background: #090d16;
        background-tint: transparent;
        border: round #4338ca;
        border-top: round #4338ca;
        border-bottom: round #4338ca;
        border-left: round #4338ca;
        border-right: round #4338ca;
    }

    #waterfall_speed_bar Button.spd-a {
        color: #818cf8;
        border: round #4338ca;
        border-top: round #4338ca;
        border-bottom: round #4338ca;
        border-left: round #4338ca;
        border-right: round #4338ca;
    }

    #waterfall_speed_bar Button.spd-b {
        color: #c084fc;
        border: round #6d28d9;
        border-top: round #6d28d9;
        border-bottom: round #6d28d9;
        border-left: round #6d28d9;
        border-right: round #6d28d9;
    }

    #waterfall_speed_bar Button.spd-a:hover,
    #waterfall_speed_bar Button.spd-a:focus {
        color: #818cf8;
        border: round #4338ca;
        border-top: round #4338ca;
        border-bottom: round #4338ca;
        border-left: round #4338ca;
        border-right: round #4338ca;
    }

    #waterfall_speed_bar Button.spd-b:hover,
    #waterfall_speed_bar Button.spd-b:focus {
        color: #c084fc;
        border: round #6d28d9;
        border-top: round #6d28d9;
        border-bottom: round #6d28d9;
        border-left: round #6d28d9;
        border-right: round #6d28d9;
    }

    #waterfall_speed_bar Button.spd-btn.active-spd,
    #waterfall_speed_bar Button.spd-btn.active-spd:hover,
    #waterfall_speed_bar Button.spd-btn.active-spd:focus,
    #waterfall_speed_bar Button.spd-btn.active-spd.-active,
    #waterfall_speed_bar Button.spd-btn.active-spd.-highlight {
        background: #090d16;
        background-tint: transparent;
        color: #a3e635;
        border: round #10b981;
        border-top: round #10b981;
        border-bottom: round #10b981;
        border-left: round #10b981;
        border-right: round #10b981;
    }

    WaterfallTimeline {
        width: 1fr;
        height: 100%;
        min-height: 0;
        background: #090d16;
        border: round #6366f1;
        border-right: none;
    }

    #log_panel {
        width: 100%;
        border: round #38bdf8;
        background: #0f172a;
        height: 5;
        padding: 0 1;
        margin-bottom: 0;
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
        ("b",           "focus_bandwidth", "BW"),
        ("g",           "focus_gain",    "Gain"),
        ("v",           "focus_volume",  "Volumen"),
        ("r",           "record",        "Grabar"),
        ("escape",      "show_settings", "Ajustes"),
        ("q",           "quit",          "Salir"),
    ]

    TITLE = "xyz-sdr -- Terminal SDR Controller"
    SUB_TITLE = "SDRplay RSP1"

    DEMOD_MODES = ["wbfm", "nbfm", "am", "usb", "lsb", "cw", "dsb", "raw", "auto"]
    GAIN_OPTIONS = [0, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60]
    VOLUME_OPTIONS = [0, 10, 20, 30, 40, 50, 60, 70, 75, 80, 90, 100]
    SQUELCH_THRESHOLD_OPTIONS = [5, 10, 12, 15, 18, 20, 25, 30, 35, 40]

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
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.driver = driver
        self.demod_mode = demod_mode
        self.config = config or {}
        self.config_path = config_path
        self.debug_mode = debug_mode
        self._device: Optional[SDRDevice] = None
        self._rx_active = False
        self._recording = False
        self._audio_output: Optional[AudioOutputQueue] = None
        self.audio_effects = AudioEffects()

        # ── Estado del viewport ──
        self.tuned_frequency: float = float(center_freq)
        self.viewport_center: float = float(center_freq)
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
        self._bandwidth_changing = False
        self._rx_stop_event = threading.Event()
        self._rx_stop_event.set()
        self._display_width: int = 120
        self._band_mailbox = BandFrameMailbox()
        self._display_sequence: int = 0

        # Instrumentación --debug
        self._debug_lock = threading.Lock()
        self._debug_rx_proc_ms: list[float] = []
        self._debug_rx_iter_count: int = 0
        self._debug_display_frames: int = 0
        self._debug_ui_proc_ms: list[float] = []
        self._debug_frame_latency_ms: list[float] = []
        self._debug_last_viewport_ms: float = 0.0
        self._debug_report_window_start: float = time.time()
        self._viewport_debounce_timer = None

        dsp_cfg = self.config.get("dsp", {})
        self.squelch_enabled = bool(dsp_cfg.get("squelch_enabled", False))
        raw_squelch = dsp_cfg.get("squelch_threshold", dsp_cfg.get("squelch_db", 15))
        squelch_int = int(float(raw_squelch))
        if squelch_int not in self.SQUELCH_THRESHOLD_OPTIONS or squelch_int < 0:
            squelch_int = 15
        self.squelch_threshold = float(squelch_int)

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

                yield Label("-- PRESETS --", id="lbl_presets")
                yield Select(
                    [(name, f"{freq}:{mode}") for name, freq, mode in PRESETS],
                    prompt="Seleccionar...",
                    id="sel_preset",
                )

            # Panel derecho — visualizacion
            with Vertical(id="display_area"):
                yield FrequencyTimeline(id="timeline")
                yield SpectrumGraph(id="spectrum")
                with Horizontal(id="waterfall_area"):
                    yield WaterfallTimeline(
                        id="waterfall",
                        max_history=waterfall_max_history,
                        history_buffer_ratio=waterfall_buffer_ratio,
                    )
                    with VerticalScroll(id="waterfall_speed_bar", can_focus=True):
                        with VerticalGroup(classes="speed-btn-stack"):
                            for i, spd in enumerate(WATERFALL_SPEEDS):
                                yield Button(
                                    str(spd),
                                    id=f"btn_spd_{spd}",
                                    classes=f"spd-btn spd-{'a' if i % 2 == 0 else 'b'}",
                                )
                yield Log(id="log_panel", max_lines=200)

        yield StatusBar(id="status")

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._device = SDRDevice(driver=self.driver)
        self._device.open()
        self._device.set_frequency(self.tuned_frequency)
        self._device.set_gain(self.gain_value)
        self.sample_rate = self._device.sample_rate

        cfg_rate = self.config.get("device", {}).get("sample_rate")
        if cfg_rate is not None:
            cfg_rate = float(cfg_rate)
            if abs(cfg_rate - self.sample_rate) > 1.0 and self._device.is_sample_rate_supported(cfg_rate):
                self.change_bandwidth(cfg_rate)
            else:
                self._rebuild_zoom_levels()
                self._adapt_viewport_to_bandwidth()
        else:
            self._rebuild_zoom_levels()
            self._adapt_viewport_to_bandwidth()

        self._refresh_bandwidth_select()

        device_label = "SIMULACION" if self._device.is_simulated else self.driver.upper()
        self.sub_title = f"{device_label} | {self.tuned_frequency / 1e6:.3f} MHz"

        # Inicializar viewport de widgets
        self._sync_viewport(immediate=True)
        self._update_mode_ui()
        self._set_waterfall_speed(10)  # Establecer velocidad inicial de cascada (10 fps)

        log = self.query_one("#log_panel", Log)
        if self._device.is_simulated:
            log.write_line("[WARN] Hardware no detectado -- Modo SIMULACION activado")
            log.write_line("[INFO] Para usar hardware real instala PothosSDR + SDRplay API")
        else:
            log.write_line(f"[OK]   Dispositivo abierto: driver={self.driver}")

        log.write_line("[INFO] Pulsa [S] o el boton para iniciar recepcion")
        log.write_line(f"[INFO] Controles: <-/-> scroll | up/dn step | ctrl+<-/-> zoom | B bandwidth | espacio centrar")
        if self.debug_mode:
            log.write_line("[DEBUG] Instrumentación activa (FPS/latencia en panel cada ~3s con RX)")
        self._update_status()
        self.call_after_refresh(self._update_display_width)

        display_fps = float(self.config.get("dsp", {}).get("display_fps", 20))
        self.set_interval(1.0 / max(1.0, display_fps), self._flush_display_frames)
        if self.debug_mode:
            self.set_interval(3.0, self._report_debug_metrics)

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

    def _flush_display_frames(self) -> None:
        """Coalescing: aplica el frame más reciente al espectro y waterfall."""
        if not self._rx_active:
            return

        frame, snr, seq = self._band_mailbox.consume_if_new(self._display_sequence)
        if frame is None:
            return

        self._display_sequence = seq
        self._last_snr = snr

        ui_t0 = time.perf_counter()
        try:
            self.query_one("#spectrum", SpectrumGraph).set_band_frame(frame)
        except Exception:
            pass

        try:
            self.query_one("#waterfall", WaterfallTimeline).add_band_row(frame)
        except Exception:
            pass

        self._update_status()

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

            self._debug_rx_iter_count = 0
            self._debug_display_frames = 0
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

        if len(parts) > 1:
            self._log(" | ".join(parts))

    def on_resize(self, event: events.Resize) -> None:
        self._update_display_width()

    def _update_display_width(self) -> None:
        """Ancho de referencia; re-slicea espectro al redimensionar terminal."""
        try:
            spectrum = self.query_one("#spectrum", SpectrumGraph)
            width = spectrum.size.width
            if width > 0:
                self._display_width = width
                spectrum.set_viewport(self.viewport_center, self.visible_span)
        except Exception:
            pass

    def on_unmount(self) -> None:
        if self._rx_active:
            self._stop_rx()
        elif self._audio_output:
            self._audio_output.stop()
            self._audio_output = None
        if self._device:
            self._device.close()

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

        try:
            spectrum = self.query_one("#spectrum", SpectrumGraph)
            spectrum.set_viewport(self.viewport_center, self.visible_span)
        except Exception:
            pass

        try:
            waterfall = self.query_one("#waterfall", WaterfallTimeline)
            waterfall.set_viewport(self.viewport_center, self.visible_span)
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

    def _start_rx(self) -> None:
        if self._rx_active:
            return

        if not self._rx_stop_event.is_set():
            if not self._rx_stop_event.wait(timeout=3.0):
                self._log("[WARN] Worker RX previo no finalizó; continuando")
                self._rx_stop_event.set()

        self._rx_active = True
        self._rx_stop_event.clear()

        try:
            self._audio_output = AudioOutputQueue(sample_rate=48_000)
            self._audio_output.set_volume(self.volume_value / 100.0)
            self._audio_output.start()
            self._log("[OK]   Salida de audio iniciada (48 kHz, callback)")
        except Exception as e:
            self._audio_output = None
            self._log(f"[WARN] Sin salida de audio: {e}")

        try:
            btn = self.query_one("#btn_rx", Button)
            btn.label = "|| DETENER RX"
            btn.variant = "error"
        except Exception:
            pass
        self._log("RX iniciado")
        self._invalidate_band_cache()
        self._rx_worker()

    def _stop_rx(self) -> None:
        if not self._rx_active and self._rx_stop_event.is_set():
            return

        self._rx_active = False

        # Detener salida de audio
        if self._audio_output:
            try:
                self._audio_output.stop()
            except Exception:
                pass
            self._audio_output = None
            self._log("[INFO] Salida de audio detenida")

        if not self._rx_stop_event.wait(timeout=3.0):
            self._log("[WARN] Timeout esperando fin del worker RX")
            self._rx_stop_event.set()

        try:
            btn = self.query_one("#btn_rx", Button)
            btn.label = ">> INICIAR RX"
            btn.variant = "success"
        except Exception:
            pass
        self._log("RX detenido")

    # ── Otras acciones ───────────────────────────────────────────────────────

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
        self._update_mode_ui()
        self._log(f"Modo: {self.demod_mode.upper()}")
        self._update_status()

    def action_record(self) -> None:
        self._recording = not self._recording
        state = "INICIADA" if self._recording else "DETENIDA"
        self._log(f"Grabacion IQ {state}")

    def action_show_settings(self) -> None:
        """Abre el panel modal de Ajustes de Hardware SDR."""
        from tui.widgets.settings_menu import SettingsScreen
        self.push_screen(SettingsScreen())

    def action_quit(self) -> None:
        """Salida limpia con pantalla de cierre."""
        self._graceful_shutdown = True
        self.exit()

    def _persist_device_config(
        self,
        *,
        driver: str | None = None,
        sample_rate: float | None = None,
    ) -> None:
        """Guarda driver y/o sample_rate en el TOML de configuración."""
        try:
            patch_device_section(
                self.config_path,
                driver=driver,
                sample_rate=sample_rate,
                center_freq=self.tuned_frequency,
                gain=self.gain_value,
            )
            device_cfg = self.config.setdefault("device", {})
            if driver is not None:
                device_cfg["driver"] = driver
            if sample_rate is not None:
                device_cfg["sample_rate"] = int(sample_rate)
            device_cfg["center_freq"] = int(self.tuned_frequency)
            device_cfg["gain"] = float(self.gain_value)
        except Exception as exc:
            self._log(f"[WARN] No se pudo guardar config: {exc}")

    def change_device_driver(self, new_driver: str) -> bool:
        """Cambia dinámicamente el driver del dispositivo SDR en tiempo real."""
        if new_driver == "sim":
            new_driver = "simulated"

        if new_driver == self.driver:
            return True

        previous_driver = self.driver
        was_active = self._rx_active
        if was_active:
            self._stop_rx()

        if self._device:
            self._device.close()

        def _try_open(driver: str) -> None:
            self.driver = driver
            self._device = SDRDevice(driver=self.driver)
            self._device.open()
            self._device.set_frequency(self.tuned_frequency)
            self._device.set_gain(self.gain_value)

        try:
            _try_open(new_driver)
        except HardwareInitializationError as exc:
            self._log(f"[ERR]  {exc}")
            self.audio_effects.play_error()
            fallback = previous_driver or "simulated"
            try:
                _try_open(fallback)
                fb_label = "SIMULACION" if self._device.is_simulated else fallback.upper()
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

        if not self._device.is_sample_rate_supported(new_rate):
            supported = ", ".join(
                _format_bandwidth_hz(rate) for rate in self._device.get_supported_sample_rates()
            )
            self._log(f"[ERR]  Bandwidth no soportado. Opciones: {supported}")
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
        elif event.button.id and event.button.id.startswith("btn_spd_"):
            self.audio_effects.play_blip()
            speed_val = int(event.button.id.replace("btn_spd_", ""))
            self._set_waterfall_speed(speed_val)

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
                self.viewport_center = new_freq
                self._apply_tuning()
                self._log(f"Frecuencia: {self.tuned_frequency / 1e6:.4f} MHz")
            except ValueError:
                self.audio_effects.play_error()
                self._log(f"[ERROR] Frecuencia invalida: {event.value}")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "sel_gain" and event.value != Select.BLANK:
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

        elif event.select.id == "sel_volume" and event.value != Select.BLANK:
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

        elif event.select.id == "sel_bandwidth" and event.value != Select.BLANK:
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

        elif event.select.id == "sel_preset" and event.value != Select.BLANK:
            parts = str(event.value).split(":")
            if len(parts) == 2:
                self.tuned_frequency = float(parts[0])
                self.viewport_center = self.tuned_frequency
                self.demod_mode = parts[1]
                self._update_mode_ui()
                self._apply_tuning()
                self.audio_effects.play_blip()
                self._log(
                    f"Preset: {self.tuned_frequency / 1e6:.3f} MHz"
                    f" {self.demod_mode.upper()}"
                )

    def on_frequency_timeline_scroll_request(self, message: FrequencyTimeline.ScrollRequest) -> None:
        if message.direction > 0:
            self.action_scroll_right()
        else:
            self.action_scroll_left()

    def on_frequency_timeline_tune_request(self, message: FrequencyTimeline.TuneRequest) -> None:
        self.tuned_frequency = max(FREQ_MIN_HZ, min(FREQ_MAX_HZ, message.frequency_hz))
        self.viewport_center = self.tuned_frequency
        self._apply_tuning()
        self._log(f"Sintonizado: {self.tuned_frequency / 1e6:.4f} MHz")

    def on_frequency_timeline_zoom_request(self, message: FrequencyTimeline.ZoomRequest) -> None:
        if message.direction > 0:
            self.action_zoom_out()
        else:
            self.action_zoom_in()

    # ── RX Worker ────────────────────────────────────────────────────────────

    @work(thread=True)
    def _rx_worker(self) -> None:
        """Loop de recepcion en hilo separado."""
        logger.info("RX worker iniciado")

        dsp_cfg = self.config.get("dsp", {})
        fft_size = int(dsp_cfg.get("fft_size", 4096))
        num_avg = int(dsp_cfg.get("fft_avg_windows", 8))
        fft_overlap = float(dsp_cfg.get("fft_overlap", 0.5))
        band_cols = int(dsp_cfg.get("band_cache_cols", 512))

        try:
            while self._rx_active:
                if self._bandwidth_changing:
                    time.sleep(0.01)
                    continue

                capture_rate = float(self.sample_rate)
                capture_freq = float(self.tuned_frequency)
                capture_mode = self.demod_mode

                num_samples = compute_rx_chunk_samples(
                    fft_size=fft_size,
                    sample_rate=capture_rate,
                    num_avg=num_avg,
                )

                try:
                    samples = self._device.read_samples(num_samples)
                    if not self._rx_active or self._bandwidth_changing:
                        continue

                    proc_t0 = time.perf_counter()
                    _, psd = average_psd(
                        samples,
                        fft_size=fft_size,
                        sample_rate=capture_rate,
                        num_avg=num_avg,
                        overlap=fft_overlap,
                    )

                    snr = float(np.max(psd) - np.percentile(psd, 10))
                    frame = make_band_frame(
                        psd,
                        capture_freq,
                        capture_rate,
                        band_cols=band_cols,
                    )
                    self._band_mailbox.publish(frame, snr)

                    if self.debug_mode:
                        proc_ms = (time.perf_counter() - proc_t0) * 1000.0
                        with self._debug_lock:
                            self._debug_rx_iter_count += 1
                            self._debug_rx_proc_ms.append(proc_ms)
                            if len(self._debug_rx_proc_ms) > 120:
                                self._debug_rx_proc_ms.pop(0)

                    if self._audio_output and capture_mode in ["wbfm", "nbfm", "am", "usb", "lsb"]:
                        from core.dsp import demodulate
                        try:
                            audio = demodulate(
                                samples,
                                mode=capture_mode,
                                sample_rate=capture_rate,
                                audio_rate=48000,
                            )
                            self._audio_output.enqueue(audio)
                        except Exception as ae:
                            logger.error(f"Error en reproducción de audio: {ae}")

                except Exception as e:
                    if self._bandwidth_changing or not self._rx_active:
                        continue
                    logger.error(f"RX error: {e}")
                    self.call_from_thread(self._log, f"[ERROR] RX: {e}")
                    break
        finally:
            self._rx_stop_event.set()
            logger.info("RX worker detenido")

    # ── Helpers ──────────────────────────────────────────────────────────────

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
        self._update_mode_ui()

        # Actualizar subtitulo
        device_str = "SIM" if (self._device and self._device.is_simulated) else self.driver.upper()
        self.sub_title = f"{device_str} | {self.tuned_frequency / 1e6:.3f} MHz | {self.demod_mode.upper()}"

        self._update_status()

    def _update_status(self) -> None:
        """Actualiza la barra de estado con los valores actuales."""
        try:
            device_str = "SIM" if (self._device and self._device.is_simulated) else self.driver
            self.query_one("#status", StatusBar).update_status(
                freq=self.tuned_frequency,
                gain=self.gain_value,
                volume=self.volume_value,
                mode=self.demod_mode,
                snr=self._last_snr,
                step=self.scroll_step,
                span=self.visible_span,
                bandwidth=self.sample_rate,
                device=device_str,
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
    """Formatea Hz a cadena legible (kHz, MHz)."""
    if hz >= 1e6:
        return f"{hz / 1e6:.1f}M"
    elif hz >= 1e3:
        return f"{hz / 1e3:.0f}k"
    else:
        return f"{hz:.0f}Hz"
