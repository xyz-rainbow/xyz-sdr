"""
xyz-sdr | tui/widgets/settings_menu.py
Pantalla modal de ajustes de hardware (SDR selector, Play/Stop).
"""

from __future__ import annotations

from typing import Optional
from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, Container
from textual.widgets import Label, Select, Button, Switch


class SettingsScreen(ModalScreen):
    """Pantalla modal de ajustes de hardware SDR."""

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

    def compose(self) -> ComposeResult:
        # Obtener lista de dispositivos SDR disponibles
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
            yield Label("⚙️ AJUSTES DE HARDWARE", id="settings_title")
            
            with Horizontal(classes="setting-row"):
                yield Label("SDR Driver:")
                yield Select(options, value=current_driver, id="set_driver")
                
            with Horizontal(classes="setting-row"):
                yield Label("Recepción (RX):")
                yield Switch(value=self.app._rx_active, id="set_rx_active")

            with Horizontal(classes="settings-actions"):
                yield Button("Cancelar", variant="default", id="btn_cancel")
                yield Button("Aplicar", variant="success", id="btn_apply")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_cancel":
            self.dismiss()
        elif event.button.id == "btn_apply":
            driver_val = self.query_one("#set_driver", Select).value
            rx_val = self.query_one("#set_rx_active", Switch).value

            # Normalizar driver
            if driver_val == "simulated":
                driver_val = "simulated"

            # Aplicar cambios al driver de la app
            self.app.change_device_driver(driver_val)

            # Cambiar estado de recepción si difiere del actual
            if rx_val != self.app._rx_active:
                if rx_val:
                    self.app._start_rx()
                else:
                    self.app._stop_rx()

            self.dismiss()
