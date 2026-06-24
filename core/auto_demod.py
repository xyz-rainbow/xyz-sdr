"""
xyz-sdr | core/auto_demod.py
Selección heurística de modo de demodulación según frecuencia (modo AUTO).
"""

from __future__ import annotations


def resolve_auto_demod_mode(frequency_hz: float) -> str:
    """Devuelve el modo de demodulación más adecuado para la frecuencia dada."""
    freq = float(frequency_hz)

    # FM comercial 88–108 MHz
    if 88.0e6 <= freq <= 108.0e6:
        return "wbfm"

    # Aviación VHF 118–137 MHz (NBFM)
    if 118.0e6 <= freq <= 137.0e6:
        return "nbfm"

    # VHF/UHF amateur, PMR446
    if (
        (144.0e6 <= freq <= 146.0e6)
        or (430.0e6 <= freq <= 440.0e6)
        or (446.0e6 <= freq <= 447.0e6)
    ):
        return "nbfm"

    # AM broadcast HF 530 kHz – 1.7 MHz
    if 530.0e3 <= freq <= 1700.0e3:
        return "am"

    # HF amateur: LSB por debajo de 10 MHz, USB hasta 30 MHz
    if freq < 10.0e6:
        return "lsb"
    if freq < 30.0e6:
        return "usb"

    return "nbfm"
