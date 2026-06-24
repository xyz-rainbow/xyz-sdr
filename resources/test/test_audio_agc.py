"""Tests de AGC post-demod FM."""

from __future__ import annotations

import numpy as np

from core.dsp import AudioAgc, apply_fm_agc


def test_audio_agc_raises_quiet_signal():
    gate = AudioAgc(target_rms=0.12, max_gain=10.0)
    quiet = np.full(480, 0.001, dtype=np.float32)
    loud = gate.process(quiet, sample_rate=48_000)
    assert float(np.sqrt(np.mean(loud**2))) > float(np.sqrt(np.mean(quiet**2)))


def test_audio_agc_limits_hot_signal():
    gate = AudioAgc(target_rms=0.12, max_gain=8.0)
    hot = np.full(480, 0.9, dtype=np.float32)
    out = gate.process(hot, sample_rate=48_000)
    assert float(np.max(np.abs(out))) <= 1.0


def test_apply_fm_agc_disabled_passthrough():
    gate = AudioAgc()
    audio = np.linspace(-0.5, 0.5, 64, dtype=np.float32)
    out = apply_fm_agc(audio, gate, enabled=False)
    np.testing.assert_array_equal(out, audio)


def test_apply_fm_agc_reuses_state():
    gate = AudioAgc(target_rms=0.2, max_gain=10.0)
    chunk = np.full(256, 0.02, dtype=np.float32)
    first = apply_fm_agc(chunk, gate, enabled=True, sample_rate=48_000)
    second = apply_fm_agc(chunk, gate, enabled=True, sample_rate=48_000)
    assert float(np.sqrt(np.mean(second**2))) >= float(np.sqrt(np.mean(first**2)))
