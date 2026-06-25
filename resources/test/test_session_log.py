"""Tests de log de sesión persistente."""

from __future__ import annotations

from pathlib import Path

from core.session_log import (
    close_session_log,
    get_session_log_path,
    log_breadcrumb,
    start_session_log,
    tail_session_log,
)


def test_start_session_log_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr("core.session_log.project_root", lambda: tmp_path)
    path = start_session_log()
    assert path is not None
    assert path.is_file()
    log_breadcrumb("test event")
    text = path.read_text(encoding="utf-8")
    assert "[breadcrumb] test event" in text
    close_session_log()
    assert get_session_log_path() is not None


def test_tail_session_log_returns_recent_lines(tmp_path, monkeypatch):
    monkeypatch.setattr("core.session_log.project_root", lambda: tmp_path)
    path = start_session_log()
    for i in range(30):
        log_breadcrumb(f"line-{i}")
    tail = tail_session_log(5)
    assert len(tail) == 5
    assert "line-29" in tail[-1]
    close_session_log()
