"""Tests del plugin de ejemplo xyz_sdr_cw_strict.

Estos tests verifican:
1. El módulo es importable.
2. El plugin implementa DemodulatorPlugin Protocol.
3. demodulate() produce audio finite.
4. discover_demodulators() lo encuentra cuando está instalado.
"""

from __future__ import annotations

import numpy as np
import pytest


def test_plugin_module_imports():
    """El módulo del plugin debe importar sin errores."""
    import xyz_sdr_cw_strict  # noqa: F401


def test_factory_callable():
    """make_cw_strict debe ser callable."""
    from xyz_sdr_cw_strict import make_cw_strict
    assert callable(make_cw_strict)


def test_factory_returns_demodulator():
    """make_cw_strict() debe devolver una instancia que implementa DemodulatorPlugin."""
    from core.plugins import DemodulatorPlugin
    from xyz_sdr_cw_strict import make_cw_strict

    plugin = make_cw_strict()
    assert isinstance(plugin, DemodulatorPlugin)
    assert plugin.name == "cw_strict"
    assert plugin.sample_rate_range[0] < plugin.sample_rate_range[1]
    assert plugin.audio_rate > 0


def test_demodulate_produces_finite_audio():
    """demodulate() debe devolver audio finite."""
    from xyz_sdr_cw_strict import make_cw_strict

    plugin = make_cw_strict()
    rng = np.random.default_rng(42)
    iq = (rng.standard_normal(2048) + 1j * rng.standard_normal(2048)).astype(np.complex64) * 0.1
    audio = plugin.demodulate(iq, sample_rate=250_000)
    assert isinstance(audio, np.ndarray)
    assert len(audio) > 0
    assert np.isfinite(audio).all()


@pytest.mark.skipif(
    True,  # Requiere `pip install -e examples/xyz_sdr_cw_strict` para descubrirlo
    reason=(
        "Requiere que el plugin esté instalado via pip install -e. "
        "Para activarlo: cd examples/xyz_sdr_cw_strict && pip install -e ."
    ),
)
def test_plugin_discoverable_via_entry_points():
    """Si el plugin está instalado, discover_demodulators() debe encontrarlo."""
    from core.plugins import discover_demodulators

    plugins = discover_demodulators()
    assert "cw_strict" in plugins