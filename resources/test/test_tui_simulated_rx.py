"""Tests: modo simulación seleccionado desde la TUI (RX + espectro)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tui.app import XyzSDRApp


def _simulated_device():
    dev = MagicMock()
    dev.is_simulated = True
    dev.driver = "simulated"
    dev.sample_rate = 2_048_000.0
    dev._device_kwargs = None
    dev.same_device_as = lambda _k: False
    return dev


def test_change_device_driver_simulated_applies_desired_rx_without_reopen():
    app = XyzSDRApp()
    app.driver = "simulated"
    app._device = _simulated_device()
    app._hardware_ready = True
    app._driver_changing = False
    app._rx_active = False

    with patch.object(app, "_schedule_reopen_device") as reopen, patch.object(
        app, "_start_rx"
    ) as start_rx:
        ok = app.change_device_driver("simulated", desired_rx=True)

    assert ok is True
    reopen.assert_not_called()
    start_rx.assert_called_once()


def test_change_device_driver_simulated_stops_rx_when_switch_off():
    app = XyzSDRApp()
    app.driver = "simulated"
    app._device = _simulated_device()
    app._hardware_ready = True
    app._driver_changing = False
    app._rx_active = True

    with patch.object(app, "_schedule_reopen_device"), patch.object(app, "_stop_rx") as stop_rx:
        ok = app.change_device_driver("simulated", desired_rx=False)

    assert ok is True
    stop_rx.assert_called_once()


def test_sync_simulated_device_state_after_hardware_ready():
    app = XyzSDRApp(driver="sdrplay")
    device = _simulated_device()

    with patch.object(app, "change_bandwidth", return_value=True), patch.object(
        app, "_rebuild_zoom_levels"
    ), patch.object(app, "_adapt_viewport_to_bandwidth"), patch.object(
        app, "_refresh_bandwidth_select"
    ), patch.object(
        app, "query_one", return_value=MagicMock()
    ):
        app._on_hardware_ready(device, "preflight failed")

    assert app.driver == "simulated"
    assert app._sdrplay_preflight_ok is True


def test_switching_to_simulated_from_sdrplay_schedules_reopen():
    app = XyzSDRApp(driver="sdrplay")
    real = MagicMock()
    real.is_simulated = False
    real.driver = "sdrplay"
    real._device_kwargs = {"driver": "sdrplay", "label": "RSP"}
    app._device = real
    app._driver_changing = False

    with patch.object(app, "_schedule_reopen_device", return_value=True) as reopen:
        ok = app.change_device_driver("simulated", desired_rx=True)

    assert ok is True
    reopen.assert_called_once()
    assert app.driver == "simulated"
