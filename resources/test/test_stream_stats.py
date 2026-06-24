"""Tests de métricas de stream IQ."""

from __future__ import annotations

from core.device import SDRDevice, SOAPY_SDR_OVERFLOW
from core.stream_stats import StreamStats
from resources.test.test_device_stream import _FakeSoapyDevice


def test_stream_stats_drop_rate():
    stats = StreamStats(samples_requested=1000, samples_received=900, overflows=2)
    assert stats.samples_dropped == 100
    assert abs(stats.drop_rate - 0.1) < 1e-9


def test_stream_stats_delta():
    before = StreamStats(samples_requested=100, samples_received=90, overflows=1)
    after = StreamStats(samples_requested=300, samples_received=250, overflows=3)
    delta = StreamStats.delta(before, after)
    assert delta.samples_requested == 200
    assert delta.samples_received == 160
    assert delta.overflows == 2


def test_read_samples_tracks_overflow(monkeypatch):
    dev = SDRDevice(driver="fake")
    fake = _FakeSoapyDevice([SOAPY_SDR_OVERFLOW, 256])
    dev._sdr = fake
    dev._stream = object()

    monkeypatch.setattr("core.device.soapysdr_available", lambda: True)

    out = dev.read_samples(256)
    stats = dev.stream_stats
    assert len(out) == 256
    assert stats.overflows >= 1
    assert stats.samples_received == 256
    assert stats.recoveries >= 1
