"""Tests for core/sdrplay_service.py -- service control + crash detection."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.sdrplay_service import (
    SDRPLAY_SERVICE_NAMES,
    _resolve_sc_start_after_stop,
    _sc_output_already_running,
    is_native_crash_exit_code,
    maybe_restart_sdrplay_service_after_crash,
    previous_session_needs_service_restart,
    wait_for_sdrplay_service_running,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_is_native_crash_exit_code_known_codes() -> None:
    # Common Windows crash exit codes (STATUS_ACCESS_VIOLATION, etc).
    assert is_native_crash_exit_code(3221225477) is True  # 0xC0000005 AV
    assert is_native_crash_exit_code(-1073741819) is True  # 0xC0000005 signed
    assert is_native_crash_exit_code(3221225725) is True  # 0xC00000FD STACK_OVERFLOW
    assert is_native_crash_exit_code(-1073741571) is True  # STACK_OVERFLOW signed


def test_is_native_crash_exit_code_normal_exit() -> None:
    assert is_native_crash_exit_code(0) is False
    assert is_native_crash_exit_code(1) is False
    assert is_native_crash_exit_code(-1) is False
    assert is_native_crash_exit_code(42) is False


def test_is_native_crash_exit_code_none_returns_false() -> None:
    assert is_native_crash_exit_code(None) is False


def test_sc_output_already_running_detects_1056() -> None:
    assert _sc_output_already_running("ERROR 1056: An instance of the service is already running.") is True
    assert _sc_output_already_running("1056") is True


def test_sc_output_already_running_detects_already_running_text() -> None:
    assert _sc_output_already_running("Service is already running") is True
    assert _sc_output_already_running("the service is ALREADY RUNNING.") is True


def test_sc_output_already_running_false_for_other_output() -> None:
    assert _sc_output_already_running("") is False
    assert _sc_output_already_running("ERROR 2: file not found") is False
    assert _sc_output_already_running("RUNNING") is False


def test_sc_output_already_running_handles_none_input() -> None:
    # Defensive: the source does (output or "").lower() so None -> "" -> False.
    assert _sc_output_already_running(None) is False


# ---------------------------------------------------------------------------
# _resolve_sc_start_after_stop
# ---------------------------------------------------------------------------


def test_resolve_sc_start_already_running_with_wait_succeeds() -> None:
    with patch("core.sdrplay_service.wait_for_sdrplay_service_running", return_value=True):
        ok, msg = _resolve_sc_start_after_stop("SDRplayAPIService", "1056", start_wait_s=2.0)
    assert ok is True
    assert "en ejecución" in msg.lower() or "ejecución" in msg.lower()


def test_resolve_sc_start_already_running_wait_times_out() -> None:
    # Even when wait+check fail, SC 1056 is treated as recoverable -> True.
    with patch("core.sdrplay_service.wait_for_sdrplay_service_running", return_value=False):
        with patch("core.sdrplay_service.check_sdrplay_service_running", return_value=False):
            with patch("core.sdrplay_service.time.sleep"):
                ok, msg = _resolve_sc_start_after_stop("SDRplayAPIService", "1056", start_wait_s=1.0)
    assert ok is True
    assert "1056" in msg


def test_resolve_sc_start_non_1056_failure_returns_false() -> None:
    # Non-1056, non-empty output -> False with the error echoed.
    ok, msg = _resolve_sc_start_after_stop("SDRplayAPIService", "ERROR 5", start_wait_s=1.0)
    assert ok is False
    assert "ERROR 5" in msg


def test_resolve_sc_start_empty_failure_returns_false() -> None:
    ok, msg = _resolve_sc_start_after_stop("SDRplayAPIService", "", start_wait_s=1.0)
    assert ok is False
    assert "No se pudo iniciar" in msg


def test_resolve_sc_start_non_recoverable_error_returns_false() -> None:
    # Not 1056, not already running -> treat as failure.
    ok, msg = _resolve_sc_start_after_stop("SDRplayAPIService", "ERROR 5", start_wait_s=1.0)
    assert ok is False
    assert "ERROR 5" in msg or "error" in msg.lower()


# ---------------------------------------------------------------------------
# previous_session_needs_service_restart
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["abnormal", "native_crash", "startup_error"])
def test_previous_session_needs_service_restart_true_for_crash_kinds(kind: str) -> None:
    marker = {"kind": kind, "details": "..."}
    assert previous_session_needs_service_restart(marker) is True


@pytest.mark.parametrize("kind", ["normal_shutdown", "user_exit", None, "", "ok"])
def test_previous_session_needs_service_restart_false_for_normal_kinds(kind: str | None) -> None:
    marker = {"kind": kind} if kind is not None else None
    if marker is not None:
        assert previous_session_needs_service_restart(marker) is False
    else:
        assert previous_session_needs_service_restart(None) is False


def test_previous_session_needs_service_restart_none_marker_returns_false() -> None:
    assert previous_session_needs_service_restart(None) is False


# ---------------------------------------------------------------------------
# wait_for_sdrplay_service_running
# ---------------------------------------------------------------------------


def test_wait_for_sdrplay_service_running_returns_true_immediately_when_running() -> None:
    with patch("core.sdrplay_service.check_sdrplay_service_running", return_value=True):
        assert wait_for_sdrplay_service_running(timeout_s=5.0) is True


def test_wait_for_sdrplay_service_running_returns_false_on_timeout() -> None:
    with patch("core.sdrplay_service.check_sdrplay_service_running", return_value=False):
        with patch("core.sdrplay_service.time.sleep"):
            assert wait_for_sdrplay_service_running(timeout_s=0.0) is False


def test_wait_for_sdrplay_service_running_returns_true_after_polling() -> None:
    # First 2 calls return False, third returns True.
    call_count = {"n": 0}

    def _check():
        call_count["n"] += 1
        return call_count["n"] >= 3

    with patch("core.sdrplay_service.check_sdrplay_service_running", side_effect=_check):
        with patch("core.sdrplay_service.time.sleep"):
            assert wait_for_sdrplay_service_running(timeout_s=10.0) is True
    assert call_count["n"] >= 3


# ---------------------------------------------------------------------------
# check_sdrplay_service_running (mocked subprocess)
# ---------------------------------------------------------------------------


def test_check_sdrplay_service_running_returns_true_on_non_windows() -> None:
    """On non-Windows platforms the helper short-circuits to True (sandbox friendly)."""
    with patch("os.name", "posix"):
        assert __import__("core.sdrplay_service", fromlist=["check_sdrplay_service_running"]).check_sdrplay_service_running() is True


def test_check_sdrplay_service_running_windows_no_service_name_returns_false() -> None:
    """When sc query for both names fails, return False (no service registered)."""
    import subprocess

    fake_proc = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")

    with patch("os.name", "nt"):
        with patch("subprocess.run", return_value=fake_proc):
            from core.sdrplay_service import check_sdrplay_service_running
            assert check_sdrplay_service_running() is False


def test_check_sdrplay_service_running_windows_running_detected() -> None:
    import subprocess

    fake_proc = subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout="SERVICE_NAME: SDRplayAPIService\n        STATE: 4 RUNNING",
        stderr="",
    )

    with patch("os.name", "nt"):
        with patch("subprocess.run", return_value=fake_proc):
            from core.sdrplay_service import check_sdrplay_service_running
            assert check_sdrplay_service_running() is True


# ---------------------------------------------------------------------------
# resolve_sdrplay_service_name
# ---------------------------------------------------------------------------


def test_resolve_sdrplay_service_name_returns_none_on_non_windows() -> None:
    with patch("os.name", "posix"):
        from core.sdrplay_service import resolve_sdrplay_service_name
        assert resolve_sdrplay_service_name() is None


def test_resolve_sdrplay_service_name_returns_first_match() -> None:
    import subprocess

    fake_proc = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    with patch("os.name", "nt"):
        with patch("subprocess.run", return_value=fake_proc) as mock_run:
            from core.sdrplay_service import resolve_sdrplay_service_name
            name = resolve_sdrplay_service_name()
    assert name == SDRPLAY_SERVICE_NAMES[0]
    assert mock_run.call_count == 1


def test_resolve_sdrplay_service_name_skips_failing_names() -> None:
    import subprocess

    fail_proc = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")
    ok_proc = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    responses = iter([fail_proc, ok_proc])

    def _side_effect(*args, **kwargs):
        return next(responses)

    with patch("os.name", "nt"):
        with patch("subprocess.run", side_effect=_side_effect):
            from core.sdrplay_service import resolve_sdrplay_service_name
            name = resolve_sdrplay_service_name()
    # Second service name matches.
    assert name == SDRPLAY_SERVICE_NAMES[1]


# ---------------------------------------------------------------------------
# maybe_restart_sdrplay_service_after_crash
# ---------------------------------------------------------------------------


def test_maybe_restart_after_crash_skipped_when_marker_is_none() -> None:
    """No prior session -> no restart needed."""
    # Should be a no-op even on Windows.
    with patch("os.name", "nt"):
        with patch("core.sdrplay_service.restart_sdrplay_service") as mock_restart:
            maybe_restart_sdrplay_service_after_crash(None)
    mock_restart.assert_not_called()


def test_maybe_restart_after_crash_skipped_when_kind_is_normal() -> None:
    marker = {"kind": "normal_shutdown"}
    with patch("os.name", "nt"):
        with patch("core.sdrplay_service.restart_sdrplay_service") as mock_restart:
            maybe_restart_sdrplay_service_after_crash(marker)
    mock_restart.assert_not_called()


def test_maybe_restart_after_crash_skipped_on_non_windows() -> None:
    marker = {"kind": "native_crash"}
    with patch("os.name", "posix"):
        with patch("core.sdrplay_service.restart_sdrplay_service") as mock_restart:
            maybe_restart_sdrplay_service_after_crash(marker)
    mock_restart.assert_not_called()


def test_maybe_restart_after_crash_triggers_restart_on_windows() -> None:
    marker = {"kind": "native_crash", "details": "AV at 0xDEADBEEF"}
    with patch("os.name", "nt"):
        with patch("core.sdrplay_service.restart_sdrplay_service", return_value=(True, "ok")) as mock_restart:
            ok, msg = maybe_restart_sdrplay_service_after_crash(marker)
    assert ok is True
    assert msg == "ok"
    mock_restart.assert_called_once_with()


def test_maybe_restart_after_crash_log_callback_called() -> None:
    marker = {"kind": "native_crash"}
    logs: list[str] = []

    def _log(msg: str) -> None:
        logs.append(msg)

    with patch("os.name", "nt"):
        with patch("core.sdrplay_service.restart_sdrplay_service", return_value=(True, "ok")):
            maybe_restart_sdrplay_service_after_crash(marker, log=_log)
    assert any("native_crash" in m for m in logs)


def test_maybe_restart_after_crash_1056_treated_as_running() -> None:
    """If restart fails but message contains 1056, return True (already running)."""
    marker = {"kind": "abnormal"}
    with patch("os.name", "nt"):
        with patch(
            "core.sdrplay_service.restart_sdrplay_service",
            return_value=(False, "ERROR 1056: instance already running"),
        ):
            with patch("core.sdrplay_service.wait_for_sdrplay_service_running", return_value=True):
                ok, msg = maybe_restart_sdrplay_service_after_crash(marker)
    assert ok is True
    assert "ya en ejecución" in msg.lower()


def test_maybe_restart_after_crash_returns_failure_message() -> None:
    """Restart fails with non-recoverable error -> return failure message."""
    marker = {"kind": "abnormal"}
    with patch("os.name", "nt"):
        with patch(
            "core.sdrplay_service.restart_sdrplay_service",
            return_value=(False, "ERROR 5: access denied"),
        ):
            with patch("core.sdrplay_service.wait_for_sdrplay_service_running", return_value=False):
                with patch("core.sdrplay_service.check_sdrplay_service_running", return_value=False):
                    ok, msg = maybe_restart_sdrplay_service_after_crash(marker)
    assert ok is False
    assert "ERROR 5" in msg