"""
xyz-sdr | tui/widgets/settings_menu.py
Pantalla modal de ajustes de hardware y software (SDR selector, Squelch, etc.).
"""

from __future__ import annotations

from typing import Optional
from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, Container
from textual.widgets import Label, Select, Button, Switch, Input, Static
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
        width: 100;
        max-width: 98%;
        height: auto;
        background: #0b0f19;
        border: round #6366f1;
        padding: 0 1;
    }

    #settings_title {
        color: #c084fc;
        text-style: bold;
        text-align: center;
        margin: 0 0 1 0;
        height: 1;
    }

    #settings_title_compact {
        color: #c084fc;
        text-style: bold;
        text-align: center;
        margin: 0;
        height: 1;
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
        width: 1fr;
        min-width: 12;
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
    #page_main .nav-grid-row {
        layout: horizontal;
        height: auto;
        margin-top: 0;
    }

    #page_main .nav-grid-main {
        height: 3;
    }

    #page_main Button.nav-btn {
        width: 1fr;
        min-width: 14;
        margin-top: 0;
        margin-right: 1;
        background: #1e1b4b;
        color: #a5b4fc;
        border: round #4338ca;
        height: 3;
        padding: 0 1;
    }

    #page_main .main-footer-row {
        layout: horizontal;
        height: 3;
        margin-top: 1;
        align: left middle;
    }

    #page_main .main-footer-row Label {
        color: #a78bfa;
        width: auto;
        min-width: 10;
        height: 3;
        margin-right: 1;
    }

    #page_main .main-footer-row Switch {
        margin-right: 2;
    }

    #page_main #btn_close_settings {
        margin-left: 1;
    }

    #page_main Button.nav-btn:hover {
        background: #312e81;
        color: #ffffff;
        border: round #6366f1;
    }

    /* ── Filas de configuración ── */
    .setting-row {
        height: auto;
        min-height: 3;
        margin-top: 0;
        layout: horizontal;
        align: left middle;
    }

    .setting-row-wide {
        height: auto;
        min-height: 3;
        margin-top: 0;
        layout: horizontal;
        align: left middle;
    }

    .setting-row Label,
    .setting-row-wide Label {
        color: #a78bfa;
        text-style: bold;
        width: 14;
        height: 3;
        content-align: left middle;
    }

    .hardware-columns {
        layout: horizontal;
        height: auto;
        margin-top: 0;
    }

    .hardware-col {
        width: 1fr;
        height: auto;
        margin-right: 1;
    }

    .hardware-col-last {
        width: 1fr;
        height: auto;
    }

    .hardware-section {
        border: round #312e81;
        background: #0f1424;
        padding: 0 1;
        margin-top: 0;
        height: auto;
    }

    .section-title {
        color: #c4b5fd;
        text-style: bold;
        margin: 0;
        width: 100%;
        height: 1;
    }

    .hint-label {
        color: #64748b;
        height: 1;
        margin: 0;
        padding: 0;
    }

    #lbl_device_detail {
        color: #e2e8f0;
        height: auto;
        min-height: 2;
        padding: 0;
        margin: 0;
    }

    #sdr_diagnose_panel {
        color: #94a3b8;
        height: auto;
        min-height: 3;
        max-height: 5;
        padding: 0;
        margin: 0;
    }

    #set_driver {
        width: 1fr;
        min-width: 28;
    }

    #set_rx_active {
        margin-top: 1;
    }

    #set_squelch_threshold {
        width: 1fr;
        min-width: 28;
    }

    #set_squelch_enabled {
        margin-top: 1;
    }

    #set_fm_deemphasis,
    #set_fm_agc_enabled {
        width: 1fr;
        min-width: 28;
    }

    .noise-grid {
        layout: grid;
        grid-size: 2 2;
        grid-gutter: 0 1;
        height: auto;
        margin-top: 0;
    }

    .noise-grid .setting-row {
        margin: 0;
    }

    .scanner-grid {
        layout: grid;
        grid-size: 2 3;
        grid-gutter: 0 1;
        height: auto;
    }

    .scanner-grid .setting-row {
        margin: 0;
    }

    .settings-actions {
        layout: horizontal;
        margin-top: 1;
        height: 3;
        align: right middle;
    }

    .settings-actions.compact-actions {
        margin-top: 0;
        height: 3;
        align: left middle;
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
            self.call_after_refresh(self._refresh_hardware_page, False)
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

    @staticmethod
    def _trim_line(text: str, max_len: int = 64) -> str:
        raw = str(text or "").strip()
        if len(raw) <= max_len:
            return raw
        return raw[: max_len - 3].rstrip() + "..."

    def refresh_sdrplay_wizard(self, attempt_recover: bool = False) -> None:
        """Actualiza el panel de diagnóstico SDRplay."""
        try:
            lines = self.app.sdrplay_wizard_lines(attempt_recover=attempt_recover)
        except Exception as exc:
            lines = [f"Error diagnóstico: {exc}"]
        try:
            panel = "\n".join(self._trim_line(line, 66) for line in lines[:4])
            self.query_one("#sdr_diagnose_panel", Static).update(panel)
        except Exception:
            pass

    def refresh_device_detail(self) -> None:
        """Ficha del dispositivo bajo el selector de driver."""
        from core.device import resolve_settings_device_display

        try:
            driver_sel = self.query_one("#set_driver", Select)
            token = str(driver_sel.value) if _valid_select_value(driver_sel.value) else None
        except Exception:
            token = None
        simulated = bool(self.app._device and self.app._device.is_simulated)
        lines = resolve_settings_device_display(
            token,
            getattr(self, "_driver_select_map", {}),
            getattr(self.app, "_cached_sdr_devices", None),
            current_driver=self.app.driver,
            simulated=simulated,
        )
        try:
            panel = "\n".join(self._trim_line(line, 54) for line in lines[:2])
            self.query_one("#lbl_device_detail", Static).update(panel)
        except Exception:
            pass

    def _refresh_hardware_page(self, attempt_recover: bool = False) -> None:
        if attempt_recover:
            try:
                self.app._refresh_enumerated_devices_if_safe()
            except Exception:
                pass
        self.refresh_device_detail()
        self.refresh_sdrplay_wizard(attempt_recover=attempt_recover)

    def _squelch_select_value(self) -> int:
        opts = getattr(self.app, "SQUELCH_THRESHOLD_OPTIONS", [5, 10, 12, 15, 18, 20, 25, 30, 35, 40])
        thr = int(getattr(self.app, "squelch_threshold", 15))
        return thr if thr in opts else 15

    def _deemphasis_select_value(self) -> int:
        opts = getattr(self.app, "FM_DEEMPHASIS_OPTIONS", [50, 75])
        us = int(getattr(self.app, "fm_deemphasis_us", 50))
        return us if us in opts else 50

    def compose(self) -> ComposeResult:
        from core.device import build_driver_select_options

        devs = list(getattr(self.app, "_cached_sdr_devices", None) or [])

        active_kwargs = (
            self.app._device._device_kwargs
            if self.app._device and self.app._device._device_kwargs
            else None
        )
        driver_options, self._driver_select_map, selected_driver = build_driver_select_options(
            devs,
            current_driver=self.app.driver,
            active_kwargs=active_kwargs,
        )

        with Container(id="settings_card"):
            # ─── PÁGINA 1: MENÚ PRINCIPAL ───
            with Container(id="page_main"):
                yield Label("⚙️ AJUSTES", id="settings_title_compact")
                with Horizontal(classes="nav-grid-row nav-grid-main"):
                    yield Button("📡 HW", id="btn_go_hardware", classes="nav-btn")
                    yield Button("🔊 Audio", id="btn_go_noise", classes="nav-btn")
                    yield Button("💾 IQ/WAV", id="btn_go_recording", classes="nav-btn")
                    yield Button("🔍 Scan", id="btn_go_scanner", classes="nav-btn")
                    yield Button("📋 Marks", id="btn_go_bookmarks", classes="nav-btn")
                with Horizontal(classes="main-footer-row"):
                    yield Label("FX:")
                    yield Switch(value=self.app.audio_effects.enabled, id="sw_sound_effects")
                    yield Label("WF:")
                    yield Switch(
                        value=getattr(self.app, "waterfall_auto_level", True),
                        id="sw_waterfall_auto_level",
                    )
                    yield Button("Cerrar", id="btn_close_settings")

            # ─── PÁGINA 2: CONFIGURACIÓN HARDWARE ───
            with Container(id="page_hardware"):
                yield Label("📡 HARDWARE", id="settings_title_compact")

                with Horizontal(classes="hardware-columns"):
                    with Container(classes="hardware-col hardware-section"):
                        yield Label("Dispositivo", classes="section-title")
                        with Horizontal(classes="setting-row-wide"):
                            yield Label("Driver:")
                            yield Select(driver_options, value=selected_driver, id="set_driver")
                        yield Static("", id="lbl_device_detail")
                        yield Label("Caché arranque · Actualizar = vivo", classes="hint-label")

                    with Container(classes="hardware-col-last hardware-section"):
                        yield Label("RX / Diagnóstico", classes="section-title")
                        with Horizontal(classes="setting-row-wide"):
                            yield Label("RX:")
                            yield Switch(value=self.app._rx_active, id="set_rx_active")
                        yield Static("…", id="sdr_diagnose_panel")
                        with Horizontal(classes="settings-actions compact-actions"):
                            yield Button("↻", id="btn_refresh_sdr_wizard")
                            yield Button("API", id="btn_restart_sdrplay_service")
                            yield Button("Diag", id="btn_run_sdrplay_diagnose")

                with Horizontal(classes="settings-actions"):
                    yield Button("Atrás", id="btn_back_to_main_hw")
                    yield Button("Aplicar", variant="success", id="btn_apply_hardware")

            # ─── PÁGINA 3: ELIMINACIÓN DE RUIDO ───
            with Container(id="page_noise"):
                yield Label("🔊 AUDIO FM", id="settings_title_compact")
                with Container(classes="noise-grid"):
                    with Horizontal(classes="setting-row"):
                        yield Label("De-emph:")
                        yield Select(
                            [
                                ("50 µs", 50),
                                ("75 µs", 75),
                            ],
                            value=self._deemphasis_select_value(),
                            id="set_fm_deemphasis",
                        )
                    with Horizontal(classes="setting-row"):
                        yield Label("AGC:")
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
                        yield Label("Umbral:")
                        yield Select(
                            [(f"{db}dB", db) for db in self.app.SQUELCH_THRESHOLD_OPTIONS],
                            value=self._squelch_select_value(),
                            id="set_squelch_threshold",
                        )
                with Horizontal(classes="settings-actions"):
                    yield Button("Atrás", id="btn_back_to_main_noise")
                    yield Button("Aplicar", variant="success", id="btn_apply_noise")

            # ─── PÁGINA 4: AJUSTES DE GRABACIÓN ───
            with Container(id="page_recording"):
                yield Label("💾 GRABACIÓN", id="settings_title_compact")
                with Horizontal(classes="setting-row"):
                    yield Label("IQ SigMF:")
                    yield Switch(
                        value=bool(self.app.config.get("recorder", {}).get("record_iq", True)),
                        id="sw_record_iq",
                    )
                with Horizontal(classes="setting-row"):
                    yield Label("Audio WAV:")
                    yield Switch(
                        value=bool(self.app.config.get("recorder", {}).get("record_audio", True)),
                        id="sw_record_audio",
                    )
                with Horizontal(classes="settings-actions"):
                    yield Button("Atrás", id="btn_back_to_main_rec")
                    yield Button("Aplicar", variant="success", id="btn_apply_recording")

            # ─── PÁGINA 5: AJUSTES DEL ESCÁNER ───
            with Container(id="page_scanner"):
                yield Label("🔍 ESCÁNER", id="settings_title_compact")
                scan_cfg = self.app.config.get("scanner", {})
                with Container(classes="scanner-grid"):
                    with Horizontal(classes="setting-row"):
                        yield Label("Inicio:")
                        yield Input(
                            value=f"{float(scan_cfg.get('freq_start', 88_000_000)) / 1e6:.3f}",
                            placeholder="MHz",
                            id="set_scan_start",
                        )
                    with Horizontal(classes="setting-row"):
                        yield Label("Fin:")
                        yield Input(
                            value=f"{float(scan_cfg.get('freq_end', 108_000_000)) / 1e6:.3f}",
                            placeholder="MHz",
                            id="set_scan_end",
                        )
                    with Horizontal(classes="setting-row"):
                        yield Label("Paso:")
                        yield Input(
                            value=f"{float(scan_cfg.get('freq_step', 200_000)) / 1e3:.1f}",
                            placeholder="kHz",
                            id="set_scan_step",
                        )
                    with Horizontal(classes="setting-row"):
                        yield Label("Dwell:")
                        yield Input(
                            value=f"{int(scan_cfg.get('dwell_ms', 500))}",
                            placeholder="ms",
                            id="set_scan_dwell",
                        )
                    with Horizontal(classes="setting-row"):
                        yield Label("SNR:")
                        yield Input(
                            value=f"{float(scan_cfg.get('min_snr_db', 10.0)):.1f}",
                            placeholder="dB",
                            id="set_scan_snr",
                        )
                    with Horizontal(classes="setting-row"):
                        yield Label("Pausa:")
                        yield Switch(
                            value=bool(scan_cfg.get("pause_on_signal", True)),
                            id="sw_scan_pause",
                        )
                with Horizontal(classes="setting-row"):
                    yield Label("Reanudar:")
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
                yield Label("📋 BOOKMARKS", id="settings_title_compact")
                yield Label(
                    f"Activos: {len(self.app._bookmarks)}",
                    id="lbl_bookmarks_count",
                )
                with Horizontal(classes="setting-row"):
                    yield Label("Export:")
                    yield Input(
                        value="var/bookmarks_export.toml",
                        id="set_bookmarks_export",
                    )
                    yield Button("→", id="btn_export_bookmarks", variant="primary")
                with Horizontal(classes="setting-row"):
                    yield Label("Import:")
                    yield Input(
                        value="var/bookmarks_export.toml",
                        id="set_bookmarks_import",
                    )
                    yield Switch(value=True, id="sw_bookmarks_merge")
                    yield Button("←", id="btn_import_bookmarks", variant="success")
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
        elif event.button.id == "btn_refresh_sdr_wizard":
            self._refresh_hardware_page(attempt_recover=True)
        elif event.button.id == "btn_restart_sdrplay_service":
            self.app._restart_sdrplay_service_async()
            self.app._log("[INFO] Reiniciando SDRplayAPIService…")
        elif event.button.id == "btn_run_sdrplay_diagnose":
            self.app._run_sdrplay_diagnose_async()
            self.app._log("[INFO] Diagnóstico SDRplay en segundo plano…")
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

            if not _valid_select_value(driver_val):
                self.app.audio_effects.play_error()
                self.app._log("[ERR]  Selecciona un driver SDR válido")
                return

            token = str(driver_val)
            target = getattr(self, "_driver_select_map", {}).get(token)
            if target is None:
                self.app.audio_effects.play_error()
                self.app._log("[ERR]  Opción de driver desconocida")
                return

            desired_rx = bool(rx_val)
            if isinstance(target, dict):
                driver_ok = self.app.change_device(target, desired_rx=desired_rx)
            else:
                driver_ok = self.app.change_device_driver(str(target), desired_rx=desired_rx)

            if not driver_ok:
                try:
                    from core.device import build_driver_select_options

                    active_kwargs = (
                        self.app._device._device_kwargs
                        if self.app._device and self.app._device._device_kwargs
                        else None
                    )
                    _, _, selected = build_driver_select_options(
                        getattr(self.app, "_cached_sdr_devices", None),
                        current_driver=self.app.driver,
                        active_kwargs=active_kwargs,
                    )
                    self.query_one("#set_driver", Select).value = selected
                except Exception:
                    pass
            else:
                try:
                    self.query_one("#set_rx_active", Switch).value = desired_rx
                except Exception:
                    pass

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

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "set_driver":
            self.refresh_device_detail()

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
