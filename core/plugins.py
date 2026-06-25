"""
xyz-sdr | core/plugins.py
Plugin contract versionado para demoduladores, band profiles y SDR drivers.

Entry points (pyproject.toml):
- xyz_sdr.demodulators  →  demodulator factories (Devolución objeto con interfaz DemodulatorPlugin)
- xyz_sdr.band_profiles  →  band profile loaders (BandProfilePlugin)
- xyz_sdr.sdr_drivers    →  SDR driver factories (SDRDriverPlugin)

Versionado
==========
``PLUGIN_API_VERSION`` sigue semver:
- PATCH: añadir campos opcionales, métodos default.
- MINOR: añadir protocolos o entry points nuevos.
- MAJOR: cambiar firmas de protocolos, romper backward compat.

Cualquier cambio incompatible debe bumpear MAJOR; los plugins externos
que dependan de la API deben declarar ``xyz_sdr_api_version`` en su setup.

Refs:
- .mavis/plans/deliverables/final_report.md §Fase 3 item 45
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

import numpy as np

logger = logging.getLogger(__name__)

PLUGIN_API_VERSION = "1.0.0"


# ── Protocolos ────────────────────────────────────────────────────────────────


@runtime_checkable
class DemodulatorPlugin(Protocol):
    """Contrato para demoduladores externos.

    Implementación típica::

        class MyDabDemod:
            name = "dab"
            sample_rate_range = (1_000_000.0, 2_048_000.0)
            audio_rate = 48_000

            def demodulate(self, iq, **kwargs):
                # tu lógica aquí
                return audio_float32

    El factory en entry_points debe devolver una INSTANCIA de la clase.
    """

    name: str
    sample_rate_range: tuple[float, float]
    audio_rate: int

    def demodulate(self, iq: np.ndarray, **kwargs) -> np.ndarray:
        """IQ samples (complex64) → audio (float32, mono)."""
        ...


@runtime_checkable
class BandProfilePlugin(Protocol):
    """Contrato para band profiles externos (alternativos a TOML)."""

    profile_id: str
    label: str

    def get_profile(self) -> dict:
        """Devuelve dict compatible con config/bands/*.toml."""
        ...


@runtime_checkable
class SDRDriverPlugin(Protocol):
    """Contrato para drivers SDR alternativos (raro; usar SoapySDR normalmente)."""

    driver_name: str

    def open(self, **kwargs) -> object:
        """Devuelve un objeto con interfaz similar a SoapySDR.Device."""
        ...


# ── Discovery ────────────────────────────────────────────────────────────────


def _entry_points(group: str) -> list:
    """Carga entry_points del grupo. Tolerante a importlib.metadata ausente."""
    try:
        from importlib import metadata as md
    except ImportError:  # pragma: no cover
        return []
    try:
        return list(md.entry_points(group=group))
    except Exception as exc:
        logger.warning("entry_points(%s) falló: %s", group, exc)
        return []


def discover_demodulators() -> dict[str, DemodulatorPlugin]:
    """Descubre demoduladores externos via entry_points ``xyz_sdr.demodulators``."""
    result: dict[str, DemodulatorPlugin] = {}
    for ep in _entry_points("xyz_sdr.demodulators"):
        try:
            factory = ep.load()
            instance = factory()
            if isinstance(instance, DemodulatorPlugin):
                result[ep.name] = instance
            else:
                logger.warning(
                    "Plugin %s no implementa DemodulatorPlugin: %s",
                    ep.name, type(instance).__name__,
                )
        except Exception as exc:
            logger.warning("Plugin demodulador %s falló al cargar: %s", ep.name, exc)
    return result


def discover_band_profiles() -> dict[str, BandProfilePlugin]:
    """Descubre band profiles externos via entry_points ``xyz_sdr.band_profiles``."""
    result: dict[str, BandProfilePlugin] = {}
    for ep in _entry_points("xyz_sdr.band_profiles"):
        try:
            factory = ep.load()
            instance = factory()
            if isinstance(instance, BandProfilePlugin):
                result[ep.name] = instance
            else:
                logger.warning(
                    "Plugin %s no implementa BandProfilePlugin", ep.name,
                )
        except Exception as exc:
            logger.warning("Plugin band_profile %s falló al cargar: %s", ep.name, exc)
    return result


def discover_sdr_drivers() -> dict[str, SDRDriverPlugin]:
    """Descubre SDR drivers externos via entry_points ``xyz_sdr.sdr_drivers``."""
    result: dict[str, SDRDriverPlugin] = {}
    for ep in _entry_points("xyz_sdr.sdr_drivers"):
        try:
            factory = ep.load()
            instance = factory()
            if isinstance(instance, SDRDriverPlugin):
                result[ep.name] = instance
        except Exception as exc:
            logger.warning("Plugin sdr_driver %s falló al cargar: %s", ep.name, exc)
    return result


def discover_all_plugins() -> dict:
    """Descubre todos los plugins. Útil para diagnóstico.

    Example::

        from core.plugins import discover_all_plugins
        print(discover_all_plugins())
        # {"demodulators": {...}, "band_profiles": {...}, "sdr_drivers": {...}}
    """
    return {
        "api_version": PLUGIN_API_VERSION,
        "demodulators": discover_demodulators(),
        "band_profiles": discover_band_profiles(),
        "sdr_drivers": discover_sdr_drivers(),
    }