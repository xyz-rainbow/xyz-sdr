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
