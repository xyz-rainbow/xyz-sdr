"""Tests de defaults.toml de fábrica (paridad GitHub main)."""

from __future__ import annotations

from pathlib import Path


def _load_defaults() -> dict:
    if True:
        import sys

        if sys.version_info >= (3, 11):
            import tomllib
        else:
            import tomli as tomllib
    path = Path(__file__).resolve().parents[2] / "config" / "defaults.toml"
    with path.open("rb") as handle:
        return tomllib.load(handle)


def test_defaults_factory_sample_rate_is_conservative():
    cfg = _load_defaults()
    # 250 kHz = ventana visible ~125 kHz (conservadora para RSP1 / PothosSDR 2021).
    assert cfg["device"]["sample_rate"] == 250_000


def test_defaults_factory_no_active_band_profile():
    cfg = _load_defaults()
    assert cfg["app"]["active_band_profile"] == ""


def test_defaults_factory_freq_span_matches_sample_rate():
    cfg = _load_defaults()
    assert cfg["display"]["freq_span_mhz"] == 0.5
