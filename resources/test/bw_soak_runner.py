"""Soak temporal: ciclo de bandwidth + interacciones display (espectro/cascada)."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_CONFIG = "config/defaults.toml"
FM98_HZ = 98_000_000.0
FM98_BAND = "fm_broadcast"
TERMINAL_SIZE = (120, 40)


@dataclass
class BwTransition:
    from_hz: float
    to_hz: float
    ok: bool
    duration_ms: float
    error: str | None = None


@dataclass
class BwSoakReport:
    ok: bool
    driver: str
    duration_s: float
    bandwidth_changes: int
    display_errors: int
    frames_applied: int
    last_sample_rate: float
    transitions: list[BwTransition]
    exceptions: list[str] = field(default_factory=list)
    export_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "driver": self.driver,
            "duration_s": round(self.duration_s, 2),
            "bandwidth_changes": self.bandwidth_changes,
            "display_errors": self.display_errors,
            "frames_applied": self.frames_applied,
            "last_sample_rate": self.last_sample_rate,
            "exceptions": self.exceptions,
            "export_path": self.export_path,
            "transitions": [asdict(t) for t in self.transitions],
        }


class _DisplayErrorHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if "Error actualizando espectro/cascada" in msg or "could not broadcast" in msg:
            self.messages.append(msg)


def build_soak_config(config_path: str = DEFAULT_CONFIG) -> tuple[dict, str]:
    from main import load_config
    from core.band_profiles import load_band_profile, merge_configs

    cfg = load_config(config_path)
    band_cfg = load_band_profile(FM98_BAND)
    cfg = merge_configs(cfg, band_cfg)
    cfg.setdefault("device", {})["center_freq"] = FM98_HZ
    cfg.setdefault("dsp", {})["demod_mode"] = "wbfm"
    return cfg, config_path


def _bandwidth_presets() -> list[float]:
    from core.device import BANDWIDTH_PRESETS

    return list(BANDWIDTH_PRESETS)


async def run_bw_soak(
    *,
    driver: str = "simulated",
    duration_s: float = 180.0,
    cycle_pause_s: float = 2.0,
    include_sidebar: bool = True,
    config_path: str = DEFAULT_CONFIG,
    export_path: Path | None = None,
    terminal_size: tuple[int, int] = TERMINAL_SIZE,
) -> BwSoakReport:
    from tui.app import XyzSDRApp

    config, cfg_path = build_soak_config(config_path)
    presets = _bandwidth_presets()
    transitions: list[BwTransition] = []
    t_start = time.perf_counter()
    display_handler = _DisplayErrorHandler()
    app_logger = logging.getLogger("tui.app")
    app_logger.addHandler(display_handler)

    app = XyzSDRApp(
        driver=driver,
        center_freq=FM98_HZ,
        demod_mode="wbfm",
        config=config,
        config_path=cfg_path,
        band_profile=FM98_BAND,
        debug_mode=True,
        auto_start_rx=True,
        headless_display=False,
    )

    cycle_index = 0
    try:
        async with app.run_test(size=terminal_size) as pilot:
            deadline = time.time() + duration_s
            for _ in range(400):
                await pilot.pause(0.05)
                if app._hardware_ready and app._rx_active:
                    break

            while time.time() < deadline:
                sequence = presets if cycle_index % 2 == 0 else list(reversed(presets))
                for idx in range(len(sequence) - 1):
                    if time.time() >= deadline:
                        break
                    from_hz = float(app.sample_rate)
                    to_hz = float(sequence[idx + 1])
                    if abs(from_hz - to_hz) < 1.0:
                        continue
                    t0 = time.perf_counter()
                    err: str | None = None
                    ok = False
                    try:
                        ok = bool(app.change_bandwidth(to_hz))
                        if not ok:
                            err = "change_bandwidth_returned_false"
                    except Exception as exc:
                        err = str(exc)
                    transitions.append(
                        BwTransition(
                            from_hz=from_hz,
                            to_hz=to_hz,
                            ok=ok and err is None,
                            duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                            error=err,
                        )
                    )
                    await pilot.pause(cycle_pause_s)

                if include_sidebar:
                    await pilot.press("ctrl+b")
                    await pilot.pause(0.3)
                    await pilot.press("ctrl+b")
                    await pilot.pause(0.3)
                    await pilot.press("shift+down")
                    await pilot.pause(0.2)

                cycle_index += 1
                await pilot.pause(0.5)
    finally:
        app_logger.removeHandler(display_handler)

    failed = [t for t in transitions if not t.ok]
    display_errors = len(display_handler.messages)
    report = BwSoakReport(
        ok=not failed and display_errors == 0,
        driver=driver,
        duration_s=time.perf_counter() - t_start,
        bandwidth_changes=len(transitions),
        display_errors=display_errors,
        frames_applied=int(app._display_frames_applied),
        last_sample_rate=float(app.sample_rate),
        transitions=transitions,
        exceptions=display_handler.messages[:50],
    )

    if export_path is not None:
        export_path = Path(export_path)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        report.export_path = str(export_path)

    return report


def default_export_path(driver: str) -> Path:
    tag = "sim" if driver == "simulated" else "hw"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return ROOT / "var" / "harness" / f"bw_soak_{tag}_{stamp}.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bandwidth soak test (display crash hunt)")
    parser.add_argument("--sim", action="store_true")
    parser.add_argument("--hardware", action="store_true")
    parser.add_argument("--duration", type=float, default=180.0, help="Seconds")
    parser.add_argument("--cycle-pause", type=float, default=2.0)
    parser.add_argument("--no-sidebar", action="store_true")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--export", type=Path, default=None)
    args = parser.parse_args(argv)

    driver = "sdrplay" if args.hardware else "simulated"
    export = args.export or default_export_path(driver)
    report = asyncio.run(
        run_bw_soak(
            driver=driver,
            duration_s=args.duration,
            cycle_pause_s=args.cycle_pause,
            include_sidebar=not args.no_sidebar,
            config_path=args.config,
            export_path=export,
        )
    )
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
