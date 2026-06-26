"""
xyz-sdr | tui/harness/__main__.py
CLI del harness de diagnóstico espectro/waterfall.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.runtime_paths import bootstrap_project_caches

bootstrap_project_caches(_ROOT)


def _load_config(path: str) -> dict:
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    with open(path, "rb") as handle:
        return tomllib.load(handle)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m tui.harness",
        description="Harness TUI espectro/waterfall para diagnóstico SDR",
    )
    parser.add_argument("--config", default="config/defaults.toml")
    parser.add_argument("--driver", default=None, help="sdrplay|simulated")
    parser.add_argument("--freq-hz", type=float, default=None)
    parser.add_argument("--gain", type=float, default=None)
    parser.add_argument("--sample-rate", type=float, default=None)
    parser.add_argument("--export-dir", type=Path, default=None)
    parser.add_argument("--headless", action="store_true", help="Captura automática sin TUI interactiva")
    parser.add_argument("--duration", type=float, default=8.0, help="Segundos RX en headless")
    parser.add_argument("--min-frames", type=int, default=5)
    parser.add_argument("--preflight", action="store_true", help="Preflight SDRplay antes de RX")
    parser.add_argument("--width", type=int, default=100)
    parser.add_argument("--height", type=int, default=32)
    return parser.parse_args(argv)


async def run_headless(args: argparse.Namespace, config: dict) -> int:
    from tui.harness.app import SdrDisplayHarnessApp, build_harness_host

    driver = args.driver or config.get("device", {}).get("driver", "simulated")
    if driver in ("sim",):
        driver = "simulated"

    host = build_harness_host(
        config,
        driver=str(driver),
        freq_hz=args.freq_hz,
        gain=args.gain,
        sample_rate=args.sample_rate,
    )
    export_dir = args.export_dir or Path("var/harness/headless_run")
    app = SdrDisplayHarnessApp(
        host,
        export_root=Path("var/harness"),
        auto_rx=True,
        headless_capture=True,
        capture_duration=float(args.duration),
        capture_export_dir=export_dir,
        min_frames=int(args.min_frames),
        run_preflight=bool(args.preflight),
    )

    async with app.run_test(size=(args.width, args.height)) as pilot:
        await pilot.pause(args.duration + 2.0)

    report = app.last_report
    if report is None:
        from tui.harness.export import export_display_snapshot

        report = export_display_snapshot(app, host, export_dir, min_frames=args.min_frames)

    payload = report.to_dict()
    print(json.dumps(payload, indent=2))
    return 0 if report.display_ok else 1


def run_interactive(args: argparse.Namespace, config: dict) -> int:
    from core.console_utf8 import prepare_terminal_for_tui, restore_terminal_after_tui
    from tui.harness.app import SdrDisplayHarnessApp, build_harness_host

    prepare_terminal_for_tui()
    try:
        driver = args.driver or config.get("device", {}).get("driver", "sdrplay")
        if driver in ("sim",):
            driver = "simulated"
        host = build_harness_host(
            config,
            driver=str(driver),
            freq_hz=args.freq_hz,
            gain=args.gain,
            sample_rate=args.sample_rate,
        )
        app = SdrDisplayHarnessApp(
            host,
            export_root=Path("var/harness"),
            run_preflight=bool(args.preflight),
            min_frames=int(args.min_frames),
        )
        app.run()
        return 0
    finally:
        restore_terminal_after_tui()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = Path(args.config)
    if not config_path.is_file():
        print(f"Config no encontrada: {config_path}", file=sys.stderr)
        return 2
    config = _load_config(str(config_path))

    if args.headless:
        return asyncio.run(run_headless(args, config))
    return run_interactive(args, config)


if __name__ == "__main__":
    raise SystemExit(main())
