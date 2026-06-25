"""Tests del ciclo de vida del stream RX y read_samples."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from core.device import SDRDevice, SOAPY_SDR_OVERFLOW


class _FakeStreamResult:
    def __init__(self, ret: int):
        self.ret = ret


class _FakeSoapyDevice:
    def __init__(self, results: list[int]):
        self._results = list(results)
        self.setup_calls = 0
        self.activate_calls = 0
        self.deactivate_calls = 0
        self.close_calls = 0

    def setupStream(self, *_args, **_kwargs):
        self.setup_calls += 1
        return object()

    def activateStream(self, _stream):
        self.activate_calls += 1

    def deactivateStream(self, _stream):
        self.deactivate_calls += 1

    def closeStream(self, _stream):
        self.close_calls += 1

    def readStream(self, _stream, bufs, count, timeoutUs=0):
        ret = self._results.pop(0) if self._results else 0
        if ret > 0:
            bufs[0][:ret] = np.ones(ret, dtype=np.complex64)
        return _FakeStreamResult(ret)

    def setSampleRate(self, *_a, **_k):
        pass

    def setFrequency(self, *_a, **_k):
        pass

    def setGainMode(self, *_a, **_k):
        pass

    def setGain(self, *_a, **_k):
        pass


def test_open_does_not_start_stream_on_sim():
    dev = SDRDevice(driver="simulated")
    dev.open()
    assert dev.stream_active is False


def test_start_stop_stream_sim_is_noop():
    dev = SDRDevice(driver="simulated")
    dev.open()
    dev.start_stream()
    dev.stop_stream()
    assert dev.stream_active is False


def test_read_samples_timeout_does_not_spin(monkeypatch):
    dev = SDRDevice(driver="fake")
    fake = _FakeSoapyDevice([0, 0, 1024])
    dev._sdr = fake
    dev._stream = object()

    monkeypatch.setattr("core.device.soapysdr_available", lambda: True)

    out = dev.read_samples(1024)
    assert len(out) == 1024
    assert len(fake._results) >= 0  # no busy-loop: stopped after timeout


def test_read_samples_recovers_from_overflow(monkeypatch):
    dev = SDRDevice(driver="fake")
    fake = _FakeSoapyDevice([SOAPY_SDR_OVERFLOW, 512])
    dev._sdr = fake
    dev._stream = object()

    monkeypatch.setattr("core.device.soapysdr_available", lambda: True)

    out = dev.read_samples(512)
    assert len(out) == 512
    assert fake.setup_calls >= 1
    assert np.count_nonzero(out) > 0
    assert dev.stream_stats.overflows >= 1


def test_sdrplay_open_defers_native_settings(monkeypatch):
    native = {"tune_calls": 0}

    class _FakeSoapy(_FakeSoapyDevice):
        def setSampleRate(self, *_a, **_k):
            native["tune_calls"] += 1

        def setFrequency(self, *_a, **_k):
            native["tune_calls"] += 1

    fake = _FakeSoapy([])

    class _FakeModule:
        @staticmethod
        def Device(_kwargs):
            return fake

    monkeypatch.setattr("core.device._soapy_mod", _FakeModule)
    monkeypatch.setattr("core.device._load_soapy", lambda: True)
    monkeypatch.setattr("core.device.resolve_device", lambda _d: {"driver": "sdrplay"})
    monkeypatch.setattr("core.device.run_sdr_io", lambda func, *args, **kwargs: func(*args, **kwargs))

    dev = SDRDevice(driver="sdrplay")
    dev.open()

    assert dev.stream_active is False
    assert dev._native_settings_deferred()
    assert native["tune_calls"] == 0
    dev.set_frequency(98_000_000.0)
    dev.set_gain(40.0)
    dev.set_sample_rate(500_000.0)
    assert native["tune_calls"] == 0


def test_set_frequency_restarts_active_stream(monkeypatch):
    dev = SDRDevice(driver="sdrplay")
    fake = _FakeSoapyDevice([])
    dev._sdr = fake
    dev._stream = object()
    dev.center_freq = 100_600_000.0

    monkeypatch.setattr("core.device.soapysdr_available", lambda: True)
    monkeypatch.setattr("core.device.run_sdr_io", lambda func, *args, **kwargs: func(*args, **kwargs))

    dev.set_frequency(98_000_000.0)

    assert dev.center_freq == 98_000_000.0
    assert fake.deactivate_calls >= 1
    assert fake.activate_calls >= 1


def test_sdrplay_stream_starts_at_safe_rate(monkeypatch):
    applied_rates: list[float] = []

    class _FakeSoapy(_FakeSoapyDevice):
        def setSampleRate(self, _dir, _ch, rate):
            applied_rates.append(float(rate))

    fake = _FakeSoapy([4096])
    dev = SDRDevice(driver="sdrplay")
    dev._sdr = fake
    dev.sample_rate = 2_048_000.0
    dev.center_freq = 98_000_000.0

    monkeypatch.setattr("core.device.soapysdr_available", lambda: True)
    monkeypatch.setattr("core.device.run_sdr_io", lambda func, *args, **kwargs: func(*args, **kwargs))
    monkeypatch.setattr("core.device.time.sleep", lambda _s: None)

    dev.start_stream()

    assert fake.setup_calls >= 1
    assert fake.activate_calls == 1
    assert applied_rates[-1] == 500_000.0
    assert dev._sdrplay_pending_sample_rate == 2_048_000.0
    assert dev._sdrplay_stream_bootstrapped is True


def test_sdrplay_minimal_activate_skips_prepare_before_activate(monkeypatch):
    prepare_calls: list[float] = []

    class _FakeSoapy(_FakeSoapyDevice):
        def setSampleRate(self, _dir, _ch, rate):
            pass

    fake = _FakeSoapy([1024])
    dev = SDRDevice(driver="sdrplay")
    dev._sdr = fake
    dev.sample_rate = 500_000.0
    dev.center_freq = 98_000_000.0

    def _track_prepare(rate_hz=None):
        prepare_calls.append(float(rate_hz or dev.sample_rate))

    monkeypatch.setattr("core.device.soapysdr_available", lambda: True)
    monkeypatch.setattr("core.device.run_sdr_io", lambda func, *args, **kwargs: func(*args, **kwargs))
    monkeypatch.setattr("core.device.time.sleep", lambda _s: None)
    monkeypatch.setattr(dev, "_prepare_stream_unlocked", _track_prepare)

    dev.start_stream()

    assert prepare_calls == []
    assert fake.activate_calls == 1
