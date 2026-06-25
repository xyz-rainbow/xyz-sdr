"""Tests de crash_ui y splash de crash."""

from __future__ import annotations

from core.crash_ui import _map_windows_exit_code


def test_map_windows_access_violation():
    assert "access violation" in _map_windows_exit_code(3221225477).lower()
    assert "access violation" in _map_windows_exit_code(-1073741819).lower()


def test_print_crash_splash_no_raise(tmp_path, monkeypatch):
    from core.session_log import start_session_log, log_breadcrumb, close_session_log
    from tui.splash import print_crash_splash

    monkeypatch.setattr("core.session_log.project_root", lambda: tmp_path)
    log_path = start_session_log()
    log_breadcrumb("crash context line")
    print_crash_splash(log_path=log_path, reason="Test crash", animate=False, tail_lines=5)
    close_session_log()
