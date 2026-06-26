"""
xyz-sdr | tui/harness/app.py
TUI mínima de diagnóstico espectro/waterfall conectada al hardware.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Log, Static

from core.device import SDRDevice
from core.input_modifiers import is_shift_pressed
from core.startup_io import suppress_startup_output
from tui.display_sync import DisplayFrameContext, DisplayLevelState, apply_band_frame_to_widgets
from tui.harness.export import export_display_snapshot
from tui.harness.host import HarnessRxHost
from tui.rx_worker import run_rx_iteration
from tui.widgets.spectrum_graph import SpectrumGraph
from tui.widgets.waterfall_timeline import WaterfallTimeline

logger = logging.getLogger(__name__)

DEFAULT_EXPORT_ROOT = Path("var/harness")


class SdrDisplayHarnessApp(App):
    """Harness Textual: espectro + waterfall + RX real/simulado."""

    TITLE = "xyz-sdr harness"
    CSS = """
    Screen {
        background: #020617;
    }
    #status {
        height: 1;
        background: #0f172a;
        color: #e2e8f0;
        padding: 0 1;
    }
    SpectrumGraph {
        height: 10;
    }
    WaterfallTimeline {
        height: 1fr;
        min-height: 8;
    }
    #log_panel {
        height: 4;
        max-height: 4;
        border: round #38bdf8;
        background: #0f172a;
    }
    """

    BINDINGS = [
        ("s", "toggle_rx", "RX"),
        ("p", "capture", "Capture"),
        ("q", "quit", "Quit"),
        ("left", "tune_down", "Freq -"),
        ("right", "tune_up", "Freq +"),
        ("+", "gain_up", "Gain +"),
        ("-", "gain_down", "Gain -"),
    ]

    def __init__(
        self,
        host: HarnessRxHost,
        *,
        export_root: Path | None = None,
        auto_rx: bool = False,
        headless_capture: bool = False,
        capture_duration: float = 0.0,
        capture_export_dir: Path | None = None,
        min_frames: int = 1,
        run_preflight: bool = False,
    ) -> None:
        super().__init__()
        self.host = host
        self.export_root = export_root or DEFAULT_EXPORT_ROOT
        self.auto_rx = auto_rx
        self.headless_capture = headless_capture
        self.capture_duration = capture_duration
        self.capture_export_dir = capture_export_dir
        self.min_frames = min_frames
        self.run_preflight = run_preflight

        self._rx_stop_event = threading.Event()
        self._rx_stop_event.set()
        self._rx_worker_token = 0
        self._display_sequence = 0
        self._rx_started_at = 0.0
        self._last_band_frame = None
        self._last_viewport_cols = None
        self._headless_done = False
        self.last_report = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Inicializando...", id="status")
        with Vertical():
            yield SpectrumGraph(id="spectrum")
            yield WaterfallTimeline(id="waterfall")
            yield Log(id="log_panel", highlight=True, max_lines=200)
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(0.05, self._flush_display_frames)
        self._log("Harness listo — [S] RX  [←→] freq  [+/-] gain  [P] captura  [Q] salir")
        self._update_status()
        if self.auto_rx:
            self.call_later(self._start_rx)

    def _log(self, message: str) -> None:
        try:
            self.query_one("#log_panel", Log).write_line(message)
        except Exception:
            logger.info(message)

    def _update_status(self) -> None:
        dev = self.host._device
        driver = getattr(dev, "driver", self.host.driver) if dev else self.host.driver
        rx = "ON" if self.host._rx_active else "OFF"
        text = (
            f"RX:{rx} | {self.host.tuned_frequency / 1e6:.4f} MHz | "
            f"gain {self.host.gain_value:.0f} dB | "
            f"pub {self.host.metrics.frames_published} app {self.host.metrics.frames_applied} | "
            f"SNR {self.host.metrics.last_snr:.1f} dB | {driver}"
        )
        try:
            self.query_one("#status", Static).update(text)
        except Exception:
            pass

    def _set_rx_waiting(self, waiting: bool) -> None:
        try:
            self.query_one("#spectrum", SpectrumGraph).set_rx_waiting(waiting)
        except Exception:
            pass

    def _flush_display_frames(self) -> None:
        if not self.host._rx_active:
            return
        frame, snr, seq = self.host._band_mailbox.consume_if_new(self._display_sequence)
        if frame is None and self._display_sequence == 0:
            latest, latest_snr, latest_seq = self.host._band_mailbox.peek_latest()
            if latest is not None and latest_seq > 0:
                frame, snr, seq = latest, latest_snr, latest_seq
        if frame is None:
            if self.headless_capture and self._rx_started_at > 0:
                elapsed = time.time() - self._rx_started_at
                if elapsed >= self.capture_duration and not self._headless_done:
                    self._headless_done = True
                    self.call_later(self._headless_export_and_quit)
            return

        try:
            self._apply_display_frame(frame, snr, seq)
        except Exception as exc:
            logger.exception("Error display harness: %s", exc)

        if self.headless_capture and not self._headless_done:
            if (
                self.host.metrics.frames_applied >= self.min_frames
                and time.time() - self._rx_started_at >= self.capture_duration
            ):
                self._headless_done = True
                self.call_later(self._headless_export_and_quit)

    def _apply_display_frame(self, frame, snr: float, seq: int) -> None:
        display_cfg = self.host.config.get("display", {})
        spectrum = self.query_one("#spectrum", SpectrumGraph)
        waterfall = self.query_one("#waterfall", WaterfallTimeline)
        plot_width = max(self.host._display_width, spectrum._column_width())

        try:
            seq, cols = apply_band_frame_to_widgets(
                frame,
                snr,
                seq,
                spectrum=spectrum,
                waterfall=waterfall,
                ctx=DisplayFrameContext(
                    viewport_center=self.host.viewport_center,
                    visible_span=self.host.visible_span,
                    passband_center_hz=self.host.passband_center_hz,
                    passband_width_hz=self.host.passband_width_hz,
                    passband_preview_width_hz=None,
                    display_width=plot_width,
                ),
                display_cfg=display_cfg,
                level_state=DisplayLevelState(
                    waterfall_auto_level=self.host.waterfall_auto_level,
                    display_level_mode=self.host.display_level_mode,
                    level_tracker=self.host._level_tracker,
                ),
            )
            self._display_sequence = seq
            self._last_band_frame = frame
            self._last_viewport_cols = cols
            self.host.note_frame_applied()
            self._update_status()
        finally:
            self._set_rx_waiting(False)

    def action_toggle_rx(self) -> None:
        if self.host._rx_active:
            self._stop_rx()
        else:
            self._start_rx()

    def action_capture(self) -> None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out = self.export_root / stamp
        report = export_display_snapshot(self, self.host, out, min_frames=self.min_frames)
        self.last_report = report
        level = "OK" if report.display_ok else "WARN"
        self._log(f"[{level}] Captura → {out}")
        self._log(f"  report: {report.export_paths.get('report_json', out / 'report.json')}")

    def action_tune_up(self) -> None:
        step = 100_000.0 if is_shift_pressed() else 5_000.0
        self.host.apply_frequency(self.host.tuned_frequency + step)
        self._sync_viewport_widgets()
        self._update_status()

    def action_tune_down(self) -> None:
        step = 100_000.0 if is_shift_pressed() else 5_000.0
        self.host.apply_frequency(self.host.tuned_frequency - step)
        self._sync_viewport_widgets()
        self._update_status()

    def action_gain_up(self) -> None:
        self.host.apply_gain(self.host.gain_value + 5.0)
        self._update_status()

    def action_gain_down(self) -> None:
        self.host.apply_gain(self.host.gain_value - 5.0)
        self._update_status()

    def action_quit(self) -> None:
        self._stop_rx()
        if self.host._device:
            try:
                self.host._device.close()
            except Exception:
                pass
        self.exit()

    def _sync_viewport_widgets(self) -> None:
        try:
            spectrum = self.query_one("#spectrum", SpectrumGraph)
            waterfall = self.query_one("#waterfall", WaterfallTimeline)
            spectrum.set_viewport(self.host.viewport_center, self.host.visible_span)
            waterfall.set_viewport(self.host.viewport_center, self.host.visible_span)
        except Exception:
            pass

    def _start_rx(self) -> None:
        if self.host._rx_active:
            return
        if not self.host._device:
            self._log("[ERR] Sin dispositivo")
            return
        if not self._rx_stop_event.is_set():
            if not self._rx_stop_event.wait(timeout=3.0):
                self._rx_stop_event.set()

        self.host._rx_active = True
        self._rx_stop_event.clear()
        self.host.reset_rx_warmup()
        self._display_sequence = 0
        self.host._band_mailbox.clear()
        self._rx_started_at = time.time()
        self._set_rx_waiting(True)
        self._rx_worker_token += 1
        token = self._rx_worker_token
        self._rx_worker(token)
        self._log("RX iniciado")

    def _stop_rx(self) -> None:
        if not self.host._rx_active and self._rx_stop_event.is_set():
            return
        self.host._rx_active = False
        self._rx_worker_token += 1
        if self.host._device and not self.host._device.is_simulated:
            try:
                self.host._device.stop_stream(timeout=5.0)
            except Exception as exc:
                logger.warning("stop_stream harness: %s", exc)
        if not self._rx_stop_event.wait(timeout=5.0):
            self._rx_stop_event.set()
        self._set_rx_waiting(False)
        self._log("RX detenido")

    @work(thread=True)
    def _rx_worker(self, token: int) -> None:
        if token != self._rx_worker_token:
            self._rx_stop_event.set()
            return

        stream_started = False
        try:
            device = self.host._device
            if device and not device.is_simulated:
                if self.run_preflight:
                    from core.sdrplay_preflight import run_preflight_best, resolve_preflight_timeout

                    timeout = resolve_preflight_timeout()
                    result = run_preflight_best(timeout=timeout)
                    if not result.ok:
                        self.call_from_thread(
                            self._log,
                            f"[ERR] Preflight falló: {result.detail[:120] if result.detail else 'unknown'}",
                        )
                        return
                try:
                    with suppress_startup_output():
                        device.start_stream(timeout=20.0)
                    stream_started = True
                except Exception as exc:
                    self.call_from_thread(self._log, f"[ERR] start_stream: {exc}")
                    return

            while self.host._rx_active and token == self._rx_worker_token:
                try:
                    result = run_rx_iteration(self.host)
                    if result is not None and result.frame_published:
                        self.host.note_frame_published(result.snr, time.time())
                    time.sleep(0.002)
                except Exception as exc:
                    if not self.host._rx_active:
                        continue
                    logger.exception("RX harness: %s", exc)
                    self.call_from_thread(self._log, f"[ERR] RX: {exc}")
                    break
        finally:
            if stream_started and self.host._device and not self.host._device.is_simulated:
                try:
                    self.host._device.stop_stream(timeout=3.0)
                except Exception:
                    pass
            self._rx_stop_event.set()

    def _headless_export_and_quit(self) -> None:
        out = self.capture_export_dir or (self.export_root / "headless_run")
        report = export_display_snapshot(self, self.host, out, min_frames=self.min_frames)
        self.last_report = report
        self._stop_rx()
        self.exit()

    def on_unmount(self) -> None:
        if self.host._rx_active:
            self._stop_rx()
        if self.host._device:
            try:
                self.host._device.close()
            except Exception:
                pass


def open_harness_device(driver: str, config: dict) -> SDRDevice:
    """Abre SDRDevice para el harness."""
    from core.soapy_runtime import bootstrap_soapy

    device_cfg = dict(config.get("device", {}))
    if driver in ("simulated", "sim"):
        dev = SDRDevice(driver="simulated")
        dev.open()
        return dev

    bootstrap_soapy()
    dev = SDRDevice(driver=driver)
    dev.sample_rate = float(device_cfg.get("sample_rate", dev.sample_rate))
    opened = dev.open()
    if not opened:
        raise RuntimeError(f"No se pudo abrir dispositivo driver={driver!r}")
    dev.set_frequency(float(device_cfg.get("center_freq", 7_100_000)))
    dev.set_gain(float(device_cfg.get("gain", 40.0)))
    return dev


def build_harness_host(
    config: dict,
    *,
    driver: str,
    freq_hz: float | None = None,
    gain: float | None = None,
    sample_rate: float | None = None,
) -> HarnessRxHost:
    merged = dict(config)
    device_cfg = dict(merged.get("device", {}))
    device_cfg["driver"] = driver
    if freq_hz is not None:
        device_cfg["center_freq"] = float(freq_hz)
    if gain is not None:
        device_cfg["gain"] = float(gain)
    if sample_rate is not None:
        device_cfg["sample_rate"] = float(sample_rate)
    merged["device"] = device_cfg

    device = open_harness_device(driver, merged)
    host = HarnessRxHost(merged, device=device)
    host.driver = driver
    if sample_rate is not None:
        host.sample_rate = float(sample_rate)
        host.visible_span = float(sample_rate)
    if freq_hz is not None:
        host.apply_frequency(float(freq_hz))
    if gain is not None:
        host.apply_gain(float(gain))
    return host
