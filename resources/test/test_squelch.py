"""Tests de squelch — SNR local, hang time y silenciamiento."""

from __future__ import annotations

import time

import numpy as np

from core.dsp import (
    SquelchGate,
    apply_squelch,
    apply_squelch_with_state,
    estimate_snr_at_freq,
    estimate_snr_db,
)


def test_estimate_snr_at_freq_uses_tuned_bin():
    psd = np.full(256, -90.0, dtype=np.float64)
    psd[200] = -30.0
    center = 100e6
    rate = 256e3
    tuned = center - rate / 2 + 200 * (rate / 256)
    snr = estimate_snr_at_freq(psd, center, rate, tuned)
    assert snr > 50.0


def test_squelch_gate_hang_keeps_open_after_drop():
    gate = SquelchGate(threshold_db=15.0, hang_ms=500.0)
    t0 = 1000.0
    assert gate.is_open(20.0, now=t0)
    assert gate.is_open(5.0, now=t0 + 0.1)
    assert not gate.is_open(5.0, now=t0 + 0.6)


def test_apply_squelch_mutes_below_threshold():
    audio = np.ones(128, dtype=np.float32) * 0.5
    muted = apply_squelch(
        audio, snr_db=5.0, enabled=True, threshold_db=15.0, hang_ms=0.0
    )
    assert np.allclose(muted, 0.0)


def test_apply_squelch_with_state_reuses_gate():
    audio = np.ones(32, dtype=np.float32)
    gate = SquelchGate(threshold_db=15.0, hang_ms=500.0)
    gate.is_open(20.0, now=1000.0)
    out, open_state = apply_squelch_with_state(
        audio, 5.0, gate, enabled=True, now=1000.1
    )
    np.testing.assert_allclose(out, audio)
    assert open_state is True


def test_apply_squelch_disabled_passthrough():
    audio = np.ones(32, dtype=np.float32)
    out = apply_squelch(audio, snr_db=0.0, enabled=False, threshold_db=15.0)
    np.testing.assert_allclose(out, audio)


def test_estimate_snr_db_legacy_peak():
    psd = np.full(128, -80.0, dtype=np.float64)
    psd[64] = -20.0
    assert estimate_snr_db(psd) > 50.0
