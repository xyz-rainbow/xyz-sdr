"""
xyz-sdr | core/console_utf8.py
Configura la consola Windows para UTF-8 y secuencias ANSI (splash / TUI).
"""

from __future__ import annotations

import os
import sys


def configure_console_encoding() -> bool:
    """
    Intenta dejar stdout en UTF-8.

    Returns:
        True si la consola debería mostrar Unicode correctamente.
    """
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if sys.platform != "win32":
        return True

    if os.environ.get("XYZ_SDR_ASCII_SPLASH", "").strip().lower() in ("1", "true", "yes"):
        return False

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)

        # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        std_out = -11
        handle = kernel32.GetStdHandle(std_out)
        mode = ctypes.c_uint32()
        if handle and kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        return True
    except Exception:
        return False


def prepare_terminal_for_tui() -> None:
    """Deja la consola lista para Textual tras el splash (no reabre stdout)."""
    configure_console_encoding()
    if sys.stdout.isatty():
        try:
            sys.stdout.write("\033[0m\033[?25h")
            sys.stdout.flush()
        except Exception:
            pass
