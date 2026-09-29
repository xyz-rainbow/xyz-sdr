"""Soak bandwidth: crash temporal espectro/cascada."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from resources.test.bw_soak_runner import run_bw_soak

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())


def test_bw_cycle_sim_no_exceptions(tmp_path: Path):
    config_path = tmp_path / "defaults.toml"
    shutil.copy(_REPO_ROOT / "config" / "defaults.toml", config_path)
    report = _run_async(
        run_bw_soak(
            driver="simulated",
            duration_s=90.0,
            cycle_pause_s=1.0,
            include_sidebar=True,
            config_path=str(config_path),
            export_path=tmp_path / "bw_soak_sim.json",
        )
    )
    assert report.export_path is not None
    assert report.display_errors == 0, report.exceptions
    assert report.bandwidth_changes >= 3
    assert report.frames_applied >= 5
    assert report.ok, report.to_dict()


@pytest.mark.integration
@pytest.mark.slow
def test_bw_soak_sdrplay(require_sdrplay, tmp_path: Path):
    report = _run_async(
        run_bw_soak(
            driver="sdrplay",
            duration_s=120.0,
            cycle_pause_s=2.0,
            include_sidebar=True,
            export_path=tmp_path / "bw_soak_hw.json",
        )
    )
    assert report.display_errors == 0, report.exceptions
    assert report.ok, report.to_dict()
