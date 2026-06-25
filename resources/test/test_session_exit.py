"""Tests del marcador de salida de sesión."""

from __future__ import annotations

import json

from core.session_exit import (
    clear_exit_marker,
    marker_was_written,
    read_exit_marker,
    write_exit_marker,
)


def test_write_and_read_exit_marker(tmp_path, monkeypatch):
    log_dir = tmp_path / "var" / "log"
    log_dir.mkdir(parents=True)
    monkeypatch.setattr("core.session_exit.project_root", lambda: tmp_path)

    clear_exit_marker()
    assert not marker_was_written()

    write_exit_marker("graceful", log_path=log_dir / "test.log", exit_code=0)
    assert marker_was_written()

    data = read_exit_marker()
    assert data is not None
    assert data["kind"] == "graceful"
    assert data["exit_code"] == 0
    assert "test.log" in data["log_path"]


def test_clear_exit_marker(tmp_path, monkeypatch):
    monkeypatch.setattr("core.session_exit.project_root", lambda: tmp_path)
    write_exit_marker("python_error", detail="boom")
    clear_exit_marker()
    assert read_exit_marker() is None
