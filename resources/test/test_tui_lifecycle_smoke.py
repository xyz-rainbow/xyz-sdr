"""Smoke E2E: XyzSDRApp con Pilot (simulado, sin Soapy ni hardware)."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from main import StartupHardwareError, resolve_driver_without_hardware
from resources.test.tui_smoke_runner import run_tui_lifecycle_smoke

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())


def test_tui_lifecycle_smoke_simulated(tmp_path: Path):
    config_path = tmp_path / "defaults.toml"
    shutil.copy(_REPO_ROOT / "config" / "defaults.toml", config_path)
    _run_async(
        run_tui_lifecycle_smoke(
            driver="simulated",
            config_path=str(config_path),
        )
    )


def test_resolve_driver_without_hardware_defaults_to_simulated():
    logs: list[str] = []
    driver, devices = resolve_driver_without_hardware(
        strict=False,
        import_ok=False,
        help_text=None,
        startup_logs=logs,
        driver="sdrplay",
    )
    assert driver == "simulated"
    assert devices == []
    assert any("simulado" in line.lower() for line in logs)


def test_resolve_driver_without_hardware_strict_raises():
    with pytest.raises(StartupHardwareError):
        resolve_driver_without_hardware(
            strict=True,
            import_ok=False,
            help_text=None,
            startup_logs=[],
            driver="sdrplay",
        )
