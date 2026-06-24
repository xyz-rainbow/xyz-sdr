"""Tests de perfiles de banda (config/bands/)."""

from __future__ import annotations

from core.band_profiles import list_band_profiles, load_band_profile, merge_configs


def test_list_band_profiles_includes_defaults():
    profiles = dict(list_band_profiles())
    assert "fm_broadcast" in profiles
    assert "airband" in profiles
    assert profiles["fm_broadcast"]


def test_load_fm_broadcast_profile():
    profile = load_band_profile("fm_broadcast")
    assert profile["device"]["sample_rate"] == 2_048_000
    assert profile["dsp"]["demod_mode"] == "wbfm"


def test_merge_configs_deep_sections():
    base = {"device": {"gain": 30.0, "driver": "auto"}, "dsp": {"volume": 50.0}}
    override = {"device": {"gain": 45.0}, "dsp": {"demod_mode": "nbfm"}}
    merged = merge_configs(base, override)
    assert merged["device"]["gain"] == 45.0
    assert merged["device"]["driver"] == "auto"
    assert merged["dsp"]["volume"] == 50.0
    assert merged["dsp"]["demod_mode"] == "nbfm"
