"""Tests de core/sounddevice_runtime.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.sounddevice_runtime import SoundDeviceProxy, terminate_portaudio


def test_sounddevice_proxy_delegates_attributes():
    proxy = SoundDeviceProxy()
    sentinel = MagicMock()
    with patch.dict("sys.modules", {"sounddevice": sentinel}):
        sentinel.query_devices = MagicMock(return_value=[])
        assert proxy.query_devices() == []


def test_terminate_portaudio_noop_when_not_loaded():
    with patch.dict("sys.modules", {"sounddevice": None}):
        terminate_portaudio()
