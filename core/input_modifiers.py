"""
xyz-sdr | core/input_modifiers.py
Detección fiable de modificadores de teclado (p. ej. Shift+rueda en Windows).
"""

from __future__ import annotations

import sys


def is_shift_pressed(*, event_shift: bool = False) -> bool:
    """
    True si Shift está pulsado.

    En Windows la rueda del ratón suele llegar sin event.shift; se consulta
    GetAsyncKeyState como respaldo.
    """
    if event_shift:
        return True
    if sys.platform == "win32":
        try:
            import ctypes

            vk_shift = 0x10
            state = ctypes.windll.user32.GetAsyncKeyState(vk_shift)
            return bool(state & 0x8000)
        except Exception:
            return False
    return False
