"""Tests de funciones SDR: demod extendido, AUTO y config patch (sin TUI/Textual)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.auto_demod import resolve_auto_demod_mode
from core.bookmarks import parse_bookmarks_data, save_bookmarks
from core.config_store import patch_recorder_section, patch_scanner_section
from core.dsp import demodulate


def test_demod_modes():
    n = 8192
    t = np.arange(n) / 250_000
    iq = (np.exp(2j * np.pi * 10_000 * t)).astype(np.complex64)

    for mode in ("wbfm", "cw", "dsb", "raw"):
        audio = demodulate(iq, mode=mode, sample_rate=250_000, audio_rate=48_000)
        assert len(audio) > 0


def test_auto_demod_resolution():
    assert resolve_auto_demod_mode(100.6e6) == "wbfm"
    assert resolve_auto_demod_mode(121.5e6) == "nbfm"
    assert resolve_auto_demod_mode(446.0e6) == "nbfm"
    assert resolve_auto_demod_mode(7.1e6) == "lsb"
    assert resolve_auto_demod_mode(14.2e6) == "usb"


def _write_toml(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "defaults.toml"
    path.write_text(text, encoding="utf-8")
    return path


SAMPLE_TOML = """\
[recorder]
record_iq = true
record_audio = true

[scanner]
freq_start = 88_000_000
freq_end = 108_000_000
freq_step = 200_000
dwell_ms = 500
min_snr_db = 10.0
pause_on_signal = true
pause_resume_snr_db = 7.0
"""


def test_patch_recorder_and_scanner_config(tmp_path: Path):
    path = _write_toml(tmp_path, SAMPLE_TOML)

    patch_recorder_section(str(path), record_iq=False, record_audio=False)
    patch_scanner_section(
        str(path),
        freq_start=90_000_000,
        freq_end=100_000_000,
        freq_step=100_000,
        dwell_ms=1000,
        min_snr_db=15.5,
        pause_on_signal=False,
        pause_resume_snr_db=5.0,
    )

    text = path.read_text(encoding="utf-8")
    assert "record_iq = false" in text
    assert "record_audio = false" in text
    # tomli_w normaliza: sin underscores en números
    assert "freq_start = 90000000" in text
    assert "freq_end = 100000000" in text
    assert "freq_step = 100000" in text
    assert "dwell_ms = 1000" in text
    assert "min_snr_db = 15.5" in text
    assert "pause_on_signal = false" in text
    assert "pause_resume_snr_db = 5.0" in text


def test_bookmarks_toml_roundtrip(tmp_path: Path):
    bookmarks = [
        ("Cadena 100", 100.6e6, "wbfm"),
        ("Airband ATC", 121.5e6, "nbfm"),
    ]
    bookmarks_path = tmp_path / "bookmarks.toml"
    save_bookmarks(bookmarks_path, bookmarks)

    import sys

    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    with bookmarks_path.open("rb") as handle:
        data = tomllib.load(handle)

    assert parse_bookmarks_data(data) == bookmarks
