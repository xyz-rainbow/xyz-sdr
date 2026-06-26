"""Tests for core/input_modifiers.py -- shift-key detection on Win + fallback."""

from __future__ import annotations

import sys

from core.input_modifiers import is_shift_pressed


def test_event_shift_true_short_circuits_to_true() -> None:
    # event_shift=True wins regardless of platform.
    assert is_shift_pressed(event_shift=True) is True


def test_event_shift_false_on_non_windows_returns_false() -> None:
    if sys.platform == "win32":
        # Windows fallback runs GetAsyncKeyState which may return either value.
        return
    assert is_shift_pressed(event_shift=False) is False