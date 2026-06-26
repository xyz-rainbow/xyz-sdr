"""Tests de core/console_utf8.py (encoding + secuencias ANSI)."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from core.console_utf8 import (
    _TERMINAL_CLEAR_ALTERNATE_SEQUENCE,
    _TERMINAL_CLEAR_SCROLLBACK_SEQUENCE,
    _TERMINAL_PREPARE_SEQUENCE,
    _TERMINAL_RESTORE_SEQUENCE,
    _write_windows_console,
    clear_alternate_screen,
    clear_console_scrollback,
    configure_console_encoding,
    enter_alternate_screen,
    prepare_terminal_for_tui,
    register_windows_console_restore,
    restore_terminal_after_tui,
)


# ---------------------------------------------------------------------------
# Constantes / secuencias
# ---------------------------------------------------------------------------


def test_prepare_terminal_uses_alternate_screen_and_clear():
    for token in ("?1049h", "[2J", "[H", "?25l", "[3J"):
        assert token in _TERMINAL_PREPARE_SEQUENCE


def test_clear_console_scrollback_sequence():
    assert "[3J" in _TERMINAL_CLEAR_SCROLLBACK_SEQUENCE
    assert "[2J" in _TERMINAL_CLEAR_SCROLLBACK_SEQUENCE
    assert "[H" in _TERMINAL_CLEAR_SCROLLBACK_SEQUENCE


def test_clear_alternate_screen_sequence_has_clear_and_home():
    assert "[2J" in _TERMINAL_CLEAR_ALTERNATE_SEQUENCE
    assert "[H" in _TERMINAL_CLEAR_ALTERNATE_SEQUENCE


def test_restore_terminal_includes_mouse_off_sequences():
    for token in ("?1000l", "?1002l", "?1003l", "?1006l", "?1007l", "?1015l", "?1049l", "?25h"):
        assert token in _TERMINAL_RESTORE_SEQUENCE


def test_restore_terminal_disables_kitty_protocol():
    assert "?1049l" in _TERMINAL_RESTORE_SEQUENCE
    # kitty keyboard protocol off (escape < u)
    assert "<u" in _TERMINAL_RESTORE_SEQUENCE


# ---------------------------------------------------------------------------
# configure_console_encoding
# ---------------------------------------------------------------------------


def test_configure_console_encoding_returns_true_on_posix(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    assert configure_console_encoding() is True


def test_configure_console_encoding_skipped_when_ascii_splash(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("XYZ_SDR_ASCII_SPLASH", "1")
    # No debe invocar kernel32 ni SetConsoleOutputCP.
    with patch("core.console_utf8.sys.platform", "win32"):
        assert configure_console_encoding() is False


def test_configure_console_encoding_handles_reconfigure_failure(monkeypatch):
    """Si stdout.reconfigure falla, debe continuar sin romper."""

    class FakeStream:
        def __init__(self):
            self.calls = []

        def reconfigure(self, **_kw):
            raise OSError("nope")

    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("sys.stdout", FakeStream())
    monkeypatch.setattr("sys.stderr", FakeStream())
    assert configure_console_encoding() is True


def test_configure_console_encoding_handles_stdout_none(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("sys.stdout", None)
    monkeypatch.setattr("sys.stderr", None)
    assert configure_console_encoding() is True


def test_configure_console_encoding_windows_success(monkeypatch):
    """Windows happy path: llama kernel32 y devuelve True."""
    fake_kernel32 = MagicMock()
    fake_kernel32.GetStdHandle.return_value = 12345
    fake_kernel32.GetConsoleMode.return_value = True
    fake_kernel32.SetConsoleMode.return_value = None
    fake_kernel32.SetConsoleOutputCP.return_value = None
    fake_kernel32.SetConsoleCP.return_value = None

    fake_ctypes = MagicMock()
    fake_ctypes.windll.kernel32 = fake_kernel32

    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.delenv("XYZ_SDR_ASCII_SPLASH", raising=False)
    monkeypatch.setattr("sys.stdout", MagicMock(reconfigure=MagicMock()))
    monkeypatch.setattr("sys.stderr", MagicMock(reconfigure=MagicMock()))

    with patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        assert configure_console_encoding() is True
    fake_kernel32.SetConsoleOutputCP.assert_called_once_with(65001)
    fake_kernel32.SetConsoleMode.assert_called_once()


def test_configure_console_encoding_windows_failure(monkeypatch):
    """Si kernel32 falla, devuelve False en lugar de explotar."""
    fake_ctypes = MagicMock()
    fake_ctypes.windll.kernel32.GetStdHandle.side_effect = OSError("boom")

    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.delenv("XYZ_SDR_ASCII_SPLASH", raising=False)
    monkeypatch.setattr("sys.stdout", MagicMock(reconfigure=MagicMock()))
    monkeypatch.setattr("sys.stderr", MagicMock(reconfigure=MagicMock()))

    with patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        assert configure_console_encoding() is False


def test_configure_console_encoding_windows_skip_setconsole_mode_if_no_handle(monkeypatch):
    """Si GetConsoleMode falla, no debe llamar SetConsoleMode."""
    fake_kernel32 = MagicMock()
    fake_kernel32.GetStdHandle.return_value = 0  # handle inválido
    fake_kernel32.GetConsoleMode.return_value = False

    fake_ctypes = MagicMock()
    fake_ctypes.windll.kernel32 = fake_kernel32

    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.delenv("XYZ_SDR_ASCII_SPLASH", raising=False)
    monkeypatch.setattr("sys.stdout", MagicMock(reconfigure=MagicMock()))
    monkeypatch.setattr("sys.stderr", MagicMock(reconfigure=MagicMock()))

    with patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        configure_console_encoding()
    fake_kernel32.SetConsoleMode.assert_not_called()


# ---------------------------------------------------------------------------
# _write_windows_console
# ---------------------------------------------------------------------------


def test_write_windows_console_invokes_write_console_w(monkeypatch):
    fake_kernel32 = MagicMock()
    fake_kernel32.GetStdHandle.return_value = 0xFFFF

    fake_ctypes = MagicMock()
    fake_ctypes.windll.kernel32 = fake_kernel32
    fake_ctypes.c_ulong = MagicMock(return_value=MagicMock())
    fake_ctypes.c_void_p = lambda x: MagicMock(value=x) if x != -1 else MagicMock(value=0xDEAD)

    monkeypatch.setattr("sys.platform", "win32")
    with patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        _write_windows_console("hello")
    fake_kernel32.WriteConsoleW.assert_called_once()


def test_write_windows_console_skips_invalid_handle(monkeypatch):
    fake_kernel32 = MagicMock()
    fake_kernel32.GetStdHandle.return_value = None

    fake_ctypes = MagicMock()
    fake_ctypes.windll.kernel32 = fake_kernel32

    monkeypatch.setattr("sys.platform", "win32")
    with patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        _write_windows_console("hello")
    fake_kernel32.WriteConsoleW.assert_not_called()


def test_write_windows_console_swallows_exception(monkeypatch):
    fake_ctypes = MagicMock()
    fake_ctypes.windll.kernel32.GetStdHandle.side_effect = OSError("nope")

    with patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        # No debe lanzar.
        _write_windows_console("hello")


# ---------------------------------------------------------------------------
# clear_console_scrollback
# ---------------------------------------------------------------------------


def test_clear_console_scrollback_writes_to_tty(monkeypatch, capsys):
    monkeypatch.setattr("sys.platform", "linux")
    fake_stdout = MagicMock(isatty=lambda: True)
    monkeypatch.setattr("sys.stdout", fake_stdout)
    monkeypatch.setattr("sys.__stdout__", fake_stdout)
    clear_console_scrollback()
    fake_stdout.write.assert_called()
    fake_stdout.flush.assert_called()


def test_clear_console_scrollback_skips_non_tty(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    fake_stdout = MagicMock(isatty=lambda: False)
    monkeypatch.setattr("sys.stdout", fake_stdout)
    monkeypatch.setattr("sys.__stdout__", fake_stdout)
    clear_console_scrollback()
    fake_stdout.write.assert_not_called()


def test_clear_console_scrollback_handles_stdout_none(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("sys.stdout", None)
    monkeypatch.setattr("sys.__stdout__", None)
    # No debe lanzar.
    clear_console_scrollback()


def test_clear_console_scrollback_swallows_write_errors(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    fake = MagicMock(isatty=lambda: True, write=MagicMock(side_effect=OSError("boom")))
    monkeypatch.setattr("sys.stdout", fake)
    monkeypatch.setattr("sys.__stdout__", fake)
    clear_console_scrollback()


# ---------------------------------------------------------------------------
# enter_alternate_screen
# ---------------------------------------------------------------------------


def test_enter_alternate_screen_writes_alt_sequence(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    fake = MagicMock(isatty=lambda: True)
    monkeypatch.setattr("sys.stdout", fake)
    monkeypatch.setattr("sys.__stdout__", fake)
    enter_alternate_screen()
    args, _ = fake.write.call_args
    written = args[0]
    assert "?1049h" in written
    assert "[2J" in written


def test_enter_alternate_screen_skips_non_tty(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    fake = MagicMock(isatty=lambda: False)
    monkeypatch.setattr("sys.stdout", fake)
    monkeypatch.setattr("sys.__stdout__", fake)
    enter_alternate_screen()
    fake.write.assert_not_called()


def test_enter_alternate_screen_handles_stdout_none(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("sys.stdout", None)
    monkeypatch.setattr("sys.__stdout__", None)
    enter_alternate_screen()


# ---------------------------------------------------------------------------
# clear_alternate_screen
# ---------------------------------------------------------------------------


def test_clear_alternate_screen_writes(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    fake = MagicMock(isatty=lambda: True)
    monkeypatch.setattr("sys.stdout", fake)
    monkeypatch.setattr("sys.__stdout__", fake)
    clear_alternate_screen()
    fake.write.assert_called()


def test_clear_alternate_screen_skips_non_tty(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    fake = MagicMock(isatty=lambda: False)
    monkeypatch.setattr("sys.stdout", fake)
    monkeypatch.setattr("sys.__stdout__", fake)
    clear_alternate_screen()
    fake.write.assert_not_called()


def test_clear_alternate_screen_handles_stdout_none(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("sys.stdout", None)
    monkeypatch.setattr("sys.__stdout__", None)
    clear_alternate_screen()


# ---------------------------------------------------------------------------
# prepare_terminal_for_tui
# ---------------------------------------------------------------------------


def test_prepare_terminal_for_tui_default(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    fake = MagicMock(isatty=lambda: True)
    monkeypatch.setattr("sys.stdout", fake)
    monkeypatch.setattr("sys.__stdout__", fake)
    prepare_terminal_for_tui()
    written = fake.write.call_args[0][0]
    # Default usa PREPARE (incluye ?1049h)
    assert "?1049h" in written


def test_prepare_terminal_for_tui_already_alternate(monkeypatch):
    """Si ya estamos en alternate, usa CLEAR_ALTERNATE (no ?1049h)."""
    monkeypatch.setattr("sys.platform", "linux")
    fake = MagicMock(isatty=lambda: True)
    monkeypatch.setattr("sys.stdout", fake)
    monkeypatch.setattr("sys.__stdout__", fake)
    prepare_terminal_for_tui(already_alternate=True)
    written = fake.write.call_args[0][0]
    assert "?1049h" not in written
    assert "[2J" in written


def test_prepare_terminal_for_tui_handles_stdout_none(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("sys.stdout", None)
    monkeypatch.setattr("sys.__stdout__", None)
    prepare_terminal_for_tui()


def test_prepare_terminal_for_tui_skips_non_tty(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    fake = MagicMock(isatty=lambda: False)
    monkeypatch.setattr("sys.stdout", fake)
    monkeypatch.setattr("sys.__stdout__", fake)
    prepare_terminal_for_tui()
    fake.write.assert_not_called()


# ---------------------------------------------------------------------------
# restore_terminal_after_tui
# ---------------------------------------------------------------------------


def test_restore_terminal_after_tui_writes_to_all_streams(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    fake_out = MagicMock(isatty=lambda: True)
    fake_err = MagicMock(isatty=lambda: True)
    monkeypatch.setattr("sys.stdout", fake_out)
    monkeypatch.setattr("sys.__stdout__", fake_out)
    monkeypatch.setattr("sys.stderr", fake_err)
    monkeypatch.setattr("sys.__stderr__", fake_err)
    restore_terminal_after_tui()
    assert fake_out.write.call_count >= 1
    assert fake_err.write.call_count >= 1


def test_restore_terminal_after_tui_skips_none_streams(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("sys.stdout", None)
    monkeypatch.setattr("sys.__stdout__", None)
    monkeypatch.setattr("sys.stderr", None)
    monkeypatch.setattr("sys.__stderr__", None)
    # No debe lanzar.
    restore_terminal_after_tui()


def test_restore_terminal_after_tui_handles_write_exception(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    fake = MagicMock(isatty=lambda: True, write=MagicMock(side_effect=OSError("boom")))
    monkeypatch.setattr("sys.stdout", fake)
    monkeypatch.setattr("sys.__stdout__", fake)
    monkeypatch.setattr("sys.stderr", fake)
    monkeypatch.setattr("sys.__stderr__", fake)
    # No debe lanzar.
    restore_terminal_after_tui()


# ---------------------------------------------------------------------------
# register_windows_console_restore
# ---------------------------------------------------------------------------


def test_register_windows_console_restore_noop_on_posix(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    # No debe invocar ctypes ni lanzar.
    register_windows_console_restore()


def test_register_windows_console_restore_windows(monkeypatch):
    fake_kernel32 = MagicMock()
    fake_ctypes = MagicMock()
    fake_ctypes.windll.kernel32 = fake_kernel32
    fake_ctypes.WINFUNCTYPE = lambda *a, **kw: lambda f: f
    fake_ctypes.c_bool = MagicMock()
    fake_ctypes.c_uint = MagicMock()

    monkeypatch.setattr("sys.platform", "win32")
    with patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        register_windows_console_restore()
    fake_kernel32.SetConsoleCtrlHandler.assert_called_once()


def test_register_windows_console_restore_swallows_exception(monkeypatch):
    fake_ctypes = MagicMock()
    fake_ctypes.windll.kernel32.SetConsoleCtrlHandler.side_effect = OSError("nope")

    monkeypatch.setattr("sys.platform", "win32")
    with patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        # No debe lanzar.
        register_windows_console_restore()
