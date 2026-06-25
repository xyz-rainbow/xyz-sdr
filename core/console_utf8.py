"""
xyz-sdr | core/console_utf8.py
Configura la consola Windows para UTF-8 y secuencias ANSI (splash / TUI).
"""

from __future__ import annotations

import os
import sys

# Secuencias que Textual (WindowsDriver) puede activar y hay que apagar siempre.
_TERMINAL_RESTORE_SEQUENCE = (
    "\033[<u"       # kitty keyboard protocol off
    "\033[?1049l"   # alternate screen off
    "\033[?25h"     # cursor visible
    "\033[?1004l"   # focus in/out off
    "\033[?2004l"   # bracketed paste off
    "\033[?1000l"   # mouse tracking off
    "\033[?1003l"
    "\033[?1015l"
    "\033[?1002l"
    "\033[?1006l"   # SGR mouse off (evita [555;32;8M en PS)
    "\033[?1007l"
    "\033[0m"
)


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


def _write_windows_console(text: str) -> None:
    """Escribe directamente en la consola (bypass wrappers de Textual)."""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        if not handle or handle == ctypes.c_void_p(-1).value:
            return
        written = ctypes.c_ulong(0)
        kernel32.WriteConsoleW(
            handle,
            text,
            len(text),
            ctypes.byref(written),
            None,
        )
    except Exception:
        pass


def prepare_terminal_for_tui() -> None:
    """Deja la consola lista para Textual tras el splash (no reabre stdout)."""
    configure_console_encoding()
    for stream in (sys.__stdout__, sys.stdout):
        try:
            if stream and stream.isatty():
                stream.write("\033[0m\033[?25h")
                stream.flush()
        except Exception:
            pass


def restore_terminal_after_tui() -> None:
    """Restaura ratón/cursor/colores tras salir de Textual (normal o crash)."""
    try:
        from core.startup_io import restore_stdio

        restore_stdio()
    except Exception:
        pass

    for stream in (sys.__stdout__, sys.__stderr__, sys.stdout, sys.stderr):
        try:
            if stream is None:
                continue
            stream.write(_TERMINAL_RESTORE_SEQUENCE)
            stream.flush()
        except Exception:
            pass

    if sys.platform == "win32":
        _write_windows_console(_TERMINAL_RESTORE_SEQUENCE)


def register_windows_console_restore() -> None:
    """Registra handler de consola Windows para restaurar TTY en Ctrl+C/cierre."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handler_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

        @handler_type
        def _handler(_ctrl_type: int) -> bool:
            restore_terminal_after_tui()
            return False

        kernel32.SetConsoleCtrlHandler(_handler, True)
    except Exception:
        pass
