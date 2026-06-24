"""Tests de core/config_store.py."""

from __future__ import annotations

from pathlib import Path

from core.config_store import (
    patch_device_section,
    patch_display_section,
    patch_dsp_section,
    patch_app_section,
    persist_band_profile,
)


def _write_toml(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "defaults.toml"
    path.write_text(text, encoding="utf-8")
    return path


SAMPLE_TOML = """\
[device]
driver       = "auto"      # driver hint
sample_rate  = 500_000
center_freq  = 100_600_000
gain         = 30.0

[dsp]
volume       = 75.0
demod_mode   = "nbfm"
squelch_enabled  = false
wbfm_bandwidth = 147_540

[display]
waterfall_auto_level = true
display_level_mode = "per_column"
freq_span_mhz = 0.5

[app]
active_band_profile = ""
"""


def test_patch_device_preserves_inline_comment(tmp_path: Path):
    path = _write_toml(tmp_path, SAMPLE_TOML)
    patch_device_section(str(path), driver="sdrplay", gain=42.0)
    text = path.read_text(encoding="utf-8")
    assert 'driver       = "sdrplay"' in text
    assert "# driver hint" in text
    assert "gain         = 42.0" in text


def test_patch_device_int_values(tmp_path: Path):
    path = _write_toml(tmp_path, SAMPLE_TOML)
    patch_device_section(str(path), sample_rate=2_048_000, center_freq=97_780_487)
    text = path.read_text(encoding="utf-8")
    assert "sample_rate  = 2_048_000" in text
    assert "center_freq  = 97_780_487" in text


def test_patch_dsp_bool_and_int(tmp_path: Path):
    path = _write_toml(tmp_path, SAMPLE_TOML)
    patch_dsp_section(
        str(path),
        squelch_enabled=True,
        wbfm_bandwidth=80_000,
        volume=50.0,
    )
    text = path.read_text(encoding="utf-8")
    assert "squelch_enabled  = true" in text
    assert "wbfm_bandwidth = 80_000" in text
    assert "volume       = 50.0" in text


def test_patch_display_section(tmp_path: Path):
    path = _write_toml(tmp_path, SAMPLE_TOML)
    patch_display_section(str(path), waterfall_auto_level=False)
    text = path.read_text(encoding="utf-8")
    assert "waterfall_auto_level = false" in text


def test_patch_missing_key_leaves_file_unchanged(tmp_path: Path):
    path = _write_toml(tmp_path, "[device]\ndriver = \"auto\"\n")
    patch_device_section(str(path), gain=99.0)
    text = path.read_text(encoding="utf-8")
    assert "gain" not in text


def test_patch_missing_file_is_noop(tmp_path: Path):
    missing = tmp_path / "missing.toml"
    patch_device_section(str(missing), driver="rtlsdr")


def test_persist_band_profile_writes_app_and_sections(tmp_path: Path):
    path = _write_toml(tmp_path, SAMPLE_TOML)
    profile = {
        "device": {"sample_rate": 2_048_000, "center_freq": 97_780_487, "gain": 40.0},
        "dsp": {"demod_mode": "wbfm", "volume": 80.0, "wbfm_bandwidth": 180_000},
        "display": {"display_level_mode": "per_column", "freq_span_mhz": 2.0},
    }
    persist_band_profile(str(path), "fm_broadcast", profile)
    text = path.read_text(encoding="utf-8")
    assert 'active_band_profile = "fm_broadcast"' in text
    assert "sample_rate  = 2_048_000" in text
    assert 'demod_mode   = "wbfm"' in text
    assert "freq_span_mhz = 2.0" in text

