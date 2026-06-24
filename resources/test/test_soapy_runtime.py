"""Tests de core/soapy_runtime.py (checker sdrplay)."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.soapy_runtime import (
    _parse_sdrplay_find_stdout,
    check_sdrplay_plugin,
    check_sdrplay_service_running,
)

SUCCESS_STDOUT = """
Found device 0
  driver = sdrplay
  label = SDRplay Dev0 RSP1 0000000001
  serial = 0000000001
"""

FAIL_STDOUT = "No devices found! driver=sdrplay\n"

ERROR_STDERR = """
[ERROR] sdrplay_api_Open() Error: sdrplay_api_Fail
[ERROR] SoapySDR::Device::enumerate(sdrplay) sdrplay_api_Open() failed
"""


def test_parse_sdrplay_find_stdout_accepts_found_device():
    assert _parse_sdrplay_find_stdout(SUCCESS_STDOUT) is True


def test_parse_sdrplay_find_stdout_rejects_no_devices():
    assert _parse_sdrplay_find_stdout(FAIL_STDOUT) is False


def test_parse_sdrplay_find_stdout_rejects_empty():
    assert _parse_sdrplay_find_stdout("") is False


def test_check_sdrplay_plugin_ignores_stderr_errors(monkeypatch):
    mock_run = MagicMock(
        return_value=MagicMock(
            stdout="",
            stderr=ERROR_STDERR,
            returncode=-1073741819,
        )
    )
    monkeypatch.setattr("core.soapy_runtime.subprocess.run", mock_run)
    assert check_sdrplay_plugin() is False


def test_check_sdrplay_plugin_accepts_stdout_match(monkeypatch):
    mock_run = MagicMock(
        return_value=MagicMock(
            stdout=SUCCESS_STDOUT,
            stderr="[WARNING] SoapyVOLKConverters: no VOLK config file found.\n",
            returncode=0,
        )
    )
    monkeypatch.setattr("core.soapy_runtime.subprocess.run", mock_run)
    assert check_sdrplay_plugin() is True


def test_check_sdrplay_service_running_detects_running(monkeypatch):
    mock_run = MagicMock(
        return_value=MagicMock(
            returncode=0,
            stdout="STATE              : 4  RUNNING\n",
        )
    )
    monkeypatch.setattr("core.soapy_runtime.subprocess.run", mock_run)
    assert check_sdrplay_service_running() is True


def test_check_sdrplay_service_running_detects_stopped(monkeypatch):
    mock_run = MagicMock(
        return_value=MagicMock(
            returncode=0,
            stdout="STATE              : 1  STOPPED\n",
        )
    )
    monkeypatch.setattr("core.soapy_runtime.subprocess.run", mock_run)
    assert check_sdrplay_service_running() is False
