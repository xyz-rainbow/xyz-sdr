"""Tests de reinicio del servicio SDRplay."""

from __future__ import annotations

import subprocess
import sys

import pytest

from core.sdrplay_service import (
    is_native_crash_exit_code,
    maybe_restart_sdrplay_service_after_crash,
    previous_session_needs_service_restart,
    restart_sdrplay_service,
)


def test_is_native_crash_exit_code():
    assert is_native_crash_exit_code(3221225477)
    assert is_native_crash_exit_code(-1073741819)
    assert not is_native_crash_exit_code(0)


def test_previous_session_needs_restart_native_crash_kind():
    assert previous_session_needs_service_restart({"kind": "native_crash"})


def test_previous_session_needs_restart_exit_code():
    assert previous_session_needs_service_restart({"kind": "graceful", "exit_code": 3221225477})


def test_previous_session_graceful_no_restart():
    assert not previous_session_needs_service_restart({"kind": "graceful", "exit_code": 0})
    assert not previous_session_needs_service_restart(None)


def test_maybe_restart_skips_without_marker(monkeypatch):
    monkeypatch.setattr("core.sdrplay_service.restart_sdrplay_service", lambda **k: (True, "ok"))
    restarted, _msg = maybe_restart_sdrplay_service_after_crash(None)
    assert restarted is False


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Restart de SDRplayAPIService usa 'sc query'/'sc start', comandos Windows-only.",
)
def test_maybe_restart_after_abnormal(monkeypatch):
    calls: list[str] = []

    def _fake_restart(**_kwargs):
        calls.append("restart")
        return True, "restarted"

    monkeypatch.setattr("core.sdrplay_service.restart_sdrplay_service", _fake_restart)
    restarted, msg = maybe_restart_sdrplay_service_after_crash({"kind": "abnormal"})
    assert restarted is True
    assert msg == "restarted"
    assert calls == ["restart"]


def test_restart_treats_already_running_as_ok(monkeypatch):
    monkeypatch.setattr("core.sdrplay_service.os.name", "nt")
    monkeypatch.setattr("core.sdrplay_service.resolve_sdrplay_service_name", lambda: "SDRplayAPIService")
    monkeypatch.setattr("core.sdrplay_service.check_sdrplay_service_running", lambda: True)

    def fake_run(cmd, **_kwargs):
        if cmd[:2] == ["sc", "stop"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(
            cmd, 1, stdout="", stderr="[SC] StartService FAILED 1056: already running."
        )

    monkeypatch.setattr("core.sdrplay_service.subprocess.run", fake_run)
    ok, msg = restart_sdrplay_service()
    assert ok is True
    assert "ejecución" in msg.lower()


def test_restart_treats_1056_as_ok_when_sc_query_lags(monkeypatch):
    """1056 implica instancia activa aunque sc query aún no muestre RUNNING."""
    monkeypatch.setattr("core.sdrplay_service.os.name", "nt")
    monkeypatch.setattr("core.sdrplay_service.resolve_sdrplay_service_name", lambda: "SDRplayAPIService")
    monkeypatch.setattr("core.sdrplay_service.check_sdrplay_service_running", lambda: False)
    monkeypatch.setattr("core.sdrplay_service.wait_for_sdrplay_service_running", lambda *_a, **_k: False)

    def fake_run(cmd, **_kwargs):
        if cmd[:2] == ["sc", "stop"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(
            cmd, 1, stdout="", stderr="[SC] StartService FAILED 1056: already running."
        )

    monkeypatch.setattr("core.sdrplay_service.subprocess.run", fake_run)
    monkeypatch.setattr("core.sdrplay_service.time.sleep", lambda *_a: None)
    ok, msg = restart_sdrplay_service()
    assert ok is True
    assert "1056" in msg or "ejecución" in msg.lower()


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Restart de SDRplayAPIService usa 'sc query'/'sc start', comandos Windows-only.",
)
def test_maybe_restart_no_warning_on_1056(monkeypatch):
    monkeypatch.setattr(
        "core.sdrplay_service.restart_sdrplay_service",
        lambda **k: (
            False,
            "No se pudo iniciar SDRplayAPIService: [SC] StartService FAILED 1056: already running.",
        ),
    )
    monkeypatch.setattr("core.sdrplay_service.check_sdrplay_service_running", lambda: True)
    restarted, msg = maybe_restart_sdrplay_service_after_crash({"kind": "abnormal"})
    assert restarted is True
    assert "ejecución" in msg.lower() or "1056" in msg


def test_restart_sdrplay_service_non_windows(monkeypatch):
    monkeypatch.setattr("core.sdrplay_service.os.name", "posix")
    ok, msg = restart_sdrplay_service()
    assert ok is False
    assert "Windows" in msg
