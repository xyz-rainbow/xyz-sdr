"""Smoke tests headless de la TUI principal (Textual Pilot, sin hardware)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Awaitable, Callable

ROOT = Path(__file__).resolve().parents[2]


async def wait_until(
    pilot,
    predicate: Callable[[], bool],
    *,
    timeout_s: float,
    pause_s: float = 0.05,
) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if predicate():
            return True
        await pilot.pause(pause_s)
    return False


async def run_tui_lifecycle_smoke(
    *,
    driver: str = "simulated",
    config_path: str = "config/defaults.toml",
    terminal_size: tuple[int, int] = (100, 32),
    hardware_timeout_s: float = 15.0,
) -> None:
    """Arranque, pantalla principal, navegación mínima y salida limpia."""
    from main import load_config
    from tui.app import XyzSDRApp

    config = load_config(config_path)

    app = XyzSDRApp(
        driver=driver,
        config=config,
        config_path=config_path,
        auto_start_rx=False,
        debug_mode=False,
    )

    async with app.run_test(size=terminal_size) as pilot:
        ready = await wait_until(
            pilot,
            lambda: bool(app._hardware_ready),
            timeout_s=hardware_timeout_s,
        )
        if not ready:
            raise AssertionError("hardware never became ready")

        app.query_one("#spectrum")
        app.query_one("#waterfall")
        app.query_one("#status")

        await pilot.click("#spectrum")
        await pilot.pause(0.1)
        await pilot.press("up")
        await pilot.pause(0.1)
        await pilot.press("down")
        await pilot.pause(0.1)

        await pilot.press("q")
        await wait_until(pilot, lambda: app._graceful_shutdown, timeout_s=3.0)

    assert app._graceful_shutdown is True
