"""Tests for unique driver Select options (Esc → settings)."""

from core.device import build_driver_select_options


def test_build_driver_select_options_skips_audio_and_unique_values():
    devices = [
        {"driver": "audio", "label": "Mic 1"},
        {"driver": "audio", "label": "Mic 2"},
        {"driver": "sdrplay", "label": "SDRplay RSP1A"},
        {"driver": "miri", "label": "Mirics SDRplay"},
    ]
    options, token_map, selected = build_driver_select_options(
        devices,
        current_driver="sdrplay",
    )

    values = [value for _, value in options]
    assert len(values) == len(set(values)), "Select values must be unique"
    assert "audio" not in values
    assert all(not v.startswith("audio") for v in values)
    assert "preset:sdrplay" in values
    assert "dev:0" in values or "dev:1" in values
    assert selected == "preset:sdrplay"
    assert token_map["preset:sdrplay"] == "sdrplay"
    assert isinstance(token_map["dev:0"], dict) or isinstance(token_map.get("dev:1"), dict)


def test_build_driver_select_options_matches_active_kwargs():
    devices = [
        {"driver": "sdrplay", "label": "SDRplay RSP1A", "serial": "ABC"},
        {"driver": "miri", "label": "Mirics SDRplay", "serial": "XYZ"},
    ]
    active = {"driver": "miri", "label": "Mirics SDRplay", "serial": "XYZ"}
    _, _, selected = build_driver_select_options(
        devices,
        current_driver="sdrplay",
        active_kwargs=active,
    )
    assert selected == "dev:1"
