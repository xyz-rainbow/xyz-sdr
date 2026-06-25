"""
xyz-sdr | core/scanner.py
Motor de escaneo de banda — testeable headless, sin dependencias de Textual.

Antes: la lógica vivía en `tui/app.py` mezclada con widgets, log, audio effects.
Ahora: `ScannerEngine` opera contra un `ScannerHost` (Protocol) que el TUI implementa.

Ventajas:
- Tests unitarios sin levantar Textual.
- Reusable desde CLI / scripts.
- Clara separación: lógica de dominio vs UI.

Refs:
- .mavis/plans/deliverables/final_report.md §Fase 3 item 43 (god class refactor)
- .mavis/plans/deliverables/fase0_docs_recorder_scanner.md §Scanner algorithm
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

import numpy as np


# ── Configuración y estado ────────────────────────────────────────────────────


@dataclass(frozen=True)
class ScannerConfig:
    """Parámetros de escaneo cargados desde TOML [scanner]."""

    freq_start_hz: float
    freq_end_hz: float
    freq_step_hz: float
    dwell_s: float
    min_snr_db: float
    pause_on_signal: bool
    pause_resume_snr_db: float

    @classmethod
    def from_dict(cls, data: dict) -> "ScannerConfig":
        return cls(
            freq_start_hz=float(data.get("freq_start", 88_000_000)),
            freq_end_hz=float(data.get("freq_end", 108_000_000)),
            freq_step_hz=float(data.get("freq_step", 200_000)),
            dwell_s=float(data.get("dwell_ms", 500)) / 1000.0,
            min_snr_db=float(data.get("min_snr_db", 10.0)),
            pause_on_signal=bool(data.get("pause_on_signal", True)),
            pause_resume_snr_db=float(data.get("pause_resume_snr_db", 7.0)),
        )


@dataclass
class ScannerState:
    """Estado mutable del escáner."""

    scanning: bool = False
    paused: bool = False
    tuned_time: float = 0.0
    last_signal_time: float = 0.0
    pause_below_since: float = 0.0


# ── Host interface ───────────────────────────────────────────────────────────


class ScannerHost(Protocol):
    """Interfaz mínima que el ScannerEngine necesita del TUI / caller.

    XyzSDRApp implementa este Protocol delegando a sus atributos.
    Tests pueden usar un mock simple con las mismas propiedades.
    """

    # Propiedades de solo lectura (estado del sintonizador)
    @property
    def tuned_frequency(self) -> float: ...
    @property
    def viewport_center(self) -> float: ...
    @property
    def passband_center_hz(self) -> float: ...
    @property
    def passband_width_hz(self) -> float: ...
    @property
    def visible_span(self) -> float: ...
    @property
    def display_width(self) -> int: ...
    @property
    def rx_active(self) -> bool: ...

    # Callbacks de efecto
    def set_tuned_frequency(self, freq_hz: float) -> None: ...
    def host_log(self, message: str) -> None: ...
    def play_chime(self) -> None: ...
    def play_error(self) -> None: ...


# ── Engine ────────────────────────────────────────────────────────────────────


class ScannerEngine:
    """Lógica de escaneo de banda testeable headless.

    Uso típico desde XyzSDRApp::

        self._scanner = ScannerEngine(self)  # self implementa ScannerHost

        # Action handler:
        def action_toggle_scan(self):
            if self._scanner.scanning and self._scanner.paused:
                self._scanner.resume()
            elif self._scanner.scanning:
                self._scanner.stop()
            else:
                self._scanner.configure(self.config.get("scanner", {}))
                self._scanner.start()

        # Per frame:
        self._scanner.on_frame(frame.center_hz, floors, ceilings)

    Args:
        host: implementa ScannerHost.
        time_fn: callable que devuelve tiempo en segundos (default: ``time.time``).
            Inyectable para tests deterministas.
    """

    def __init__(self, host: ScannerHost, time_fn: Callable[[], float] | None = None) -> None:
        import time as _time
        self._host = host
        self._time_fn = time_fn or _time.time
        self._config: ScannerConfig | None = None
        self._state = ScannerState()

    # ── Properties (state inspection for UI) ────────────────────────────────

    @property
    def scanning(self) -> bool:
        return self._state.scanning

    @property
    def paused(self) -> bool:
        return self._state.paused

    @property
    def state(self) -> ScannerState:
        """Snapshot del estado (para tests / debug)."""
        return ScannerState(**vars(self._state))

    # ── Configuration ───────────────────────────────────────────────────────

    def configure(self, config: dict | ScannerConfig) -> None:
        if isinstance(config, ScannerConfig):
            self._config = config
        else:
            self._config = ScannerConfig.from_dict(config)

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Inicia el escaneo. Devuelve False si no se pudo (RX off)."""
        if not self._host.rx_active:
            self._host.play_error()
            self._host.host_log("[ERROR] Inicia RX antes de escanear")
            return False
        if self._config is None:
            raise RuntimeError(
                "ScannerEngine no configurado. Llama configure() antes de start()."
            )
        cfg = self._config
        self._state = ScannerState(
            scanning=True,
            paused=False,
            tuned_time=self._time_fn(),
        )
        self._host.host_log(
            f"[SCAN] Iniciando escaneo ({cfg.freq_start_hz / 1e6:.2f} - "
            f"{cfg.freq_end_hz / 1e6:.2f} MHz, paso {cfg.freq_step_hz / 1e3:.1f} kHz)"
        )
        # Saltar directamente a la frecuencia de inicio
        self._host.set_tuned_frequency(cfg.freq_start_hz)
        return True

    def stop(self) -> None:
        """Detiene el escaneo y resetea estado."""
        if not self._state.scanning:
            return
        self._state = ScannerState()
        self._host.host_log("[SCAN] Escaneo detenido")

    def pause(self, passband_snr: float) -> None:
        """Pausa el escaneo por señal detectada."""
        if self._state.paused:
            return
        self._state.paused = True
        self._state.pause_below_since = 0.0
        self._host.play_chime()
        self._host.host_log(
            f"[SCAN] Pausa — señal {passband_snr:.1f} dB en "
            f"{self._host.tuned_frequency / 1e6:.4f} MHz"
        )

    def resume(self) -> None:
        """Reanuda un escaneo en pausa."""
        if not self._state.scanning or not self._state.paused:
            return
        self._state.paused = False
        self._state.tuned_time = self._time_fn()
        self._state.last_signal_time = 0.0
        self._state.pause_below_since = 0.0
        self._host.host_log("[SCAN] Reanudando escaneo")

    def step(self) -> None:
        """Avanza a la siguiente frecuencia (wrap-around en freq_end)."""
        cfg = self._config
        if cfg is None:
            return
        next_freq = self._host.tuned_frequency + cfg.freq_step_hz
        if next_freq > cfg.freq_end_hz:
            next_freq = cfg.freq_start_hz
        self._host.host_log(f"[SCAN] Sintonizando: {next_freq / 1e6:.4f} MHz")
        self._host.set_tuned_frequency(next_freq)
        self._state.tuned_time = self._time_fn()
        self._state.last_signal_time = 0.0

    # ── Per-frame callback ──────────────────────────────────────────────────

    def on_frame(
        self,
        frame_center_hz: float,
        floors: np.ndarray,
        ceilings: np.ndarray,
    ) -> None:
        """Procesa un frame del RX worker. Decide pausar/avanzar/reanudar.

        Args:
            frame_center_hz: center_hz del BandFrame actual.
            floors: array de floors por columna (auto-level).
            ceilings: array de ceilings por columna.
        """
        cfg = self._config
        if cfg is None or not self._state.scanning:
            return

        # 1. Solo actuar si la frecuencia del frame coincide con la sintonizada
        if abs(frame_center_hz - self._host.tuned_frequency) > 10.0:
            return

        # 2. Calcular SNR en passband
        passband_snr = self._compute_passband_snr(floors, ceilings)

        now = self._time_fn()

        # 3. Si está en pausa, esperar a que SNR baje de pause_resume
        if self._state.paused:
            self._handle_paused(passband_snr, now, cfg)
            return

        # 4. Detectar señal y decidir pausa o log
        if passband_snr >= cfg.min_snr_db:
            if cfg.pause_on_signal:
                self.pause(passband_snr)
                return
            if self._state.last_signal_time == 0.0:
                self._host.host_log(
                    f"[SCAN] Señal en {self._host.tuned_frequency / 1e6:.4f} MHz "
                    f"(SNR: {passband_snr:.1f} dB)"
                )
            self._state.last_signal_time = now
            return

        # 5. SNR bajo: esperar dwell y avanzar
        ref_time = (
            self._state.last_signal_time
            if self._state.last_signal_time > 0.0
            else self._state.tuned_time
        )
        if now - ref_time >= cfg.dwell_s:
            self.step()

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _handle_paused(
        self,
        passband_snr: float,
        now: float,
        cfg: ScannerConfig,
    ) -> None:
        if passband_snr < cfg.pause_resume_snr_db:
            if self._state.pause_below_since == 0.0:
                self._state.pause_below_since = now
            elif now - self._state.pause_below_since >= cfg.dwell_s:
                self.resume()
        else:
            self._state.pause_below_since = 0.0

    def _compute_passband_snr(
        self,
        floors: np.ndarray,
        ceilings: np.ndarray,
    ) -> float:
        """SNR = max(ceilings - floors) en las columnas del passband."""
        from core.passband import freq_to_col  # lazy import para evitar ciclo

        host = self._host
        band_w = host.passband_width_hz
        left_hz = host.passband_center_hz - band_w / 2
        right_hz = host.passband_center_hz + band_w / 2
        col_l = freq_to_col(
            left_hz,
            widget_width=host.display_width,
            viewport_center_hz=host.viewport_center,
            visible_span_hz=host.visible_span,
        )
        col_r = freq_to_col(
            right_hz,
            widget_width=host.display_width,
            viewport_center_hz=host.viewport_center,
            visible_span_hz=host.visible_span,
        )
        pb_l = max(0, min(min(col_l, col_r), host.display_width - 1))
        pb_r = max(0, min(max(col_l, col_r), host.display_width - 1))

        if pb_r < pb_l:
            return 0.0
        return float(np.max(ceilings[pb_l : pb_r + 1] - floors[pb_l : pb_r + 1]))