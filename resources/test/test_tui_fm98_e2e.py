"""E2E FM ~98 MHz: Textual Pilot sobre XyzSDRApp (sim + integración SDRplay)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from resources.test.fm98_e2e_runner import run_fm98_e2e


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())


def test_fm98_e2e_sim(tmp_path: Path):
    export = tmp_path / "fm98_sim.json"
    report = _run_async(
        run_fm98_e2e(driver="simulated", export_path=export)
    )
    assert export.is_file()
    assert report.ok, report.to_dict()
    assert report.frames_applied >= 3
    assert abs(report.tuned_frequency_hz - 98_000_000.0) < 500_000.0


@pytest.mark.integration
@pytest.mark.slow
def test_fm98_e2e_sdrplay(require_sdrplay, tmp_path: Path):
    export = tmp_path / "fm98_hw.json"
    report = _run_async(
        run_fm98_e2e(driver="sdrplay", export_path=export)
    )
    assert export.is_file()
    assert report.ok, report.to_dict()
    assert report.frames_applied >= 5
