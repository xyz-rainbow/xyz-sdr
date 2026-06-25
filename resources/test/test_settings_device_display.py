"""Tests de ficha de dispositivo en ajustes."""

from __future__ import annotations

from core.device import format_device_detail_lines, resolve_settings_device_display


def test_format_device_detail_with_serial():
    dev = {"driver": "sdrplay", "label": "SDRplay Dev0 RSP1 0000000001", "serial": "0000000001"}
    lines = format_device_detail_lines(dev)
    assert lines[0] == "SDRplay Dev0 RSP1"
    assert lines[1] == "0000000001"


def test_resolve_settings_device_from_cache():
    cached = [{"driver": "sdrplay", "label": "SDRplay Dev0 RSP1", "serial": "0000000001"}]
    token_map = {"preset:sdrplay": "sdrplay"}
    lines = resolve_settings_device_display(
        "preset:sdrplay",
        token_map,
        cached,
        current_driver="sdrplay",
        simulated=False,
    )
    assert "SDRplay Dev0 RSP1" in lines[0]
