"""Tests del harness de diagnóstico espectro/waterfall."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from core.band_buffer import BandFrame
from tui.display_sync import DisplayFrameContext, DisplayLevelState, apply_band_frame_to_widgets
from tui.harness.export import build_export_report, evaluate_display_ok, export_display_snapshot
from tui.harness.host import HarnessRxHost
from tui.harness.app import SdrDisplayHarnessApp, build_harness_host
from tui.rx_worker import run_rx_iteration
from tui.widgets.spectrum_graph import SpectrumGraph
from tui.widgets.waterfall_timeline import WaterfallTimeline


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())


def _config() -> dict:
    return {
        "device": {
            "driver": "simulated",
            "sample_rate": 250_000.0,
            "center_freq": 7_100_000.0,
            "gain": 40.0,
        },
        "dsp": {"wbfm_bandwidth": 180_000},
        "display": {"waterfall_auto_level": True, "display_level_mode": "per_column"},
    }


def test_harness_rx_iteration_publishes_frames():
    host = HarnessRxHost(_config())
    host._device = MagicMock()
    host._device.is_simulated = True
    host._device.read_samples = lambda n: np.random.randn(n).astype(np.complex64) * 0.1
    host._rx_active = True

    result = run_rx_iteration(host)
    assert result is not None
    assert result.frame_published is True
    frame, snr, seq = host._band_mailbox.peek_latest()
    assert frame is not None
    assert seq >= 1


def test_apply_band_frame_to_widgets_populates_widgets():
    host = HarnessRxHost(_config())
    spectrum = SpectrumGraph()
    waterfall = WaterfallTimeline()
    spectrum._frequency_columns = 80
    waterfall._frequency_columns = 80
    frame = BandFrame(
        center_hz=7_100_000.0,
        sample_rate=250_000.0,
        timestamp=time.time(),
        band_cols=np.linspace(-85.0, -25.0, 256, dtype=np.float32),
    )
    display_cfg = host.config.get("display", {})
    seq, cols = apply_band_frame_to_widgets(
        frame,
        2.0,
        1,
        spectrum=spectrum,
        waterfall=waterfall,
        ctx=DisplayFrameContext(
            viewport_center=host.viewport_center,
            visible_span=host.visible_span,
            passband_center_hz=host.passband_center_hz,
            passband_width_hz=host.passband_width_hz,
            passband_preview_width_hz=None,
            display_width=80,
        ),
        display_cfg=display_cfg,
        level_state=DisplayLevelState(
            waterfall_auto_level=host.waterfall_auto_level,
            display_level_mode=host.display_level_mode,
            level_tracker=host._level_tracker,
        ),
    )
    assert seq == 1
    assert cols is not None
    assert spectrum._viewport_cols is not None
    assert len(waterfall._history) == 1


def test_build_export_report_display_ok():
    host = HarnessRxHost(_config())
    host.metrics.frames_applied = 5
    spectrum = SpectrumGraph()
    waterfall = WaterfallTimeline()
    spectrum._viewport_cols = np.linspace(-80.0, -30.0, 40)
    waterfall._history = [object()] * 3
    waterfall._slice_cache = np.linspace(-80.0, -30.0, 120).reshape(3, 40)
    report = build_export_report(host, spectrum, waterfall, min_frames=3)
    assert report.spectrum_has_viewport_cols is True
    assert report.waterfall_rows == 3
    assert evaluate_display_ok(report, min_frames=3) is True


def test_export_display_snapshot_writes_report(tmp_path: Path):
    host = HarnessRxHost(_config())
    host.metrics.frames_applied = 2
    app = SdrDisplayHarnessApp(host, export_root=tmp_path, min_frames=1)

    async def _run() -> None:
        async with app.run_test(size=(80, 24)) as pilot:
            spectrum = app.query_one("#spectrum", SpectrumGraph)
            waterfall = app.query_one("#waterfall", WaterfallTimeline)
            spectrum._frequency_columns = 60
            waterfall._frequency_columns = 60
            frame = BandFrame(
                center_hz=7_100_000.0,
                sample_rate=250_000.0,
                timestamp=time.time(),
                band_cols=np.linspace(-85.0, -25.0, 128, dtype=np.float32),
            )
            app._apply_display_frame(frame, 1.5, 1)
            await pilot.pause(0.1)
            export_display_snapshot(app, host, tmp_path / "cap", min_frames=1)

    _run_async(_run())

    assert (tmp_path / "cap" / "report.json").is_file()
    assert (tmp_path / "cap" / "frame.npz").is_file()
    data = json.loads((tmp_path / "cap" / "report.json").read_text(encoding="utf-8"))
    assert data["frames_applied"] >= 1


def test_build_harness_host_simulated():
    with patch("tui.harness.app.open_harness_device") as open_mock:
        dev = MagicMock()
        dev.driver = "simulated"
        dev.is_simulated = True
        open_mock.return_value = dev
        host = build_harness_host(_config(), driver="simulated", freq_hz=7_200_000.0)
    assert host.tuned_frequency == 7_200_000.0
    assert host._device is dev


def test_headless_cli_simulated_exit_code():
    from tui.harness.__main__ import run_headless, parse_args

    args = parse_args(
        [
            "--headless",
            "--driver",
            "simulated",
            "--duration",
            "0.5",
            "--min-frames",
            "1",
            "--width",
            "80",
            "--height",
            "20",
        ]
    )
    with patch("tui.harness.app.build_harness_host") as build_mock:
        host = HarnessRxHost(_config())
        host._device = MagicMock()
        host._device.is_simulated = True
        host._device.driver = "simulated"
        host._device.read_samples = lambda n: (np.random.randn(n).astype(np.complex64) * 0.2)
        build_mock.return_value = host
        code = _run_async(run_headless(args, _config()))
    assert code in (0, 1)
