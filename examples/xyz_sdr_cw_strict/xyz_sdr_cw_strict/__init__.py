"""
xyz-sdr CW Strict — ejemplo de plugin externo.

Implementa ``DemodulatorPlugin`` (ver core/plugins.py) y se registra
automáticamente via entry_points ``xyz_sdr.demodulators``.

Modo que añade: ``cw_strict``. Igual que ``cw`` pero con un filtro de
bandwidth mucho más estrecho (50 Hz vs 200 Hz por defecto) para aislar
señales CW密集 en bandas congestionadas.

Instalación (desarrollo):

.. code-block:: bash

    # Desde la raíz de xyz-sdr:
    pip install -e examples/xyz_sdr_cw_strict

Una vez instalado, el modo aparece en ``discover_demodulators()`` y se
puede usar::

    from core.plugins import discover_demodulators
    plugins = discover_demodulators()
    if "cw_strict" in plugins:
        cw_strict = plugins["cw_strict"]
        audio = cw_strict.demodulate(iq_samples, sample_rate=48_000)
"""

from __future__ import annotations

import numpy as np

from core.plugins import DemodulatorPlugin
from core.dsp import demodulate as core_demodulate, low_pass_filter


class CWStrictDemod:
    """CW demod con filtro ultra-estrecho (50 Hz)."""

    name = "cw_strict"
    sample_rate_range = (250_000.0, 1_000_000.0)
    audio_rate = 48_000

    def __init__(self, cw_bandwidth_hz: float = 50.0):
        self._cw_bandwidth_hz = cw_bandwidth_hz

    def demodulate(self, iq: np.ndarray, **kwargs) -> np.ndarray:
        """Delega a demodulate(mode='cw') y post-filtra con BW estricto."""
        # 1. Demod SSB-CW con el pipeline interno
        audio = core_demodulate(
            iq,
            mode="cw",
            sample_rate=kwargs.get("sample_rate", 48_000.0),
            audio_rate=self.audio_rate,
            passband_width_hz=200.0,
        )
        # 2. Filtro paso bajo agresivo para aislar tono CW
        return low_pass_filter(audio, self._cw_bandwidth_hz, self.audio_rate)


def make_cw_strict() -> DemodulatorPlugin:
    """Factory para entry_points."""
    return CWStrictDemod()