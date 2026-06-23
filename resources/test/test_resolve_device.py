"""Tests de resolución de dispositivos SoapySDR."""

from __future__ import annotations

import pytest

from core.device import HardwareInitializationError, resolve_device


def test_resolve_device_auto_picks_first():
    devices = [
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
