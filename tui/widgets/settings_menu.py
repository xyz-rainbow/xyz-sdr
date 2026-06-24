"""
xyz-sdr | tui/widgets/settings_menu.py
Pantalla modal de ajustes de hardware y software (SDR selector, Squelch, etc.).
"""

from __future__ import annotations

from typing import Optional
from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, Container
from textual.widgets import Label, Select, Button, Switch, Input
from textual.reactive import reactive

from tui.widgets.waterfall_timeline import WaterfallTimeline


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
    #page_recording {
        display: none;
    }
    #page_scanner {
        display: none;
    }
    #page_bookmarks {
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

    SettingsScreen.show-recording #page_main {
        display: none;
    }
    SettingsScreen.show-recording #page_recording {
        display: block;
    }

    SettingsScreen.show-scanner #page_main {
        display: none;
    }
    SettingsScreen.show-scanner #page_scanner {
        display: block;
    }

    SettingsScreen.show-bookmarks #page_main {
        display: none;
    }
    SettingsScreen.show-bookmarks #page_bookmarks {
        display: block;
    }

    #page_recording Label,
    #page_scanner Label,
    #page_bookmarks Label {
        width: 20;
    }

    #sw_record_iq,
    #sw_record_audio {
        margin-top: 1;
    }

    #set_scan_start,
    #set_scan_end,
    #set_scan_step,
    #set_scan_dwell,
    #set_scan_snr,
    #set_scan_pause_resume,
    #set_bookmarks_export,
    #set_bookmarks_import {
        width: 24;
        height: 3;
        background: #0b0f19;
        border: round #4338ca;
        color: #e0e7ff;
        padding: 0 1;
    }

    #sw_scan_pause,
    #sw_bookmarks_merge {
        margin-top: 1;
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

    #set_fm_deemphasis,
    #set_fm_agc_enabled {
        width: 29;
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
        self.remove_class("show-recording")
        self.remove_class("show-scanner")
        self.remove_class("show-bookmarks")
        if new_page == "hardware":
            self.add_class("show-hardware")
        elif new_page == "noise":
            self.add_class("show-noise")
        elif new_page == "recording":
            self.add_class("show-recording")
        elif new_page == "scanner":
            self.add_class("show-scanner")
        elif new_page == "bookmarks":
            self.add_class("show-bookmarks")

    def _refresh_bookmarks_count_label(self) -> None:
        try:
            lbl = self.query_one("#lbl_bookmarks_count", Label)
            lbl.update(f"Activos: {len(self.app._bookmarks)}")
        except Exception:
            pass

    def _squelch_select_value(self) -> int:
        opts = getattr(self.app, "SQUELCH_THRESHOLD_OPTIONS", [5, 10, 12, 15, 18, 20, 25, 30, 35, 40])
        thr = int(getattr(self.app, "squelch_threshold", 15))
        return thr if thr in opts else 15

    def _deemphasis_select_value(self) -> int:
        opts = getattr(self.app, "FM_DEEMPHASIS_OPTIONS", [50, 75])
        us = int(getattr(self.app, "fm_deemphasis_us", 50))
        return us if us in opts else 50

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
                yield Button("🔊 Audio FM / Noise", id="btn_go_noise", classes="nav-btn")
                yield Button("💾 Ajustes de Grabación", id="btn_go_recording", classes="nav-btn")
                yield Button("🔍 Ajustes del Escáner", id="btn_go_scanner", classes="nav-btn")
                yield Button("📋 Bookmarks", id="btn_go_bookmarks", classes="nav-btn")
                with Horizontal(classes="setting-row"):
                    yield Label("Efectos Sonido:")
                    yield Switch(value=self.app.audio_effects.enabled, id="sw_sound_effects")
                with Horizontal(classes="setting-row"):
                    yield Label("Waterfall auto:")
                    yield Switch(
                        value=getattr(self.app, "waterfall_auto_level", True),
                        id="sw_waterfall_auto_level",
                    )
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
                yield Label("🔊 AUDIO FM / NOISE", id="settings_title")
                with Horizontal(classes="setting-row"):
                    yield Label("De-emphasis:")
                    yield Select(
                        [
                            ("50 µs (EU)", 50),
                            ("75 µs (US)", 75),
                        ],
                        value=self._deemphasis_select_value(),
                        id="set_fm_deemphasis",
                    )
                with Horizontal(classes="setting-row"):
                    yield Label("AGC FM:")
                    yield Switch(
                        value=getattr(self.app, "fm_agc_enabled", True),
                        id="set_fm_agc_enabled",
                    )
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

            # ─── PÁGINA 4: AJUSTES DE GRABACIÓN ───
            with Container(id="page_recording"):
                yield Label("💾 AJUSTES DE GRABACIÓN", id="settings_title")
                with Horizontal(classes="setting-row"):
                    yield Label("Grabar IQ (SigMF):")
                    yield Switch(
                        value=bool(self.app.config.get("recorder", {}).get("record_iq", True)),
                        id="sw_record_iq",
                    )
                with Horizontal(classes="setting-row"):
                    yield Label("Grabar Audio (WAV):")
                    yield Switch(
                        value=bool(self.app.config.get("recorder", {}).get("record_audio", True)),
                        id="sw_record_audio",
                    )
                with Horizontal(classes="settings-actions"):
                    yield Button("Atrás", id="btn_back_to_main_rec")
                    yield Button("Aplicar", variant="success", id="btn_apply_recording")

            # ─── PÁGINA 5: AJUSTES DEL ESCÁNER ───
            with Container(id="page_scanner"):
                yield Label("🔍 AJUSTES DEL ESCÁNER", id="settings_title")
                scan_cfg = self.app.config.get("scanner", {})
                with Horizontal(classes="setting-row"):
                    yield Label("Frecuencia Inicio:")
                    yield Input(
                        value=f"{float(scan_cfg.get('freq_start', 88_000_000)) / 1e6:.3f}",
                        placeholder="MHz",
                        id="set_scan_start",
                    )
                with Horizontal(classes="setting-row"):
                    yield Label("Frecuencia Fin:")
                    yield Input(
                        value=f"{float(scan_cfg.get('freq_end', 108_000_000)) / 1e6:.3f}",
                        placeholder="MHz",
                        id="set_scan_end",
                    )
                with Horizontal(classes="setting-row"):
                    yield Label("Paso Escaneo:")
                    yield Input(
                        value=f"{float(scan_cfg.get('freq_step', 200_000)) / 1e3:.1f}",
                        placeholder="kHz",
                        id="set_scan_step",
                    )
                with Horizontal(classes="setting-row"):
                    yield Label("Dwell Time:")
                    yield Input(
                        value=f"{int(scan_cfg.get('dwell_ms', 500))}",
                        placeholder="ms",
                        id="set_scan_dwell",
                    )
                with Horizontal(classes="setting-row"):
                    yield Label("Umbral Min SNR:")
                    yield Input(
                        value=f"{float(scan_cfg.get('min_snr_db', 10.0)):.1f}",
                        placeholder="dB",
                        id="set_scan_snr",
                    )
                with Horizontal(classes="setting-row"):
                    yield Label("Pausa al detectar:")
                    yield Switch(
                        value=bool(scan_cfg.get("pause_on_signal", True)),
                        id="sw_scan_pause",
                    )
                with Horizontal(classes="setting-row"):
                    yield Label("Reanudar bajo SNR:")
                    yield Input(
                        value=f"{float(scan_cfg.get('pause_resume_snr_db', 7.0)):.1f}",
                        placeholder="dB",
                        id="set_scan_pause_resume",
                    )
                with Horizontal(classes="settings-actions"):
                    yield Button("Atrás", id="btn_back_to_main_scan")
                    yield Button("Aplicar", variant="success", id="btn_apply_scanner")

            # ─── PÁGINA 6: BOOKMARKS ───
            with Container(id="page_bookmarks"):
                yield Label("📋 BOOKMARKS", id="settings_title")
                yield Label(
                    f"Activos: {len(self.app._bookmarks)}",
                    id="lbl_bookmarks_count",
                )
                yield Label("Exportar a:")
                yield Input(
                    value="var/bookmarks_export.toml",
                    id="set_bookmarks_export",
                )
                yield Button("Exportar", id="btn_export_bookmarks", variant="primary")
                yield Label("Importar desde:")
                yield Input(
                    value="var/bookmarks_export.toml",
                    id="set_bookmarks_import",
                )
                with Horizontal(classes="setting-row"):
                    yield Label("Fusionar:")
                    yield Switch(value=True, id="sw_bookmarks_merge")
                yield Button("Importar", id="btn_import_bookmarks", variant="success")
                with Horizontal(classes="settings-actions"):
                    yield Button("Atrás", id="btn_back_to_main_bm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        # Efectos de sonido al pulsar botones
        if event.button.id in ("btn_apply_noise", "btn_apply_recording", "btn_apply_scanner"):
            self.app.audio_effects.play_chime()
        elif event.button.id in ("btn_export_bookmarks", "btn_import_bookmarks"):
            self.app.audio_effects.play_blip()
        elif event.button.id != "btn_apply_hardware":
            self.app.audio_effects.play_blip()

        # Navegación
        if event.button.id == "btn_go_hardware":
            self.current_page = "hardware"
        elif event.button.id == "btn_go_noise":
            self.current_page = "noise"
        elif event.button.id == "btn_go_recording":
            self.current_page = "recording"
        elif event.button.id == "btn_go_scanner":
            self.current_page = "scanner"
        elif event.button.id == "btn_go_bookmarks":
            self.current_page = "bookmarks"
            self._refresh_bookmarks_count_label()
        elif event.button.id in (
            "btn_back_to_main_hw",
            "btn_back_to_main_noise",
            "btn_back_to_main_rec",
            "btn_back_to_main_scan",
            "btn_back_to_main_bm",
        ):
            self.current_page = "main"
        elif event.button.id == "btn_close_settings":
            self.dismiss()

        # Acciones - Aplicar Grabación
        elif event.button.id == "btn_apply_recording":
            iq_val = self.query_one("#sw_record_iq", Switch).value
            audio_val = self.query_one("#sw_record_audio", Switch).value
            self.app._persist_recorder_config(record_iq=iq_val, record_audio=audio_val)
            self.app._log(
                f"[OK]   Grabación: IQ {'ON' if iq_val else 'OFF'}"
                f" | Audio {'ON' if audio_val else 'OFF'}"
            )
            self.current_page = "main"

        # Acciones - Aplicar Escáner
        elif event.button.id == "btn_apply_scanner":
            start_str = self.query_one("#set_scan_start", Input).value
            end_str = self.query_one("#set_scan_end", Input).value
            step_str = self.query_one("#set_scan_step", Input).value
            dwell_str = self.query_one("#set_scan_dwell", Input).value
            snr_str = self.query_one("#set_scan_snr", Input).value
            pause_val = self.query_one("#sw_scan_pause", Switch).value
            pause_resume_str = self.query_one("#set_scan_pause_resume", Input).value

            try:
                start_val = float(start_str) * 1e6
                end_val = float(end_str) * 1e6
                step_val = float(step_str) * 1e3
                dwell_val = float(dwell_str)
                snr_val = float(snr_str)
                pause_resume_val = float(pause_resume_str)
            except ValueError:
                self.app.audio_effects.play_error()
                self.app._log("[ERROR] Parámetros del escáner inválidos")
                return

            self.app._persist_scanner_config(
                freq_start=start_val,
                freq_end=end_val,
                freq_step=step_val,
                dwell_ms=dwell_val,
                min_snr_db=snr_val,
                pause_on_signal=bool(pause_val),
                pause_resume_snr_db=pause_resume_val,
            )
            self.app._log(
                f"[OK]   Escáner: {start_str} a {end_str} MHz"
                f" | Paso: {step_str} kHz | Dwell: {dwell_val:.0f} ms"
                f" | Min SNR: {snr_val:.1f} dB"
                f" | Pausa: {'ON' if pause_val else 'OFF'}"
                f" | Reanudar < {pause_resume_val:.1f} dB"
            )
            self.current_page = "main"

        elif event.button.id == "btn_export_bookmarks":
            export_path = self.query_one("#set_bookmarks_export", Input).value
            if self.app.export_bookmarks_to_path(export_path):
                self._refresh_bookmarks_count_label()

        elif event.button.id == "btn_import_bookmarks":
            import_path = self.query_one("#set_bookmarks_import", Input).value
            merge_val = self.query_one("#sw_bookmarks_merge", Switch).value
            if self.app.import_bookmarks_from_path(import_path, merge=bool(merge_val)):
                self._refresh_bookmarks_count_label()

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
            deemph_val = self.query_one("#set_fm_deemphasis", Select).value
            agc_val = self.query_one("#set_fm_agc_enabled", Switch).value
            squelch_val = self.query_one("#set_squelch_enabled", Switch).value
            threshold_val = self.query_one("#set_squelch_threshold", Select).value

            if deemph_val is not None and _valid_select_value(deemph_val):
                self.app.fm_deemphasis_us = float(deemph_val)
            self.app.fm_agc_enabled = bool(agc_val)
            self.app.squelch_enabled = squelch_val
            if threshold_val is not None and _valid_select_value(threshold_val):
                self.app.squelch_threshold = float(threshold_val)

            self.app._persist_dsp_config(
                squelch_enabled=squelch_val,
                squelch_threshold=self.app.squelch_threshold,
                fm_deemphasis_us=self.app.fm_deemphasis_us,
                fm_agc_enabled=self.app.fm_agc_enabled,
            )
            self.app._fm_agc.reset()
            self.app._squelch_gate.configure(
                threshold_db=self.app.squelch_threshold,
                hang_ms=self.app.squelch_hang_ms,
            )
            self.app.audio_effects.play_chime()
            self.app._log(
                f"[OK]   FM de-emphasis {self.app.fm_deemphasis_us:.0f} µs"
                f" | AGC {'ON' if self.app.fm_agc_enabled else 'OFF'}"
                f" | Squelch {'ON' if squelch_val else 'OFF'}"
                f" ({self.app.squelch_threshold:.0f} dB)"
            )
            self.app._update_status()

            self.current_page = "main"

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "sw_sound_effects":
            self.app.audio_effects.enabled = event.value
            self.app._log(f"[OK]   Efectos de sonido {'ACTIVADOS' if event.value else 'DESACTIVADOS'}")
            if event.value:
                self.app.audio_effects.play_blip()
        elif event.switch.id == "sw_waterfall_auto_level":
            self.app.waterfall_auto_level = bool(event.value)
            try:
                waterfall = self.app.query_one("#waterfall", WaterfallTimeline)
                waterfall.waterfall_auto_level = bool(event.value)
            except Exception:
                pass
            self.app._persist_display_config(waterfall_auto_level=bool(event.value))
            self.app._log(
                f"[OK]   Waterfall auto-level {'ON' if event.value else 'OFF'}"
            )
