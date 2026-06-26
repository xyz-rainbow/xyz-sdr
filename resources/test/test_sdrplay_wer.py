"""Tests WER helper (sin admin / sin hardware)."""
from __future__ import annotations

import sys

import pytest

from core.sdrplay_wer import default_dumps_dir, enable_wer_minidumps, wer_status


def test_default_dumps_dir():
    path = default_dumps_dir()
    assert path.name == "dumps"
    assert "var" in path.parts


# On Windows, monkeypatching `os.name` to 'posix' trips a pytest internal
# (Path(os.getcwd()) vs self.config.invocation_params.dir in repr_failure)
# that crashes the whole pytest session on PosixPath mismatch. Skip there --
# the behavior is exercised implicitly by test_default_dumps_dir (which runs
# on every platform) plus the Linux/macOS matrix of CI.
_skip_non_windows_tests = pytest.mark.skipif(
    sys.platform == "win32",
    reason="monkeypatching os.name='posix' triggers pytest PosixPath crash on Windows runners",
)


@_skip_non_windows_tests
def test_wer_status_non_windows(monkeypatch):
    monkeypatch.setattr("core.sdrplay_wer.os.name", "posix")
    status = wer_status()
    assert status["supported"] is False


@_skip_non_windows_tests
def test_enable_wer_non_windows(monkeypatch):
    monkeypatch.setattr("core.sdrplay_wer.os.name", "posix")
    ok, msg = enable_wer_minidumps()
    assert ok is False
    assert "Windows" in msg
