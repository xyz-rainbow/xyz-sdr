"""Tests de core/sdrplay_usb.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from core.sdrplay_usb import CM_PROB_FAILED_INSTALL, SdrplayUsbStatus, probe_sdrplay_usb


def test_probe_sdrplay_usb_non_windows():
    with patch("core.sdrplay_usb.os.name", "posix"):
        status = probe_sdrplay_usb()
    assert status == SdrplayUsbStatus()


def test_probe_sdrplay_usb_failed_install():
    payload = json.dumps(
        {
            "Status": "Error",
            "ConfigManagerErrorCode": CM_PROB_FAILED_INSTALL,
            "InstanceId": "USB\\VID_1DF7&PID_2500\\abc",
        }
    )
    proc = MagicMock(returncode=0, stdout=payload, stderr="")
    with patch("core.sdrplay_usb.subprocess.run", return_value=proc):
        status = probe_sdrplay_usb()
    assert status.present is True
    assert status.ok is False
    assert status.problem_code == CM_PROB_FAILED_INSTALL
    assert status.problem_label == "driver_not_installed"


def test_probe_sdrplay_usb_symbolic_problem_code():
    payload = json.dumps(
        {
            "Status": "Error",
            "ConfigManagerErrorCode": "CM_PROB_FAILED_INSTALL",
            "InstanceId": "USB\\VID_1DF7&PID_2500\\abc",
        }
    )
    proc = MagicMock(returncode=0, stdout=payload, stderr="")
    with patch("core.sdrplay_usb.subprocess.run", return_value=proc):
        status = probe_sdrplay_usb()
    assert status.present is True
    assert status.ok is False
    assert status.problem_code == CM_PROB_FAILED_INSTALL


def test_probe_sdrplay_usb_ok():
    payload = json.dumps(
        {
            "Status": "OK",
            "ProblemCode": 0,
            "InstanceId": "USB\\VID_1DF7&PID_2500\\abc",
        }
    )
    proc = MagicMock(returncode=0, stdout=payload, stderr="")
    with patch("core.sdrplay_usb.subprocess.run", return_value=proc):
        status = probe_sdrplay_usb()
    assert status.present is True
    assert status.ok is True
