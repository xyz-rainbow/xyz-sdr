"""Tests headless de core/scanner.py — ScannerEngine con ScannerHost mock."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import numpy as np
import pytest

from core.scanner import (
    ScannerConfig,
    ScannerEngine,
    ScannerHost,
    ScannerState,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_host(**overrides) -> MagicMock:
    """Crea un host mock que satisface ScannerHost.

    side_effect en set_tuned_frequency: actualiza tuned_frequency
    (simula el comportamiento real del TUI).
    """
    host = MagicMock(spec=ScannerHost)
    host.tuned_frequency = 100_000_000.0
    host.viewport_center = 100_000_000.0
    host.passband_center_hz = 100_000_000.0
    host.passband_width_hz = 200_000.0
    host.visible_span = 500_000.0
    host.display_width = 100
    host.rx_active = True

    # Simular que set_tuned_frequency actualiza la propiedad
    def _set_freq(freq_hz: float) -> None:
        host.tuned_frequency = freq_hz
        host.passband_center_hz = freq_hz
        host.viewport_center = freq_hz

    host.set_tuned_frequency.side_effect = _set_freq
    for k, v in overrides.items():
        setattr(host, k, v)
    return host


def _make_engine(**host_overrides) -> ScannerEngine:
    return ScannerEngine(_make_host(**host_overrides))


class _Clock:
    """Reloj de tests inyectable a ScannerEngine."""
    def __init__(self, initial: float = 1000.0):
        self.now = initial

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _make_engine_with_clock(clock: _Clock, **host_overrides) -> ScannerEngine:
    return ScannerEngine(_make_host(**host_overrides), time_fn=clock)


def _make_config(**overrides) -> ScannerConfig:
    defaults = dict(
        freq_start_hz=88_000_000.0,
        freq_end_hz=108_000_000.0,
        freq_step_hz=200_000.0,
        dwell_s=0.5,
        min_snr_db=10.0,
        pause_on_signal=True,
        pause_resume_snr_db=7.0,
    )
    defaults.update(overrides)
    return ScannerConfig(**defaults)


def _flat_levels(n: int, base: float = -60.0, height: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Genera (floors, ceilings) con SNR=`height` dB."""
    floors = np.full(n, base, dtype=np.float32)
    ceilings = floors + height
    return floors, ceilings


# ── Config ────────────────────────────────────────────────────────────────────


def test_config_from_dict_defaults():
    cfg = ScannerConfig.from_dict({})
    assert cfg.freq_start_hz == 88_000_000.0
    assert cfg.freq_end_hz == 108_000_000.0
    assert cfg.dwell_s == 0.5
    assert cfg.min_snr_db == 10.0


def test_config_from_dict_overrides():
    cfg = ScannerConfig.from_dict({
        "freq_start": 118_000_000,
        "freq_end": 137_000_000,
        "dwell_ms": 250,
        "min_snr_db": 15.0,
        "pause_on_signal": False,
        "pause_resume_snr_db": 5.5,
    })
    assert cfg.freq_start_hz == 118_000_000
    assert cfg.freq_end_hz == 137_000_000
    assert cfg.dwell_s == 0.25
    assert cfg.min_snr_db == 15.0
    assert cfg.pause_on_signal is False
    assert cfg.pause_resume_snr_db == 5.5


# ── Lifecycle ────────────────────────────────────────────────────────────────


def test_engine_initial_state_not_scanning():
    eng = _make_engine()
    assert eng.scanning is False
    assert eng.paused is False


def test_engine_configure_then_start():
    eng = _make_engine()
    eng.configure(_make_config())
    eng.start()
    assert eng.scanning is True
    assert eng.paused is False
    # Debe haber saltado a la freq de inicio
    eng._host.set_tuned_frequency.assert_called_with(88_000_000.0)
    # Y host_logueado
    assert any("Iniciando escaneo" in str(c) for c in eng._host.host_log.call_args_list)


def test_engine_start_requires_rx_active():
    eng = _make_engine(rx_active=False)
    eng.configure(_make_config())
    result = eng.start()
    assert result is False
    eng._host.play_error.assert_called_once()
    assert eng.scanning is False


def test_engine_start_requires_configure_first():
    eng = _make_engine()
    with pytest.raises(RuntimeError, match="no configurado"):
        eng.start()


def test_engine_stop_resets_state():
    eng = _make_engine()
    eng.configure(_make_config())
    eng.start()
    eng.stop()
    assert eng.scanning is False
    assert eng.paused is False


def test_engine_stop_when_not_scanning_is_noop():
    eng = _make_engine()
    eng.stop()  # no debe lanzar
    assert eng.scanning is False


# ── Step / wrap-around ───────────────────────────────────────────────────────


def test_engine_step_increments_frequency():
    eng = _make_engine(tuned_frequency=100_000_000.0)
    eng.configure(_make_config(freq_step_hz=200_000.0))
    eng.start()  # lleva a 88_000_000
    eng.step()   # siguiente: 88_200_000
    assert eng._host.tuned_frequency == 88_200_000.0


def test_engine_step_wraps_at_end():
    eng = _make_engine()
    eng.configure(_make_config(freq_start_hz=88_000_000, freq_end_hz=108_000_000, freq_step_hz=200_000))
    eng.start()  # freq → 88_000_000
    # Forzar freq cerca del final
    eng._host.tuned_frequency = 107_900_000.0
    eng.step()  # 107_900_000 + 200_000 = 108_100_000 > 108_000_000 → wrap a 88_000_000
    assert eng._host.tuned_frequency == 88_000_000.0


# ── Pause / resume ───────────────────────────────────────────────────────────


def test_engine_pause_emits_chime_and_host_log():
    eng = _make_engine()
    eng.configure(_make_config())
    eng.start()
    eng.pause(15.5)
    assert eng.paused is True
    eng._host.play_chime.assert_called_once()
    assert any("Pausa" in str(c) for c in eng._host.host_log.call_args_list)


def test_engine_pause_idempotent():
    eng = _make_engine()
    eng.configure(_make_config())
    eng.start()
    eng.pause(15.0)
    eng.pause(20.0)  # segunda llamada, ya está en pausa
    eng._host.play_chime.assert_called_once()  # solo 1 chime


def test_engine_resume_clears_pause():
    eng = _make_engine()
    eng.configure(_make_config())
    eng.start()
    eng.pause(15.0)
    eng.resume()
    assert eng.paused is False
    assert eng.scanning is True


def test_engine_resume_requires_paused():
    eng = _make_engine()
    eng.configure(_make_config())
    eng.start()
    eng.resume()  # no estaba en pausa, no debe hacer nada
    # Y host_loguear el resume solo si estaba pausado
    host_log_messages = [str(c) for c in eng._host.host_log.call_args_list]
    assert not any("Reanudando" in m for m in host_log_messages)


# ── on_frame host_logic ───────────────────────────────────────────────────────────


def test_on_frame_ignores_when_not_scanning():
    eng = _make_engine()
    floors, ceilings = _flat_levels(100, height=20.0)
    eng.on_frame(100_000_000.0, floors, ceilings)
    # No debe haber llamado a play_chime (no pause)
    eng._host.play_chime.assert_not_called()


def test_on_frame_pauses_on_high_snr():
    eng = _make_engine()
    eng.configure(_make_config(min_snr_db=10.0, pause_on_signal=True))
    eng.start()  # freq → 88_000_000
    floors, ceilings = _flat_levels(100, base=-60.0, height=20.0)
    # frame_center_hz debe coincidir con tuned_frequency (88_000_000)
    eng.on_frame(88_000_000.0, floors, ceilings)
    assert eng.paused is True


def test_on_frame_continues_on_low_snr_within_dwell():
    eng = _make_engine()
    eng.configure(_make_config(dwell_s=10.0))  # dwell largo, no avanzará
    eng.start()
    floors, ceilings = _flat_levels(100, base=-60.0, height=2.0)
    eng.on_frame(100_000_000.0, floors, ceilings)
    # No debe avanzar (dwell no cumplido)
    assert eng.scanning is True
    assert eng.paused is False


def test_on_frame_advances_after_dwell_with_no_signal():
    """Sin señal y tras dwell cumplido, el scanner avanza a la siguiente freq."""
    clock = _Clock(100.0)
    eng = _make_engine_with_clock(clock, tuned_frequency=100_000_000.0)
    eng.configure(_make_config(dwell_s=0.1, freq_step_hz=200_000))
    eng.start()  # freq → 88_000_000; tuned_time = 100.0
    # Avanzar el reloj más allá del dwell
    clock.advance(0.5)  # now = 100.5
    floors, ceilings = _flat_levels(100, height=0.0)  # sin señal
    eng.on_frame(88_000_000.0, floors, ceilings)
    # Debe haber avanzado a la siguiente freq
    assert eng._host.tuned_frequency == 88_200_000.0


def test_on_frame_continues_when_dwell_not_yet_elapsed():
    """Sin señal pero dwell no cumplido → no avanza todavía."""
    clock = _Clock(100.0)
    eng = _make_engine_with_clock(clock, tuned_frequency=100_000_000.0)
    eng.configure(_make_config(dwell_s=1.0, freq_step_hz=200_000))
    eng.start()
    clock.advance(0.1)  # now = 100.1 (< 1.0 dwell)
    floors, ceilings = _flat_levels(100, height=0.0)
    eng.on_frame(88_000_000.0, floors, ceilings)
    assert eng._host.tuned_frequency == 88_000_000.0


def test_on_frame_ignores_frame_with_wrong_center():
    eng = _make_engine()
    eng.configure(_make_config())
    eng.start()
    floors, ceilings = _flat_levels(100, height=30.0)
    # center_hz distinto de tuned_frequency → ignora
    eng.on_frame(200_000_000.0, floors, ceilings)
    assert eng.paused is False


def test_on_frame_resumes_when_paused_and_snr_low():
    """Pausado + SNR bajo por más del dwell → resume."""
    clock = _Clock(200.0)
    eng = _make_engine_with_clock(clock)
    eng.configure(_make_config(
        freq_start_hz=88_000_000, freq_end_hz=108_000_000, freq_step_hz=200_000,
        pause_resume_snr_db=5.0, dwell_s=0.1,
    ))
    eng.start()  # freq → 88_000_000; tuned_time = 200.0
    eng.pause(15.0)  # paused=True
    # 1er frame: SNR bajo, marca pause_below_since
    clock.advance(0.2)  # now = 200.2
    floors, ceilings = _flat_levels(100, height=0.0)
    # frame_center_hz debe coincidir con tuned_frequency (88_000_000)
    eng.on_frame(88_000_000.0, floors, ceilings)
    # 2do frame: ya pasó el dwell (0.3s > 0.1s) → resume
    clock.advance(0.3)  # now = 200.5
    eng.on_frame(88_000_000.0, floors, ceilings)
    assert eng.paused is False


# ── State snapshot ───────────────────────────────────────────────────────────


def test_state_snapshot_is_decoupled():
    """state property debe devolver una copia, no la referencia mutable."""
    eng = _make_engine()
    eng.configure(_make_config())
    eng.start()
    snap = eng.state
    snap.scanning = False  # modificar la copia
    assert eng.scanning is True  # original intacto


def test_state_defaults():
    s = ScannerState()
    assert s.scanning is False
    assert s.paused is False
    assert s.tuned_time == 0.0