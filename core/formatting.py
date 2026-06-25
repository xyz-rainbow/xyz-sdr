"""
xyz-sdr | core/formatting.py
Funciones de formateo de unidades compartidas entre core/ y tui/.
"""

from __future__ import annotations


def format_bandwidth_hz(rate_hz: float) -> str:
    """Formatea un bandwidth (Hz) en formato verbose: '1.5 MHz', '250 kHz', '500 Hz'.

    Usado en logs, mensajes de error y diálogos donde prima la legibilidad.

    Args:
        rate_hz: bandwidth en Hz (puede ser float).

    Returns:
        Cadena formateada con unidad apropiada.
    """
    if rate_hz >= 1_000_000:
        value = rate_hz / 1_000_000
        text = f"{value:.3f}".rstrip("0").rstrip(".")
        return f"{text} MHz"
    if rate_hz >= 1_000:
        return f"{rate_hz / 1_000:.0f} kHz"
    return f"{rate_hz:.0f} Hz"


def format_hz_compact(hz: float) -> str:
    """Formatea Hz en formato compacto: '1.5M', '250k', '500Hz'.

    Usado en status bar y widgets donde prima el espacio horizontal.

    Args:
        hz: frecuencia en Hz (puede ser float).

    Returns:
        Cadena formateada compacta sin espacios.
    """
    if hz >= 1e6:
        return f"{hz / 1e6:.1f}M"
    elif hz >= 1e3:
        return f"{hz / 1e3:.0f}k"
    else:
        return f"{hz:.0f}Hz"