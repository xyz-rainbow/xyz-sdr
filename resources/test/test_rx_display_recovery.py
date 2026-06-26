"""Tests: recuperación RX/display tras reinicios SDRplay y stop suave."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from core.band_buffer import BandFrame, BandFrameMailbox
from tui.app import XyzSDRApp
from tui.widgets.spectrum_graph import SpectrumGraph


def _sdrplay_device(*, sdr_open: bool = True):
    dev = MagicMock()
    dev.is_simulated = False
    dev.driver = "sdrplay"
    dev.sample_rate = 250_000.0
    dev._device_kwargs = {"driver": "sdrplay", "label": "RSP"}
    dev._sdr = object() if sdr_open else None
    dev.open.return_value = True
    return dev


def test_mailbox_peek_latest():
    mailbox = BandFrameMailbox()
    frame = BandFrame(
        center_hz=7_100_000.0,
        sample_rate=250_000.0,
        timestamp=time.time(),
        band_cols=np.zeros(8, dtype=np.float32),
    )
    mailbox.publish(frame, 1.0)
    peeked, snr, seq = mailbox.peek_latest()
    assert peeked is frame
    assert snr == 1.0
    assert seq == 1
    consumed, _, seq2 = mailbox.consume_if_new(0)
    assert consumed is frame
    assert seq2 == 1


def test_flush_display_does_not_set_rx_waiting_each_tick():
    app = XyzSDRApp()
    app._rx_active = True
    spectrum = SpectrumGraph()
    spectrum._frequency_columns = 40
    spectrum.set_rx_waiting(False)

    with patch.object(app, "query_one", return_value=spectrum), patch.object(
        app, "_band_mailbox"
    ) as mailbox_mock:
        mailbox_mock.consume_if_new.return_value = (None, 0.0, 0)
        mailbox_mock.peek_latest.return_value = (None, 0.0, 0)
        app._flush_display_frames()

    assert spectrum._rx_waiting is False


def test_recover_sdrplay_skips_api_fault_when_device_open():
    app = XyzSDRApp()
    app._device = _sdrplay_device(sdr_open=True)

    with patch("core.soapy_runtime.is_sdrplay_api_fault") as fault:
        assert app._recover_sdrplay_service_for_rx() is True
        fault.assert_not_called()


def test_stop_rx_does_not_shutdown_sdr_io():
    app = XyzSDRApp()
    app._rx_active = True
    app._rx_stop_event.set()
    app._device = _sdrplay_device(sdr_open=True)

    with patch("core.sdr_io.shutdown_sdr_io") as shutdown, patch.object(
        app, "query_one", return_value=SpectrumGraph()
    ):
        app._stop_rx()
        shutdown.assert_not_called()


def test_reopen_sdrplay_device_on_start_rx_when_flagged():
    app = XyzSDRApp()
    app._hardware_ready = True
    app._driver_changing = False
    app._device = _sdrplay_device(sdr_open=False)
    app._sdrplay_device_needs_reopen = True
    app.tuned_frequency = 7_100_000.0
    app.gain_value = 40.0

    with patch.object(app, "_maybe_restart_sdrplay_before_rx"), patch.object(
        app, "_invalidate_band_cache"
    ), patch.object(app, "_set_spectrum_rx_waiting"), patch.object(
        app, "_rx_worker"
    ), patch.object(app, "query_one", return_value=MagicMock()):
        app._start_rx()

    app._device.close.assert_called_once()
    app._device.open.assert_called_once()
    assert app._sdrplay_device_needs_reopen is False


def test_after_sdrplay_api_restart_closes_device_and_sets_flag():
    app = XyzSDRApp()
    app._device = _sdrplay_device(sdr_open=True)
    app._rx_active = False
    app._rx_stop_event.set()

    with patch.object(app, "_log") as log_mock, patch.object(
        app, "query_one", return_value=SpectrumGraph()
    ):
        app._after_sdrplay_api_restart()

    app._device.close.assert_called_once()
    assert app._sdrplay_device_needs_reopen is True
    assert any("INICIAR RX" in str(c) for c in log_mock.call_args_list)
