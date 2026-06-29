"""E2E runner FM ~98 MHz con Textual Pilot (sim o SDRplay)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FM98_HZ = 98_000_000.0
FM98_BAND = "fm_broadcast"
FM98_DEMOD = "wbfm"
DEFAULT_CONFIG = "config/defaults.toml"
TERMINAL_SIZE = (120, 40)


@dataclass
class StepResult:
    name: str
    ok: bool
    duration_ms: float
    error: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class Fm98Report:
    ok: bool
    driver: str
    duration_s: float
    tuned_frequency_hz: float
    frames_applied: int
    rx_active: bool
    steps: list[StepResult]
    errors: list[str] = field(default_factory=list)
    export_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "driver": self.driver,
            "duration_s": round(self.duration_s, 2),
            "tuned_frequency_hz": self.tuned_frequency_hz,
            "frames_applied": self.frames_applied,
            "rx_active": self.rx_active,
            "errors": self.errors,
            "export_path": self.export_path,
            "steps": [asdict(s) for s in self.steps],
        }


def build_fm98_config(config_path: str = DEFAULT_CONFIG) -> tuple[dict, str]:
    """Carga defaults + perfil fm_broadcast y fija 98 MHz."""
    from main import load_config
    from core.band_profiles import load_band_profile, merge_configs

    cfg = load_config(config_path)
    band_cfg = load_band_profile(FM98_BAND)
    cfg = merge_configs(cfg, band_cfg)
    cfg.setdefault("device", {})["center_freq"] = FM98_HZ
    cfg.setdefault("dsp", {})["demod_mode"] = FM98_DEMOD
    return cfg, config_path


def _min_frames_for(driver: str) -> int:
    return 3 if driver == "simulated" else 5


def _hw_timeout(driver: str) -> float:
    return 15.0 if driver == "simulated" else 30.0


async def _run_step(
    name: str,
    fn: Callable[[], Awaitable[tuple[bool, str | None, dict[str, Any]]]],
) -> StepResult:
    t0 = time.perf_counter()
    try:
        ok, err, detail = await fn()
    except Exception as exc:
        return StepResult(
            name=name,
            ok=False,
            duration_ms=round((time.perf_counter() - t0) * 1000, 1),
            error=str(exc),
        )
    return StepResult(
        name=name,
        ok=ok,
        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
        error=err,
        detail=detail,
    )


async def _wait_until(
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


async def _query_exists(app, selector: str) -> bool:
    try:
        app.screen.query_one(selector)
        return True
    except Exception:
        try:
            app.query_one(selector)
            return True
        except Exception:
            return False


async def _wait_rx_state(pilot, app, *, active: bool, timeout_s: float = 3.0) -> bool:
    return await _wait_until(
        pilot,
        lambda: bool(app._rx_active) == active,
        timeout_s=timeout_s,
    )


async def _toggle_rx_via_ui(pilot, app) -> None:
    """Alterna RX con tecla S o botón si el binding no llega."""
    before = bool(app._rx_active)
    await pilot.press("s")
    if await _wait_rx_state(pilot, app, active=not before, timeout_s=1.5):
        return
    await pilot.click("#btn_rx")
    await _wait_rx_state(pilot, app, active=not before, timeout_s=2.0)


async def run_fm98_e2e(
    *,
    driver: str = "simulated",
    config_path: str = DEFAULT_CONFIG,
    export_path: Path | None = None,
    terminal_size: tuple[int, int] = TERMINAL_SIZE,
    min_frames: int | None = None,
) -> Fm98Report:
    """Ejecuta la secuencia E2E FM 98 MHz dentro de run_test."""
    from tui.app import XyzSDRApp
    from tui.widgets.settings_menu import SettingsScreen

    config, cfg_path = build_fm98_config(config_path)
    if min_frames is None:
        min_frames = _min_frames_for(driver)

    steps: list[StepResult] = []
    errors: list[str] = []
    t_start = time.perf_counter()

    app = XyzSDRApp(
        driver=driver,
        center_freq=FM98_HZ,
        demod_mode=FM98_DEMOD,
        config=config,
        config_path=cfg_path,
        band_profile=FM98_BAND,
        debug_mode=True,
        auto_start_rx=True,
        headless_display=False,
    )

    async with app.run_test(size=terminal_size) as pilot:
        hw_timeout = _hw_timeout(driver)

        async def step_wait_hardware() -> tuple[bool, str | None, dict[str, Any]]:
            ready = await _wait_until(
                pilot,
                lambda: bool(app._hardware_ready),
                timeout_s=hw_timeout,
            )
            if not ready:
                return False, "hardware_not_ready", {}
            return True, None, {"hardware_ready": True}

        steps.append(await _run_step("wait_hardware", step_wait_hardware))

        async def step_assert_tune_98() -> tuple[bool, str | None, dict[str, Any]]:
            delta = abs(float(app.tuned_frequency) - FM98_HZ)
            ok = delta < 500_000.0
            detail = {"tuned_hz": float(app.tuned_frequency), "delta_hz": delta}
            err = None if ok else f"tune_off_by_{delta:.0f}_hz"
            return ok, err, detail

        steps.append(await _run_step("assert_tune_98", step_assert_tune_98))

        async def step_rx_toggle() -> tuple[bool, str | None, dict[str, Any]]:
            if not app._rx_active:
                await _toggle_rx_via_ui(pilot, app)
            was_on = bool(app._rx_active)
            await _toggle_rx_via_ui(pilot, app)
            off_ok = await _wait_rx_state(pilot, app, active=False, timeout_s=2.0)
            await _toggle_rx_via_ui(pilot, app)
            on_ok = await _wait_rx_state(pilot, app, active=True, timeout_s=2.0)
            ok = was_on and off_ok and on_ok
            detail = {"was_on": was_on, "off_ok": off_ok, "on_ok": on_ok}
            err = None if ok else "rx_toggle_inconsistent"
            return ok, err, detail

        steps.append(await _run_step("rx_toggle", step_rx_toggle))

        async def step_scroll_zoom() -> tuple[bool, str | None, dict[str, Any]]:
            step0 = float(app.scroll_step)
            span0 = float(app.visible_span)
            await pilot.press("up")
            await pilot.pause(0.2)
            step_changed = float(app.scroll_step) != step0
            await pilot.press("ctrl+left")
            await pilot.pause(0.2)
            span_changed = float(app.visible_span) != span0
            await pilot.press("space")
            await pilot.pause(0.2)
            ok = step_changed or span_changed
            detail = {
                "step0_hz": step0,
                "step_hz": float(app.scroll_step),
                "span0_hz": span0,
                "span_hz": float(app.visible_span),
            }
            err = None if ok else "scroll_zoom_no_change"
            return ok, err, detail

        steps.append(await _run_step("scroll_zoom", step_scroll_zoom))

        async def step_sidebar() -> tuple[bool, str | None, dict[str, Any]]:
            before = bool(app._sidebar_collapsed)
            await pilot.press("ctrl+b")
            await pilot.pause(0.2)
            mid = bool(app._sidebar_collapsed)
            await pilot.press("ctrl+b")
            await pilot.pause(0.2)
            after = bool(app._sidebar_collapsed)
            ok = mid != before and after == before
            detail = {"before": before, "mid": mid, "after": after}
            err = None if ok else "sidebar_toggle_failed"
            return ok, err, detail

        steps.append(await _run_step("sidebar", step_sidebar))

        async def step_settings_open() -> tuple[bool, str | None, dict[str, Any]]:
            await pilot.press("escape")
            await pilot.pause(0.3)
            ok = isinstance(app.screen, SettingsScreen) and await _query_exists(
                app, "#btn_go_hardware"
            )
            err = None if ok else "settings_not_open"
            return ok, err, {"screen": type(app.screen).__name__}

        steps.append(await _run_step("settings_open", step_settings_open))

        async def step_settings_hardware() -> tuple[bool, str | None, dict[str, Any]]:
            await pilot.click("#btn_go_hardware")
            await pilot.pause(0.3)
            ok = await _query_exists(app, "#sw_auto_start_rx")
            err = None if ok else "hardware_page_not_visible"
            return ok, err, {}

        steps.append(await _run_step("settings_hardware", step_settings_hardware))

        async def step_settings_toggle_auto_rx() -> tuple[bool, str | None, dict[str, Any]]:
            before = bool(app._auto_start_rx)
            await pilot.click("#sw_auto_start_rx")
            await pilot.pause(0.2)
            after = bool(app._auto_start_rx)
            ok = after != before
            detail = {"before": before, "after": after}
            err = None if ok else "auto_rx_switch_unchanged"
            return ok, err, detail

        steps.append(await _run_step("settings_toggle_auto_rx", step_settings_toggle_auto_rx))

        async def step_settings_apply_close() -> tuple[bool, str | None, dict[str, Any]]:
            await pilot.click("#btn_apply_hardware")
            await pilot.pause(0.6)
            if await _query_exists(app, "#btn_close_settings"):
                await pilot.click("#btn_close_settings")
            else:
                await pilot.click("#btn_back_to_main_hw")
                await pilot.pause(0.3)
                await pilot.click("#btn_close_settings")
            if isinstance(app.screen, SettingsScreen):
                await pilot.press("escape")
            closed = await _wait_until(
                pilot,
                lambda: not isinstance(app.screen, SettingsScreen),
                timeout_s=3.0,
            )
            ok = closed
            err = None if ok else "settings_still_open"
            return ok, err, {"screen": type(app.screen).__name__}

        steps.append(await _run_step("settings_apply_close", step_settings_apply_close))

        async def step_capture() -> tuple[bool, str | None, dict[str, Any]]:
            await pilot.press("p")
            await pilot.pause(2.0)
            report = app.last_display_report
            if report is None:
                app.action_capture_display()
                await pilot.pause(1.0)
                report = app.last_display_report
            ok = report is not None
            detail: dict[str, Any] = {}
            if report is not None:
                detail["display_ok"] = bool(report.display_ok)
                detail["frames_applied"] = int(report.frames_applied)
            err = None if ok else "capture_report_missing"
            return ok, err, detail

        steps.append(await _run_step("capture", step_capture))

        async def step_frames_ok() -> tuple[bool, str | None, dict[str, Any]]:
            wait_s = 3.0 if driver == "simulated" else 5.0
            await pilot.pause(wait_s)
            frames = int(app._display_frames_applied)
            ok = frames >= min_frames
            detail = {"frames_applied": frames, "min_frames": min_frames}
            err = None if ok else f"frames_below_{min_frames}"
            return ok, err, detail

        steps.append(await _run_step("frames_ok", step_frames_ok))

    failed = [s for s in steps if not s.ok]
    if failed:
        errors.extend(f"{s.name}: {s.error}" for s in failed if s.error)

    report = Fm98Report(
        ok=not failed,
        driver=driver,
        duration_s=time.perf_counter() - t_start,
        tuned_frequency_hz=float(app.tuned_frequency),
        frames_applied=int(app._display_frames_applied),
        rx_active=bool(app._rx_active),
        steps=steps,
        errors=errors,
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
    return ROOT / "var" / "harness" / f"fm98_report_{tag}_{stamp}.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FM 98 MHz E2E pilot runner")
    parser.add_argument("--sim", action="store_true", help="Usar driver simulated")
    parser.add_argument("--hardware", action="store_true", help="Usar driver sdrplay")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--export", type=Path, default=None)
    parser.add_argument("--loop", type=int, default=1, help="Repeticiones (hardware flaky)")
    args = parser.parse_args(argv)

    if args.hardware:
        driver = "sdrplay"
    else:
        driver = "simulated"

    exit_code = 0
    for i in range(max(1, args.loop)):
        export = args.export
        if export is None:
            export = default_export_path(driver)
        elif args.loop > 1:
            export = export.with_name(f"{export.stem}_{i + 1}{export.suffix}")

        report = asyncio.run(
            run_fm98_e2e(
                driver=driver,
                config_path=args.config,
                export_path=export,
            )
        )
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        if not report.ok:
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
