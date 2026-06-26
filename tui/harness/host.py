"""
xyz-sdr | tui/harness/host.py
Host RX mínimo para el harness (protocolo RxWorkerHost).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from core.band_buffer import BandFrameMailbox
from core.device import SDRDevice
from core.display_levels import ColumnLevelTracker
from core.dsp import AudioAgc, FmDemodState, SquelchGate
from core.rx_warmup import RX_WARMUP_ITERS, cap_rx_warmup_samples


@dataclass
class HarnessMetrics:
  frames_published: int = 0
  frames_applied: int = 0
  last_snr: float = 0.0
  last_frame_ts: float = 0.0


class HarnessRxHost:
    """Contrato mínimo para run_rx_iteration sin la app principal."""

    def __init__(self, config: dict, device: SDRDevice | None = None) -> None:
        device_cfg = config.get("device", {})
        dsp_cfg = config.get("dsp", {})
        display_cfg = config.get("display", {})

        self.config = config
        self._device = device
        self._band_mailbox = BandFrameMailbox()
        self._recorder = None
        self._audio_output = None
        self._fm_demod_state = FmDemodState()
        self._fm_agc = AudioAgc()
        self._squelch_gate = SquelchGate()
        self._squelch_open = True
        self._debug_lock = threading.Lock()
        self._debug_rx_proc_ms: list[float] = []
        self._debug_rx_iter_count = 0
        self._debug_chunk_samples: list[int] = []
        self._debug_chunk_duration_ms: list[float] = []
        self._debug_demod_ms: list[float] = []
        self._debug_audio_samples: list[int] = []

        self._rx_active = False
        self._bandwidth_changing = False
        self._rx_warmup_iters_left = 0
        self._display_width = 80
        self._display_sequence = 0
        self.metrics = HarnessMetrics()

        self.driver = str(device_cfg.get("driver", "simulated"))
        self.sample_rate = float(device_cfg.get("sample_rate", 250_000))
        self.tuned_frequency = float(device_cfg.get("center_freq", 7_100_000))
        self.gain_value = float(device_cfg.get("gain", 40.0))
        self.visible_span = float(self.sample_rate)
        self.viewport_center = float(self.tuned_frequency)
        self.passband_center_hz = float(self.tuned_frequency)
        self.passband_width_hz = float(dsp_cfg.get("wbfm_bandwidth", 180_000))
        self.demod_mode = "raw"
        self.squelch_enabled = False
        self.squelch_threshold = float(dsp_cfg.get("squelch_threshold", 5))
        self.fm_deemphasis_us = float(dsp_cfg.get("fm_deemphasis_us", 50))
        self.fm_agc_enabled = bool(dsp_cfg.get("fm_agc_enabled", True))
        self.debug_mode = False

        self.waterfall_auto_level = bool(display_cfg.get("waterfall_auto_level", True))
        self.display_level_mode = str(display_cfg.get("display_level_mode", "per_column"))
        self._level_tracker = ColumnLevelTracker(
            width=max(self._display_width, 1),
            floor_pct=float(display_cfg.get("column_floor_pct", 10)),
            ceiling_pct=float(display_cfg.get("column_ceiling_pct", 99)),
            min_range_db=float(display_cfg.get("waterfall_min_range_db", 6.0)),
            attack=float(display_cfg.get("column_ema_attack", 0.35)),
            release=float(display_cfg.get("column_ema_release", 0.08)),
            smooth_bins=int(display_cfg.get("column_smooth_bins", 3)),
            history_rows=int(display_cfg.get("column_history_rows", 32)),
        )
        span_ratio = self.visible_span / max(self.sample_rate, 1.0)
        self._level_tracker.set_span_ratio(span_ratio)

    @property
    def active_demod_mode(self) -> str:
        return self.demod_mode

    def consume_rx_warmup_samples(self, requested: int) -> int:
        prev = self._rx_warmup_iters_left
        capped, remaining = cap_rx_warmup_samples(requested, self._rx_warmup_iters_left)
        self._rx_warmup_iters_left = remaining
        if prev > 0 and remaining == 0 and self._device and not self._device.is_simulated:
            try:
                self._device.maybe_ramp_sdrplay_sample_rate()
            except Exception:
                pass
        return capped

    def ensure_audio_output(self) -> None:
        return

    def note_frame_published(self, snr: float, timestamp: float) -> None:
        self.metrics.frames_published += 1
        self.metrics.last_snr = snr
        self.metrics.last_frame_ts = timestamp

    def note_frame_applied(self) -> None:
        self.metrics.frames_applied += 1

    def reset_rx_warmup(self) -> None:
        self._rx_warmup_iters_left = RX_WARMUP_ITERS

    def apply_frequency(self, hz: float) -> None:
        self.tuned_frequency = float(hz)
        self.viewport_center = float(hz)
        self.passband_center_hz = float(hz)
        if self._device:
            self._device.set_frequency(self.tuned_frequency)

    def apply_gain(self, db: float) -> None:
        self.gain_value = float(db)
        if self._device:
            self._device.set_gain(self.gain_value)
