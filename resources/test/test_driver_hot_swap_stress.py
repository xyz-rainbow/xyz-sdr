"""Stress tests for rapid hot-swapping of SDR drivers."""

from __future__ import annotations

import time
import pytest
import threading
from unittest.mock import MagicMock, patch

from core.device import SDRDevice, HardwareInitializationError
from tui.app import XyzSDRApp


@pytest.mark.slow
def test_sdr_device_hot_swap_stress():
    """Stress test opening, streaming, reading, and closing SDRDevice switching drivers."""
    drivers = ["simulated", "sim", "simulated"]
    
    # We will do a loop of rapid opening, streaming, and switching
    for i in range(15):
        driver = drivers[i % len(drivers)]
        dev = SDRDevice(driver=driver)
        
        # Open
        assert dev.open() is True
        assert dev.driver == "simulated"
        
        # Start stream
        dev.start_stream()
        
        # Read samples
        samples = dev.read_samples(1024)
        assert len(samples) == 1024
        
        # Change parameters
        dev.set_frequency(100e6)
        dev.set_sample_rate(500000.0)
        
        # Stop & close
        dev.stop_stream()
        dev.close()


@pytest.mark.slow
def test_tui_app_reopen_device_concurrency():
    """Verify that multiple concurrent driver change requests do not cause deadlocks or multiple concurrent threads."""
    with patch("tui.app.SDRDevice") as mock_sdr_device_class:
        # Set up mock device
        mock_dev = MagicMock()
        mock_dev.driver = "simulated"
        mock_dev.is_simulated = True
        mock_dev.sample_rate = 500000.0
        mock_sdr_device_class.return_value = mock_dev
        
        app = XyzSDRApp()
        app.driver = "simulated"
        app._device = mock_dev
        app._rx_active = False
        app._driver_changing = False
        
        with patch.object(app, "_reopen_device_async") as mock_reopen:
            # Schedule driver change 1 - should succeed
            res1 = app.change_device_driver("sdrplay")
            assert res1 is True
            assert app._driver_changing is True
            assert mock_reopen.call_count == 1
            
            # Schedule driver change 2 immediately - should be rejected because _driver_changing is True
            res2 = app.change_device_driver("sdrplay")
            assert res2 is False
            assert app._driver_changing is True
            assert mock_reopen.call_count == 1

