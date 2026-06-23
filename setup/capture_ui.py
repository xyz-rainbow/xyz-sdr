#!/usr/bin/env python3
"""Headless UI capture for xyz-sdr (Textual run_test + SVG screenshot)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def capture(
    output: Path,
    width: int = 120,
    height: int = 40,
    driver: str = "simulated",
) -> Path:
    from tui.app import XyzSDRApp

    app = XyzSDRApp(driver=driver)
    output.parent.mkdir(parents=True, exist_ok=True)

    async with app.run_test(size=(width, height)) as pilot:
        await pilot.pause(1.0)
        log = app.query_one("#log_panel")
        log.clear()
        log.write_line("[20:00:16] Volumen: 75%")
        log.write_line("[20:00:17] [ERROR] Bandwidth invalido: Select.NULL")
        await pilot.pause(0.25)
        saved = app.save_screenshot(filename=output.name, path=str(output.parent))
        print(f"log size={log.size} lines={log.line_count} region={log.region}")
        print(f"saved={saved}")
        return Path(saved)


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture xyz-sdr UI screenshot (SVG)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "docs" / "assets" / "ui_capture.svg",
    )
    parser.add_argument("--width", type=int, default=120)
    parser.add_argument("--height", type=int, default=40)
    parser.add_argument("--driver", default="simulated")
    args = parser.parse_args()
    asyncio.run(capture(args.output, args.width, args.height, args.driver))


if __name__ == "__main__":
    main()
