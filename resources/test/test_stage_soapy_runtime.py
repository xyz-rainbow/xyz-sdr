"""Tests de core/stage_soapy_runtime.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.stage_soapy_runtime import format_stage_summary, stage_soapy_subset


def test_stage_soapy_subset_copies_core_files(tmp_path, monkeypatch):
    pothos_bin = tmp_path / "pothos" / "bin"
    pothos_bin.mkdir(parents=True)
    (pothos_bin / "SoapySDR.dll").write_bytes(b"soapy" * 1000)
    (pothos_bin / "SoapySDRUtil.exe").write_bytes(b"util" * 500)
    (pothos_bin / "pthreadVC2.dll").write_bytes(b"pt" * 100)

    dest = tmp_path / "drivers" / "win-x64" / "soapy"
    monkeypatch.setattr("core.stage_soapy_runtime.bundled_soapy_dir", lambda root=None: dest)
    monkeypatch.setattr(
        "core.stage_soapy_runtime.bundled_manifest_path",
        lambda root=None: tmp_path / "drivers" / "win-x64" / "manifest.json",
    )
    monkeypatch.setattr(
        "core.stage_soapy_runtime.project_root", lambda: tmp_path
    )

    report = stage_soapy_subset(
        pothos_bin=pothos_bin,
        dest_dir=dest,
        files=("SoapySDR.dll", "SoapySDRUtil.exe", "pthreadVC2.dll", "missing.dll"),
    )

    assert (dest / "SoapySDR.dll").is_file()
    assert (dest / "SoapySDRUtil.exe").is_file()
    assert report["missing_optional"] == ["missing.dll"]
    manifest = json.loads((tmp_path / "drivers" / "win-x64" / "manifest.json").read_text())
    assert "soapy_subset" in manifest


def test_stage_requires_soapysdr_dll(tmp_path):
    pothos_bin = tmp_path / "bin"
    pothos_bin.mkdir()
    (pothos_bin / "pthreadVC2.dll").write_bytes(b"x")

    with pytest.raises(FileNotFoundError, match="SoapySDR.dll"):
        stage_soapy_subset(
            pothos_bin=pothos_bin,
            dest_dir=tmp_path / "out",
            files=("pthreadVC2.dll",),
            dry_run=True,
        )


def test_format_stage_summary():
    text = format_stage_summary(
        {
            "source_bin": "C:/Pothos/bin",
            "dest_dir": "drivers/soapy",
            "dry_run": False,
            "artifacts": [{"name": "SoapySDR.dll", "size_bytes": 123}],
            "missing_optional": ["libusb-1.0.dll"],
        }
    )
    assert "SoapySDR.dll" in text
    assert "libusb-1.0.dll" in text
