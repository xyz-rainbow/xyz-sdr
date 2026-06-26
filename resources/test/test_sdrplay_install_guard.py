"""Tests for SDRplay API install guard (process blocking detection)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from core.sdrplay_install_guard import (
    BlockingProcess,
    _python_blocks_api_install,
    _python_is_installer,
    list_blocking_processes,
    prepare_for_sdrplay_api_install,
    reset_soapy_bootstrap,
)


def test_python_is_installer_detects_install_drivers():
    cmd = r'"Y:\xyz-sdr\.venv\Scripts\python.exe" setup\install_drivers.py'
    assert _python_is_installer(cmd) is True
    assert _python_blocks_api_install(cmd) is False


def test_python_blocks_only_main_py():
    assert _python_blocks_api_install(r"python main.py --sim") is True
    assert _python_blocks_api_install(r"python -m pytest") is False


def test_list_blocking_processes_parses_json_array():
    payload = [
        {"ProcessId": 100, "Name": "SDRuno.exe", "CommandLine": "C:\\SDRuno\\SDRuno.exe"},
        {"ProcessId": 200, "Name": "python.exe", "CommandLine": "python main.py --sim"},
    ]
    with patch("core.sdrplay_install_guard.os.name", "nt"), patch(
        "core.sdrplay_install_guard._collect_protected_pids",
        return_value={50},
    ), patch(
        "core.sdrplay_install_guard.subprocess.run",
        return_value=MagicMock(returncode=0, stdout=json.dumps(payload)),
    ), patch("core.sdrplay_install_guard.os.getpid", return_value=50):
        found = list_blocking_processes()
    assert len(found) == 2
    assert found[0].name == "SDRuno.exe"
    assert found[1].pid == 200


def test_list_blocking_skips_installer_python():
    payload = [
        {
            "ProcessId": 200,
            "Name": "python.exe",
            "CommandLine": r'"Y:\xyz-sdr\.venv\Scripts\python.exe" setup\install_drivers.py',
        },
        {"ProcessId": 300, "Name": "python.exe", "CommandLine": "python main.py"},
    ]
    with patch("core.sdrplay_install_guard.os.name", "nt"), patch(
        "core.sdrplay_install_guard._collect_protected_pids",
        return_value={50, 200},
    ), patch(
        "core.sdrplay_install_guard.subprocess.run",
        return_value=MagicMock(returncode=0, stdout=json.dumps(payload)),
    ), patch("core.sdrplay_install_guard.os.getpid", return_value=50):
        found = list_blocking_processes()
    assert len(found) == 1
    assert found[0].pid == 300


def test_list_blocking_processes_skips_unrelated_python():
    payload = [{"ProcessId": 300, "Name": "python.exe", "CommandLine": "python -m pip install foo"}]
    with patch("core.sdrplay_install_guard.os.name", "nt"), patch(
        "core.sdrplay_install_guard._collect_protected_pids",
        return_value={50},
    ), patch(
        "core.sdrplay_install_guard.subprocess.run",
        return_value=MagicMock(returncode=0, stdout=json.dumps(payload)),
    ), patch("core.sdrplay_install_guard.os.getpid", return_value=50):
        found = list_blocking_processes()
    assert found == []


def test_blocking_process_summary_truncates():
    proc = BlockingProcess(pid=1, name="python.exe", command_line="x" * 120)
    assert len(proc.summary) <= 120
    assert "pid=1" in proc.summary


def test_terminate_process_uses_tree_only_for_external_apps():
    with patch("core.sdrplay_install_guard.subprocess.run", return_value=MagicMock(returncode=0)) as run:
        from core.sdrplay_install_guard import _terminate_process

        _terminate_process(42, tree=False)
        _terminate_process(99, tree=True)
    assert run.call_args_list[0].args[0] == ["taskkill", "/PID", "42", "/F"]
    assert run.call_args_list[1].args[0] == ["taskkill", "/PID", "99", "/F", "/T"]


def test_prepare_for_sdrplay_api_install_stops_service_and_resets_cache():
    messages: list[str] = []

    with patch("core.sdrplay_install_guard.list_blocking_processes", return_value=[]), patch(
        "core.sdrplay_service.stop_sdrplay_service",
        return_value=(True, "stopped"),
    ), patch("core.sdrplay_install_guard.reset_soapy_bootstrap") as reset_mock, patch(
        "core.sdrplay_install_guard.time.sleep"
    ):
        ok, msg = prepare_for_sdrplay_api_install(messages.append, lang="es")

    assert ok is True
    reset_mock.assert_called_once()
    assert any("Deteniendo SDRplayAPIService" in m for m in messages)


def test_prepare_fails_when_blocker_cannot_be_killed():
    blocker = BlockingProcess(pid=99, name="SDRuno.exe", command_line="SDRuno.exe")

    with patch(
        "core.sdrplay_install_guard.list_blocking_processes",
        side_effect=[[blocker], [blocker]],
    ), patch("core.sdrplay_install_guard._terminate_process", return_value=False):
        ok, _msg = prepare_for_sdrplay_api_install(lang="en")

    assert ok is False


def test_reset_soapy_bootstrap_clears_modules():
    import sys

    sys.modules["SoapySDR"] = object()
    with patch("core.soapy_runtime.clear_soapy_bootstrap_cache") as clear_mock:
        reset_soapy_bootstrap()
    clear_mock.assert_called_once()
    assert "SoapySDR" not in sys.modules
