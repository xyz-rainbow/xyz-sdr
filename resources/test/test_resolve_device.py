"""Tests de resolución de dispositivos SoapySDR."""

from __future__ import annotations

import pytest

from core.device import HardwareInitializationError, filter_sdr_devices, resolve_device


def test_filter_sdr_devices_skips_audio():
    devices = [
        {"driver": "audio", "label": "Mic"},
        {"driver": "rtlsdr", "label": "RTL"},
    ]
    assert filter_sdr_devices(devices) == [{"driver": "rtlsdr", "label": "RTL"}]


def test_resolve_device_auto_picks_first_non_audio():
    devices = [
        {"driver": "audio", "label": "Mic"},
        {"driver": "sdrplay", "label": "RSPdx", "serial": "ABC"},
        {"driver": "rtlsdr", "label": "RTL"},
    ]
    kwargs = resolve_device("auto", devices)
    assert kwargs["driver"] == "sdrplay"
    assert kwargs["serial"] == "ABC"


def test_resolve_device_sdrplay_match():
    devices = [
        {"driver": "rtlsdr", "label": "RTL"},
        {"driver": "sdrplay", "label": "RSPduo", "serial": "XYZ"},
    ]
    kwargs = resolve_device("sdrplay", devices)
    assert kwargs["serial"] == "XYZ"


def test_resolve_device_no_match_raises():
    devices = [{"driver": "rtlsdr", "label": "RTL"}]
    with pytest.raises(HardwareInitializationError):
        resolve_device("hackrf", devices)


def test_resolve_device_empty_raises():
    with pytest.raises(HardwareInitializationError):
        resolve_device("auto", [])


def test_resolve_device_sdrplay_to_miri_proxy():
    devices = [
        {"driver": "rtlsdr", "label": "RTL"},
        {"driver": "miri", "label": "Mirics SDRplay RSPduo", "serial": "123"},
    ]
    kwargs = resolve_device("sdrplay", devices)
    assert kwargs["driver"] == "miri"
    assert kwargs["serial"] == "123"


def test_resolve_device_sdrplay_rejects_msi2500_miri():
    devices = [
        {"driver": "miri", "label": "Mirics MSi2500 default (e.g. VTX3D card)", "miri": "0"},
    ]
    with pytest.raises(HardwareInitializationError) as exc:
        resolve_device("sdrplay", devices)
    assert "SDRplay RSP" in str(exc.value)
    assert "msi2500" in str(exc.value).lower() or "miri" in str(exc.value).lower()


def test_resolve_device_sdrplay_prefers_native_over_miri():
    devices = [
        {"driver": "miri", "label": "Mirics MSi2500 default (e.g. VTX3D card)", "miri": "0"},
        {"driver": "sdrplay", "label": "SDRplay Dev0 RSP1", "serial": "0000000001"},
    ]
    kwargs = resolve_device("sdrplay", devices)
    assert kwargs["driver"] == "sdrplay"
    assert kwargs["serial"] == "0000000001"
