"""
xyz-sdr | tui/app.py
Aplicacion principal Textual — TUI del controlador SDR.
v2: Timeline + Espectro + Waterfall con navegacion por teclado.
"""

from __future__ import annotations

import logging
import time
import numpy as np
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Container
from textual.widgets import (
    Header, Footer, Static, Label, Button,
    Select, Input, Log,
)
from textual.reactive import reactive
from textual import work, events

from core.device import SDRDevice
from core.dsp import average_psd

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

# Anchos de banda visibles / zoom (Hz) — limitados a sample_rate para v1
VISIBLE_SPANS = [
    100_000, 200_000, 500_000, 1_000_000, 2_048_000,
]
DEFAULT_ZOOM_INDEX = 4  # 2.048 MHz (= sample_rate completo)

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
    """Barra de estado inferior con metricas en tiempo real."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: #0f172a;
        color: #e2e8f0;
        text-style: bold;
        padding: 0 1;
    }
    """

    def update_status(
        self,
        freq: float,
        gain: float,
        mode: str,
        snr: float,
        step: float,
        span: float,
        device: str,
    ) -> None:
        step_str = _format_hz(step)
        span_str = _format_hz(span)
        
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
        
        text.append("GAIN ", "bold #fbbf24")
        text.append(f"{gain:.0f} dB", "bold #ffffff")
        text.append(" ┃ ", "#475569")
        
        text.append("MODE ", "bold #f472b6")
        text.append(f"{mode.upper()}", "bold #ffffff")
        text.append(" ┃ ", "#475569")
        
        text.append("SNR ", "bold #34d399")
        text.append(f"{snr:.1f} dB", "bold #ffffff")
        text.append(" ┃ ", "#475569")
        
        text.append("DEV ", "bold #38bdf8")
        text.append(f"{device.upper()}", "bold #ffffff")
        
        self.update(text)


# ─── App Principal ───────────────────────────────────────────────────────────

class XyzSDRApp(App):
    """xyz-sdr Terminal SDR Controller v2."""

    CSS = """
    Screen {
        background: #090d16;
    }

    Header {
        background: #0f172a;
        color: #c084fc;
        text-style: bold;
        border-bottom: solid #6366f1;
    }

    Footer {
        background: #0f172a;
        color: #38bdf8;
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
        background: #1e1b4b;
        border: round #4338ca;
        color: #e0e7ff;
    }

    #controls Input:focus {
        border: round #818cf8;
        background: #2e1065;
    }

    #controls Select {
        border: round #4338ca;
        background: #1e1b4b;
    }

    #controls Select:focus {
        border: round #818cf8;
    }

    #controls Button {
        width: 100%;
        margin-top: 1;
        background: #3b0764;
        color: #f5f3ff;
        border: round #7c3aed;
        height: 3;
    }

    #controls Button:hover {
        background: #6b21a8;
        border: round #a855f7;
    }

    #controls Button.-primary {
        background: #064e3b;
        color: #ecfdf5;
        border: round #10b981;
    }

    #controls Button.-primary:hover {
        background: #047857;
        border: round #34d399;
    }

    #controls Button.-error {
        background: #7f1d1d;
        color: #fef2f2;
        border: round #dc2626;
    }

    #controls Button.-error:hover {
        background: #b91c1c;
        border: round #f87171;
    }

    /* ── Matriz 3x3 de modos demod ── */
    .mode-grid {
        layout: grid;
        grid-size: 3 3;
        grid-columns: 1fr 1fr 1fr;
        grid-rows: 3 3 3;
        grid-gutter: 0 1;
        height: 11;
        margin-top: 1;
        min-height: 11;
    }

    .mode-grid Static {
        width: 100%;
        height: 3;
        padding: 0;
        margin: 0;
        background: #1e1b4b;
        color: #a5b4fc;
        border: round #4338ca;
        content-align: center middle;
        text-style: bold;
    }

    .mode-grid Static:hover {
        background: #312e81;
        color: #e0e7ff;
        border: round #6366f1;
    }

    .mode-grid Static.active-mode {
        background: #10b981;
        color: #ffffff;
        border: round #34d399;
        text-style: bold;
    }

    .mode-grid Static.active-mode:hover {
        background: #059669;
        border: round #6ee7b7;
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
    }

    #waterfall_speed_bar {
        width: 7;
        background: #0b0f19;
        border-left: solid #1e293b;
        align: center top;
        padding: 0;
    }

    #waterfall_speed_bar Label {
        color: #818cf8;
        text-style: bold;
        text-align: center;
        margin-top: 1;
        width: 100%;
    }

    .spd-btn {
        width: 5;
        min-width: 5;
        height: 1;
        min-height: 1;
        margin-top: 1;
        padding: 0;
        background: #1e1b4b;
        color: #a5b4fc;
        border: none;
        text-align: center;
        content-align: center middle;
    }

    .spd-btn:hover {
        background: #312e81;
        color: #ffffff;
    }

    .spd-btn.active-spd {
        background: #10b981;
        color: #ffffff;
        text-style: bold;
    }

    WaterfallTimeline {
        width: 1fr;
        height: 100%;
        background: #090d16;
        border: round #6366f1;
    }

    #log_panel {
        border: round #38bdf8;
        background: #0f172a;
        height: 5;
        padding: 0 1;
    }

    StatusBar {
        height: 1;
        background: #0f172a;
        color: #e2e8f0;
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
        ("g",           "focus_gain",    "Gain"),
        ("r",           "record",        "Grabar"),
        ("escape",      "show_settings", "Ajustes"),
        ("q",           "quit",          "Salir"),
    ]

    TITLE = "xyz-sdr -- Terminal SDR Controller"
    SUB_TITLE = "SDRplay RSP1"

    DEMOD_MODES = ["wbfm", "nbfm", "am", "usb", "lsb", "cw", "dsb", "raw", "auto"]
    GAIN_OPTIONS = [0, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60]

    # ── Inicializacion ───────────────────────────────────────────────────────

    def __init__(
        self,
        driver: str = "sdrplay",
        center_freq: float = 100_600_000,
        gain: float = 40.0,
        demod_mode: str = "wbfm",
        config: dict = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.driver = driver
        self.demod_mode = demod_mode
        self.config = config or {}
        self._device: Optional[SDRDevice] = None
        self._rx_active = False
        self._recording = False
        self._audio_stream = None

        # ── Estado del viewport ──
        self.tuned_frequency: float = float(center_freq)
        self.viewport_center: float = float(center_freq)
        self.visible_span: float = float(VISIBLE_SPANS[DEFAULT_ZOOM_INDEX])
        self.scroll_step: float = float(SCROLL_STEPS[DEFAULT_STEP_INDEX])
        self.step_index: int = DEFAULT_STEP_INDEX
        self.zoom_index: int = DEFAULT_ZOOM_INDEX
        self.gain_value: float = float(gain)
        self.sample_rate: float = 2_048_000.0
        self._last_snr: float = 0.0

    # ── Layout ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
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

                yield Label("-- GANANCIA (dB) --")
                yield Select(
                    [(f"{g} dB", g) for g in self.GAIN_OPTIONS],
                    value=int(self.gain_value) if int(self.gain_value) in self.GAIN_OPTIONS else self.GAIN_OPTIONS[-1],
                    id="sel_gain",
                )

                yield Label("-- MODO DEMOD --")
                with Container(classes="mode-grid"):
                    for m in self.DEMOD_MODES:
                        yield Static(m.upper(), id=f"btn_mode_{m}")

                yield Label("-- PRESETS --")
                yield Select(
                    [(name, f"{freq}:{mode}") for name, freq, mode in PRESETS],
                    prompt="Seleccionar...",
                    id="sel_preset",
                )

                yield Button(">> INICIAR RX", id="btn_rx", variant="success")
                yield Button("(o) GRABAR IQ", id="btn_rec", variant="warning")

            # Panel derecho — visualizacion
            with Vertical(id="display_area"):
                yield FrequencyTimeline(id="timeline")
                yield SpectrumGraph(id="spectrum")
                with Horizontal(id="waterfall_area"):
                    yield WaterfallTimeline(id="waterfall")
                    with Vertical(id="waterfall_speed_bar"):
                        yield Label("SPD")
                        for spd in [1, 2, 3, 5, 10, 25, 50]:
                            yield Button(str(spd), id=f"btn_spd_{spd}", classes="spd-btn")
                yield Log(id="log_panel", max_lines=200)

        yield StatusBar(id="status")
        yield Footer()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._device = SDRDevice(driver=self.driver)
        self._device.open()
        self.sample_rate = self._device.sample_rate

        device_label = "SIMULACION" if self._device.is_simulated else self.driver.upper()
        self.sub_title = f"{device_label} | {self.tuned_frequency / 1e6:.3f} MHz"

        # Inicializar viewport de widgets
        self._sync_viewport()
        self._update_mode_ui()
        self._set_waterfall_speed(10)  # Establecer velocidad inicial de cascada (10 fps)

        log = self.query_one("#log_panel", Log)
        if self._device.is_simulated:
            log.write_line("[WARN] Hardware no detectado -- Modo SIMULACION activado")
            log.write_line("[INFO] Para usar hardware real instala PothosSDR + SDRplay API")
        else:
            log.write_line(f"[OK]   Dispositivo abierto: driver={self.driver}")

        log.write_line("[INFO] Pulsa [S] o el boton para iniciar recepcion")
        log.write_line(f"[INFO] Controles: <-/-> scroll | up/dn step | ctrl+<-/-> zoom | espacio centrar")
        self._update_status()

    def on_unmount(self) -> None:
        self._rx_active = False
        if self._device:
            self._device.close()

    # ── Sincronizacion del Viewport ──────────────────────────────────────────

    def _sync_viewport(self) -> None:
        """Propaga el estado del viewport a los 3 widgets de visualizacion."""
        try:
            timeline = self.query_one("#timeline", FrequencyTimeline)
            timeline.viewport_center_hz = self.viewport_center
            timeline.visible_span_hz = self.visible_span
            timeline.tuned_freq_hz = self.tuned_frequency
        except Exception:
            pass

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
            self.visible_span = float(VISIBLE_SPANS[self.zoom_index])
            self._sync_viewport()
            self._log(f"Zoom: {_format_hz(self.visible_span)}")
            self._update_status()

    def action_zoom_out(self) -> None:
        """Zoom out: muestra mas ancho de banda (menor resolucion)."""
        if self.zoom_index < len(VISIBLE_SPANS) - 1:
            self.zoom_index += 1
            self.visible_span = float(VISIBLE_SPANS[self.zoom_index])
            self._sync_viewport()
            self._log(f"Zoom: {_format_hz(self.visible_span)}")
            self._update_status()

    # ── Centrado (Espacio) ───────────────────────────────────────────────────

    def action_center_view(self) -> None:
        """Centra el viewport en la frecuencia sintonizada actual."""
        self.viewport_center = self.tuned_frequency
        self._sync_viewport()
        self._log("Vista centrada")

    # ── RX Start/Stop ────────────────────────────────────────────────────────

    def action_toggle_rx(self) -> None:
        if self._rx_active:
            self._stop_rx()
        else:
            self._start_rx()

    def _start_rx(self) -> None:
        self._rx_active = True

        # Inicializar salida de audio con sounddevice
        import sounddevice as sd
        try:
            self._audio_stream = sd.OutputStream(
                samplerate=48000,
                channels=1,
                dtype='float32',
            )
            self._audio_stream.start()
            self._log("[OK]   Salida de audio iniciada (48 kHz)")
        except Exception as e:
            self._audio_stream = None
            self._log(f"[WARN] Sin salida de audio: {e}")

        btn = self.query_one("#btn_rx", Button)
        btn.label = "|| DETENER RX"
        btn.variant = "error"
        self._log("RX iniciado")
        self._rx_worker()

    def _stop_rx(self) -> None:
        self._rx_active = False

        # Detener salida de audio
        if self._audio_stream:
            try:
                self._audio_stream.stop()
                self._audio_stream.close()
            except Exception:
                pass
            self._audio_stream = None
            self._log("[INFO] Salida de audio detenida")

        btn = self.query_one("#btn_rx", Button)
        btn.label = ">> INICIAR RX"
        btn.variant = "success"
        self._log("RX detenido")

    # ── Otras acciones ───────────────────────────────────────────────────────

    def action_focus_freq(self) -> None:
        self.query_one("#inp_freq", Input).focus()

    def action_focus_gain(self) -> None:
        self.query_one("#sel_gain", Select).focus()

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

    def change_device_driver(self, new_driver: str) -> None:
        """Cambia dinámicamente el driver del dispositivo SDR en tiempo real."""
        if new_driver == self.driver:
            return

        was_active = self._rx_active
        if was_active:
            self._stop_rx()

        if self._device:
            self._device.close()

        self.driver = new_driver
        self._device = SDRDevice(driver=self.driver)
        self._device.open()
        self.sample_rate = self._device.sample_rate

        self._sync_viewport()
        
        device_str = "SIMULACION" if self._device.is_simulated else self.driver.upper()
        self.sub_title = f"{device_str} | {self.tuned_frequency / 1e6:.3f} MHz"
        self._log(f"[OK]   Cambiado a driver: {device_str}")

        if was_active:
            self._start_rx()
        else:
            self._update_status()

    # ── Eventos UI ───────────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_rx":
            self.action_toggle_rx()
        elif event.button.id == "btn_rec":
            self.action_record()
        elif event.button.id and event.button.id.startswith("btn_spd_"):
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
        for s in [1, 2, 3, 5, 10, 25, 50]:
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
            mode = event.widget.id.replace("btn_mode_", "")
            self.demod_mode = mode
            self._update_mode_ui()
            self._log(f"Modo: {self.demod_mode.upper()}")
            self._update_status()

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
                self._log(f"[ERROR] Frecuencia invalida: {event.value}")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "sel_gain" and event.value != Select.BLANK:
            try:
                self.gain_value = float(event.value)
                if self._device:
                    self._device.set_gain(self.gain_value)
                self._log(f"Ganancia: {self.gain_value:.0f} dB")
                self._update_status()
            except ValueError:
                self._log(f"[ERROR] Ganancia invalida: {event.value}")

        elif event.select.id == "sel_preset" and event.value != Select.BLANK:
            parts = str(event.value).split(":")
            if len(parts) == 2:
                self.tuned_frequency = float(parts[0])
                self.viewport_center = self.tuned_frequency
                self.demod_mode = parts[1]
                self._update_mode_ui()
                self._apply_tuning()
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

        fft_size = self.config.get("dsp", {}).get("fft_size", 4096)
        num_samples = fft_size * 16

        while self._rx_active:
            try:
                samples = self._device.read_samples(num_samples)
                freqs_mhz, psd = average_psd(
                    samples,
                    fft_size=fft_size,
                    sample_rate=self.sample_rate,
                )

                capture_center = self.tuned_frequency

                # Actualizar espectro
                self.call_from_thread(
                    self.query_one("#spectrum", SpectrumGraph).update_data,
                    freqs_mhz,
                    psd,
                    capture_center,
                )

                # Actualizar waterfall
                self.call_from_thread(
                    self.query_one("#waterfall", WaterfallTimeline).add_row,
                    capture_center,
                    self.sample_rate,
                    psd,
                )

                # Demodulación y salida de audio en tiempo real
                if self._audio_stream and self.demod_mode in ["wbfm", "nbfm", "am", "usb", "lsb"]:
                    from core.dsp import demodulate
                    try:
                        audio = demodulate(
                            samples,
                            mode=self.demod_mode,
                            sample_rate=self.sample_rate,
                            audio_rate=48000,
                        )
                        self._audio_stream.write(audio)
                    except Exception as ae:
                        logger.error(f"Error en reproducción de audio: {ae}")

                # Actualizar SNR y status
                snr = float(np.max(psd) - np.percentile(psd, 10))
                self._last_snr = snr
                self.call_from_thread(self._update_status)

            except Exception as e:
                logger.error(f"RX error: {e}")
                self.call_from_thread(self._log, f"[ERROR] RX: {e}")
                break

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
                mode=self.demod_mode,
                snr=self._last_snr,
                step=self.scroll_step,
                span=self.visible_span,
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

def _format_hz(hz: float) -> str:
    """Formatea Hz a cadena legible (kHz, MHz)."""
    if hz >= 1e6:
        return f"{hz / 1e6:.1f}M"
    elif hz >= 1e3:
        return f"{hz / 1e3:.0f}k"
    else:
        return f"{hz:.0f}Hz"
