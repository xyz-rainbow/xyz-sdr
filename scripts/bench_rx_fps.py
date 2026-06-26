#!/usr/bin/env python3
"""Benchmark RX + display FPS using XyzSDRApp (Textual run_test, no interactive TUI)."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    import numpy as np

    return float(np.percentile(values, pct))


async def run_bench(
    *,
    duration_s: float,
    sim: bool,
    width: int,
    height: int,
    config_path: str,
) -> dict:
    from main import load_config
    from tui.app import XyzSDRApp

    config = load_config(config_path)
    driver = "simulated" if sim else str(config.get("device", {}).get("driver", "sdrplay"))

    app = XyzSDRApp(
        driver=driver,
        config=config,
        config_path=config_path,
        debug_mode=True,
        auto_start_rx=True,
        headless_display=False,
    )

    samples: list[dict] = []
    errors: list[str] = []
    t_end = time.time() + duration_s

    async with app.run_test(size=(width, height)) as pilot:
        # Esperar hardware + auto-RX
        for _ in range(200):
            await pilot.pause(0.05)
            if app._hardware_ready and app._rx_active:
                break

        if not app._hardware_ready:
            errors.append("hardware_not_ready")
        if not app._rx_active:
            errors.append("rx_not_started")
            app._start_rx()

        window_start = time.time()
        last_frames = 0
        last_pub = 0

        while time.time() < t_end:
            await pilot.pause(0.5)
            now = time.time()
            window_s = max(now - window_start, 0.001)
            frames = int(app._display_frames_applied)
            _, _, pub_seq = app._band_mailbox.peek_latest()
            ui_fps = (frames - last_frames) / window_s if window_s > 0 else 0.0
            pub_rate = (pub_seq - last_pub) / window_s if window_s > 0 else 0.0

            with app._debug_lock:
                ui_proc = list(app._debug_ui_proc_ms)
                latencies = list(app._debug_frame_latency_ms)
                rx_proc = list(app._debug_rx_proc_ms)
                rx_iters = app._debug_rx_iter_count

            sample = {
                "t": round(now - (t_end - duration_s), 2),
                "ui_fps": round(ui_fps, 2),
                "pub_rate": round(pub_rate, 2),
                "frames_applied": frames,
                "pub_seq": int(pub_seq),
                "rx_active": bool(app._rx_active),
                "ui_draw_ms_avg": round(statistics.mean(ui_proc), 2) if ui_proc else 0.0,
                "ui_draw_ms_p95": round(_percentile(ui_proc, 95), 2) if ui_proc else 0.0,
                "latency_ms_avg": round(statistics.mean(latencies), 1) if latencies else 0.0,
                "latency_ms_p95": round(_percentile(latencies, 95), 1) if latencies else 0.0,
                "rx_iter_s": round(rx_iters / window_s, 2) if rx_iters else 0.0,
                "rx_proc_ms_avg": round(statistics.mean(rx_proc), 2) if rx_proc else 0.0,
            }
            if app._device and not app._device.is_simulated:
                st = app._device.stream_stats
                sample["iq_drop_pct"] = round(
                    getattr(st, "drop_rate", 0.0) * 100.0, 2
                )
            samples.append(sample)

            window_start = now
            last_frames = frames
            last_pub = pub_seq
            app._debug_rx_iter_count = 0

    return {
        "driver": driver,
        "sim": sim,
        "duration_s": duration_s,
        "terminal_size": [width, height],
        "errors": errors,
        "final_frames_applied": int(app._display_frames_applied),
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark RX/display FPS")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--sim", action="store_true")
    parser.add_argument("--width", type=int, default=120)
    parser.add_argument("--height", type=int, default=36)
    parser.add_argument("--config", default="config/defaults.toml")
    parser.add_argument("--out", type=Path, default=Path("var/harness/bench_rx_fps.json"))
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    report = asyncio.run(
        run_bench(
            duration_s=args.duration,
            sim=args.sim,
            width=args.width,
            height=args.height,
            config_path=args.config,
        )
    )
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
