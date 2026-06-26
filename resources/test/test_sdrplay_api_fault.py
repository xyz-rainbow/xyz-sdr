"""Tests de is_sdrplay_api_fault."""

from __future__ import annotations

from unittest.mock import patch

from core.soapy_runtime import is_sdrplay_api_fault


def test_is_sdrplay_api_fault_detects_service_not_responding():
    with patch("core.soapy_runtime.check_sdrplay_api", return_value=True), patch(
        "core.soapy_runtime.run_sdrplay_find",
        return_value=(False, "", "sdrplay_api_ServiceNotResponding"),
    ):
        assert is_sdrplay_api_fault() is True


def test_is_sdrplay_api_fault_false_when_device_found():
    with patch("core.soapy_runtime.check_sdrplay_api", return_value=True), patch(
        "core.soapy_runtime.run_sdrplay_find",
        return_value=(True, "Found device driver=sdrplay", ""),
    ):
        assert is_sdrplay_api_fault() is False


def test_is_sdrplay_api_fault_false_without_api_on_disk():
    with patch("core.soapy_runtime.check_sdrplay_api", return_value=False):
        assert is_sdrplay_api_fault() is False
