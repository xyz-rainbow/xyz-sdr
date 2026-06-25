"""Tests WER helper (sin admin / sin hardware)."""
from __future__ import annotations

from core.sdrplay_wer import default_dumps_dir, enable_wer_minidumps, wer_status


def test_default_dumps_dir():
    path = default_dumps_dir()
    assert path.name == "dumps"
    assert "var" in path.parts


def test_wer_status_non_windows(monkeypatch):
    monkeypatch.setattr("core.sdrplay_wer.os.name", "posix")
    status = wer_status()
    assert status["supported"] is False


def test_enable_wer_non_windows(monkeypatch):
    monkeypatch.setattr("core.sdrplay_wer.os.name", "posix")
    ok, msg = enable_wer_minidumps()
    assert ok is False
    assert "Windows" in msg
