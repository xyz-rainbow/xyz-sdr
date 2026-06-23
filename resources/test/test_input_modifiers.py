"""Tests de detección de modificadores de entrada."""

from __future__ import annotations

from unittest.mock import patch

from core.input_modifiers import is_shift_pressed


def test_is_shift_pressed_from_event_flag():
    assert is_shift_pressed(event_shift=True) is True


def test_is_shift_pressed_false_without_event():
    with patch("core.input_modifiers.sys.platform", "linux"):
        assert is_shift_pressed(event_shift=False) is False


def test_is_shift_pressed_windows_fallback():
    with patch("core.input_modifiers.sys.platform", "win32"):
        with patch("ctypes.windll.user32.GetAsyncKeyState", return_value=0x8000):
            assert is_shift_pressed(event_shift=False) is True
