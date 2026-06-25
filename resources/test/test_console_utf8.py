"""Tests de restauración de terminal tras TUI."""

from __future__ import annotations

from core.console_utf8 import _TERMINAL_RESTORE_SEQUENCE, restore_terminal_after_tui


def test_restore_terminal_includes_mouse_off_sequences(capsys):
    restore_terminal_after_tui()
    for token in ("?1000l", "?1002l", "?1003l", "?1006l", "?1007l", "?1015l", "?1049l", "?25h"):
        assert token in _TERMINAL_RESTORE_SEQUENCE
