"""Tests estructurales de core/plugins.py."""

from __future__ import annotations

import numpy as np
import pytest

from core.plugins import (
    PLUGIN_API_VERSION,
    BandProfilePlugin,
    DemodulatorPlugin,
    SDRDriverPlugin,
    discover_all_plugins,
    discover_band_profiles,
    discover_demodulators,
    discover_sdr_drivers,
)


def test_plugin_api_version_is_semver():
    """PLUGIN_API_VERSION debe seguir semver (X.Y.Z)."""
    parts = PLUGIN_API_VERSION.split(".")
    assert len(parts) == 3, f"Versión no es semver: {PLUGIN_API_VERSION}"
    assert all(p.isdigit() for p in parts), f"Componentes no numéricos: {parts}"


def test_protocols_are_runtime_checkable():
    """Los protocolos deben ser ``@runtime_checkable`` para isinstance()."""
    # Creamos implementaciones vacías y verificamos que isinstance las acepta
    class _StubDemod:
        name = "stub"
        sample_rate_range = (1.0, 2.0)
        audio_rate = 48_000

        def demodulate(self, iq, **kwargs):
            return np.zeros(10, dtype=np.float32)

    class _StubBand:
        profile_id = "stub"
        label = "Stub"

        def get_profile(self):
            return {}

    assert isinstance(_StubDemod(), DemodulatorPlugin)
    assert isinstance(_StubBand(), BandProfilePlugin)


def test_discover_demodulators_returns_dict():
    """Sin entry_points externos, debe devolver dict vacío (no lanzar)."""
    result = discover_demodulators()
    assert isinstance(result, dict)


def test_discover_band_profiles_returns_dict():
    result = discover_band_profiles()
    assert isinstance(result, dict)


def test_discover_sdr_drivers_returns_dict():
    result = discover_sdr_drivers()
    assert isinstance(result, dict)


def test_discover_all_plugins_includes_version():
    """discover_all_plugins debe incluir PLUGIN_API_VERSION para diagnóstico."""
    all_plugins = discover_all_plugins()
    assert all_plugins["api_version"] == PLUGIN_API_VERSION
    assert "demodulators" in all_plugins
    assert "band_profiles" in all_plugins
    assert "sdr_drivers" in all_plugins


def test_plugin_loading_tolerates_broken_entry_point(monkeypatch, caplog):
    """Si un entry_point falla al cargar, se loguea warning pero discovery continúa."""
    from core import plugins as plugins_mod

    class FakeEP:
        def __init__(self, name, load_fn):
            self.name = name
            self._load_fn = load_fn

        def load(self):
            return self._load_fn()

    def boom():
        raise RuntimeError("plugin explota")

    monkeypatch.setattr(
        plugins_mod,
        "_entry_points",
        lambda group: [FakeEP("broken", boom)] if group == "xyz_sdr.demodulators" else [],
    )

    with caplog.at_level("WARNING"):
        result = discover_demodulators()
    # No debe lanzar; el plugin roto simplemente no aparece
    assert "broken" not in result
    assert any("broken" in r.message for r in caplog.records)


def test_plugin_rejects_nonconforming_factory(monkeypatch, caplog):
    """Si el factory no implementa el protocolo, se loguea warning."""
    from core import plugins as plugins_mod

    class FakeEP:
        def __init__(self, name, factory):
            self.name = name
            self._factory = factory

        def load(self):
            return self._factory

    class NotAPlugin:
        """No implementa DemodulatorPlugin."""
        pass

    monkeypatch.setattr(
        plugins_mod,
        "_entry_points",
        lambda group: [FakeEP("wrong", NotAPlugin)] if group == "xyz_sdr.demodulators" else [],
    )

    with caplog.at_level("WARNING"):
        result = discover_demodulators()
    assert "wrong" not in result
    assert any("no implementa DemodulatorPlugin" in r.message for r in caplog.records)