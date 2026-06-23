"""
xyz-sdr | tui/widgets/settings_menu.py
Pantalla modal de ajustes de hardware y software (SDR selector, Squelch, etc.).
"""

from __future__ import annotations

from typing import Optional
from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, Container
from textual.widgets import Label, Select, Button, Switch
from textual.reactive import reactive


def _valid_select_value(value) -> bool:
    if value is None:
        return False
    blank = getattr(Select, "BLANK", object())
    if value is blank:
        return False
    null = getattr(Select, "NULL", None)
    if null is not None and value is null:
        return False
    return not str(value).startswith("Select.")


class SettingsScreen(ModalScreen):
    """Pantalla modal de ajustes general con navegación interna por páginas."""

    current_page = reactive("main")

    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
        background: rgba(9, 13, 22, 0.85);
    }

    #settings_card {
        width: 50;
        height: auto;
        background: #0b0f19;
        border: round #6366f1;
        padding: 1 2;
    }

    #settings_title {
        color: #c084fc;
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }

    /* ── Gestión de páginas ── */
    #page_main {
        display: block;
    }
    #page_hardware {
        display: none;
    }
    #page_noise {
        display: none;
    }

    SettingsScreen.show-hardware #page_main {
        display: none;
    }
    SettingsScreen.show-hardware #page_hardware {
        display: block;
    }

    SettingsScreen.show-noise #page_main {
        display: none;
    }
    SettingsScreen.show-noise #page_noise {
        display: block;
    }

    /* ── Estilos de los botones de navegación ── */
    #page_main Button.nav-btn {
        width: 100%;
        margin-top: 1;
        background: #1e1b4b;
        color: #a5b4fc;
        border: round #4338ca;
        height: 3;
    }

    #page_main Button.nav-btn:hover {
        background: #312e81;
        color: #ffffff;
        border: round #6366f1;
    }

    /* ── Filas de configuración ── */
    .setting-row {
        height: 3;
        margin-top: 1;
        layout: horizontal;
        align: left middle;
    }

    .setting-row Label {
        color: #a78bfa;
        text-style: bold;
        width: 15;
        height: 3;
        content-align: left middle;
    }

    #set_driver {
        width: 29;
    }

    #set_rx_active {
        margin-top: 1;
    }

    #set_squelch_threshold {
        width: 29;
    }

    #set_squelch_enabled {
        margin-top: 1;
    }

    .settings-actions {
        layout: horizontal;
        margin-top: 2;
        height: 3;
        align: right middle;
    }

    .settings-actions Button {
        margin-left: 1;
    }
    """

    BINDINGS = [("escape", "dismiss", "Cerrar")]

    def watch_current_page(self, new_page: str) -> None:
        self.remove_class("show-hardware")
        self.remove_class("show-noise")
        if new_page == "hardware":
            self.add_class("show-hardware")
        elif new_page == "noise":
            self.add_class("show-noise")

    def _squelch_select_value(self) -> int:
        opts = getattr(self.app, "SQUELCH_THRESHOLD_OPTIONS", [5, 10, 12, 15, 18, 20, 25, 30, 35, 40])
        thr = int(getattr(self.app, "squelch_threshold", 15))
        return thr if thr in opts else 15

    def compose(self) -> ComposeResult:
        # 1. Obtener lista de dispositivos SDR disponibles para página Hardware
        options = []
        from core.device import SDRDevice
        try:
            devs = SDRDevice.list_devices()
        except Exception:
            devs = []

        seen = set()
        for d in devs:
            drv = d.get("driver", "simulated")
            lbl = d.get("label", f"{drv.upper()} Detectado")
            options.append((lbl, drv))
            seen.add(drv)

        # Opciones estándar de respaldo
        defaults = [
            ("Auto (primer dispositivo)", "auto"),
            ("SDRplay RSP", "sdrplay"),
            ("RTL-SDR Dongle", "rtlsdr"),
            ("HackRF One", "hackrf"),
            ("Airspy", "airspy"),
            ("Simulación (Hardware)", "simulated")
        ]
        for lbl, drv in defaults:
            if drv not in seen:
                options.append((lbl, drv))
                seen.add(drv)

        current_driver = self.app.driver
        if current_driver == "simulated" or current_driver == "sim":
            current_driver = "simulated"

        with Container(id="settings_card"):
            # ─── PÁGINA 1: MENÚ PRINCIPAL ───
            with Container(id="page_main"):
                yield Label("⚙️ AJUSTES GENERALES", id="settings_title")
                yield Button("📡 Hardware SDR", id="btn_go_hardware", classes="nav-btn")
                yield Button("🔊 Eliminación de Ruido [Noise Removal]", id="btn_go_noise", classes="nav-btn")
                with Horizontal(classes="setting-row"):
                    yield Label("Efectos Sonido:")
                    yield Switch(value=self.app.audio_effects.enabled, id="sw_sound_effects")
                with Horizontal(classes="settings-actions"):
                    yield Button("Cerrar", id="btn_close_settings")

            # ─── PÁGINA 2: CONFIGURACIÓN HARDWARE ───
            with Container(id="page_hardware"):
                yield Label("📡 CONFIGURACIÓN HARDWARE", id="settings_title")
                with Horizontal(classes="setting-row"):
                    yield Label("SDR Driver:")
                    yield Select(options, value=current_driver, id="set_driver")
                with Horizontal(classes="setting-row"):
                    yield Label("Recepción (RX):")
                    yield Switch(value=self.app._rx_active, id="set_rx_active")
                with Horizontal(classes="settings-actions"):
                    yield Button("Atrás", id="btn_back_to_main_hw")
                    yield Button("Aplicar", variant="success", id="btn_apply_hardware")

            # ─── PÁGINA 3: ELIMINACIÓN DE RUIDO ───
            with Container(id="page_noise"):
                yield Label("🔊 NOISE REMOVAL", id="settings_title")
                with Horizontal(classes="setting-row"):
                    yield Label("Squelch:")
                    yield Switch(
                        value=getattr(self.app, "squelch_enabled", False),
                        id="set_squelch_enabled",
                    )
                with Horizontal(classes="setting-row"):
                    yield Label("Umbral Squelch:")
                    yield Select(
                        [(f"{db} dB", db) for db in self.app.SQUELCH_THRESHOLD_OPTIONS],
                        value=self._squelch_select_value(),
                        id="set_squelch_threshold",
                    )
                with Horizontal(classes="settings-actions"):
                    yield Button("Atrás", id="btn_back_to_main_noise")
                    yield Button("Aplicar", variant="success", id="btn_apply_noise")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        # Efectos de sonido al pulsar botones
        if event.button.id == "btn_apply_noise":
            self.app.audio_effects.play_chime()
        elif event.button.id != "btn_apply_hardware":
            self.app.audio_effects.play_blip()

        # Navegación
        if event.button.id == "btn_go_hardware":
            self.current_page = "hardware"
        elif event.button.id == "btn_go_noise":
            self.current_page = "noise"
        elif event.button.id in ("btn_back_to_main_hw", "btn_back_to_main_noise"):
            self.current_page = "main"
        elif event.button.id == "btn_close_settings":
            self.dismiss()

        # Acciones - Aplicar Hardware
        elif event.button.id == "btn_apply_hardware":
            driver_val = self.query_one("#set_driver", Select).value
            rx_val = self.query_one("#set_rx_active", Switch).value

            if driver_val in (None, Select.BLANK):
                self.app.audio_effects.play_error()
                self.app._log("[ERR]  Selecciona un driver SDR válido")
                return

            driver_ok = self.app.change_device_driver(str(driver_val))

            if not driver_ok:
                try:
                    current = "simulated" if self.app.driver in ("sim", "simulated") else self.app.driver
                    self.query_one("#set_driver", Select).value = current
                except Exception:
                    pass

            if driver_ok and rx_val != self.app._rx_active:
                if rx_val:
                    self.app._start_rx()
                else:
                    self.app._stop_rx()
            else:
                try:
                    self.query_one("#set_rx_active", Switch).value = self.app._rx_active
                except Exception:
                    pass

            if driver_ok:
                self.app.audio_effects.play_chime()

            self.current_page = "main"

        # Acciones - Aplicar Noise Removal
        elif event.button.id == "btn_apply_noise":
            squelch_val = self.query_one("#set_squelch_enabled", Switch).value
            threshold_val = self.query_one("#set_squelch_threshold", Select).value

            self.app.squelch_enabled = squelch_val
            if threshold_val is not None and _valid_select_value(threshold_val):
                self.app.squelch_threshold = float(threshold_val)

            self.app._persist_dsp_config(
                squelch_enabled=squelch_val,
                squelch_threshold=self.app.squelch_threshold,
            )
            self.app._squelch_gate.configure(
                threshold_db=self.app.squelch_threshold,
                hang_ms=self.app.squelch_hang_ms,
            )
            self.app.audio_effects.play_chime()
            self.app._log(
                f"[OK]   Squelch {'ACTIVADO' if squelch_val else 'DESACTIVADO'}"
                f" | Umbral: {self.app.squelch_threshold:.0f} dB"
            )
            self.app._update_status()

            self.current_page = "main"

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "sw_sound_effects":
            self.app.audio_effects.enabled = event.value
            self.app._log(f"[OK]   Efectos de sonido {'ACTIVADOS' if event.value else 'DESACTIVADOS'}")
            if event.value:
                self.app.audio_effects.play_blip()
