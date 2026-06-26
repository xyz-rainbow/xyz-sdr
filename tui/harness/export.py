"""
xyz-sdr | tui/harness/export.py
Exportación de capturas del harness (SVG, PNG, NPZ, report.json).
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from tui.harness.host import HarnessMetrics, HarnessRxHost
from tui.widgets.display_palette import cell_background, normalize_per_column
from tui.widgets.spectrum_graph import SpectrumGraph
from tui.widgets.waterfall_timeline import WaterfallTimeline


@dataclass
class DisplayExportContext:
    """Contexto mínimo para exportar capturas (app principal o harness)."""

    tuned_frequency_hz: float
    sample_rate: float
    visible_span_hz: float
    frames_published: int = 0
    frames_applied: int = 0
    last_snr: float = 0.0
    device: Any = None


@dataclass
class HarnessExportReport:
    display_ok: bool = False
    frames_published: int = 0
    frames_applied: int = 0
    waterfall_rows: int = 0
    spectrum_has_viewport_cols: bool = False
    psd_min_db: float | None = None
    psd_max_db: float | None = None
    device: dict[str, Any] = field(default_factory=dict)
    tuned_frequency_hz: float = 0.0
    sample_rate: float = 0.0
    visible_span_hz: float = 0.0
    export_paths: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rasterize_levels(
    rows: np.ndarray,
    floors: np.ndarray,
    ceilings: np.ndarray,
) -> np.ndarray:
    """Convierte matriz de dB a imagen RGB uint8 (H, W, 3)."""
    if rows.size == 0:
        return np.zeros((1, 1, 3), dtype=np.uint8)

    height, width = rows.shape
    image = np.zeros((height, width, 3), dtype=np.uint8)
    floor_row = np.asarray(floors, dtype=np.float64).reshape(-1)[:width]
    ceil_row = np.asarray(ceilings, dtype=np.float64).reshape(-1)[:width]
    if len(floor_row) < width:
        floor_row = np.pad(floor_row, (0, width - len(floor_row)), constant_values=-80.0)
    if len(ceil_row) < width:
        ceil_row = np.pad(ceil_row, (0, width - len(ceil_row)), constant_values=-20.0)

    for row_idx in range(height):
        norms = normalize_per_column(rows[row_idx], floor_row, ceil_row)
        for col_idx in range(width):
            norm = norms[col_idx]
            if np.isnan(norm):
                color = "#08080f"
            else:
                color = cell_background(float(norm), in_band=True)
            image[row_idx, col_idx] = _hex_to_rgb(color)
    return image


def _save_png(image: np.ndarray, path: Path) -> bool:
    try:
        from PIL import Image
    except ImportError:
        return False
    Image.fromarray(image).save(path)
    return True


def evaluate_display_ok(
    report: HarnessExportReport,
    *,
    min_frames: int = 1,
    min_contrast_db: float = 3.0,
) -> bool:
    if report.error:
        return False
    if report.frames_applied < min_frames:
        return False
    if report.waterfall_rows <= 0:
        return False
    if not report.spectrum_has_viewport_cols:
        return False
    if report.psd_min_db is None or report.psd_max_db is None:
        return False
    return (report.psd_max_db - report.psd_min_db) > min_contrast_db


def _context_from_host(host: HarnessRxHost) -> DisplayExportContext:
    return DisplayExportContext(
        tuned_frequency_hz=float(host.tuned_frequency),
        sample_rate=float(host.sample_rate),
        visible_span_hz=float(host.visible_span),
        frames_published=int(host.metrics.frames_published),
        frames_applied=int(host.metrics.frames_applied),
        last_snr=float(host.metrics.last_snr),
        device=host._device,
    )


def build_export_report(
    host_or_ctx: HarnessRxHost | DisplayExportContext,
    spectrum: SpectrumGraph | None,
    waterfall: WaterfallTimeline | None,
    *,
    min_frames: int = 1,
    error: str | None = None,
) -> HarnessExportReport:
    ctx = (
        host_or_ctx
        if isinstance(host_or_ctx, DisplayExportContext)
        else _context_from_host(host_or_ctx)
    )
    device = ctx.device
    report = HarnessExportReport(
        frames_published=ctx.frames_published,
        frames_applied=ctx.frames_applied,
        tuned_frequency_hz=float(ctx.tuned_frequency_hz),
        sample_rate=float(ctx.sample_rate),
        visible_span_hz=float(ctx.visible_span_hz),
        error=error,
    )
    if device is not None:
        report.device = {
            "driver": str(getattr(device, "driver", "")),
            "sample_rate": float(getattr(device, "sample_rate", ctx.sample_rate)),
            "is_simulated": bool(getattr(device, "is_simulated", False)),
        }

    viewport_cols = getattr(spectrum, "_viewport_cols", None) if spectrum is not None else None
    report.spectrum_has_viewport_cols = viewport_cols is not None and len(viewport_cols) > 0

    if waterfall is not None:
        report.waterfall_rows = len(getattr(waterfall, "_history", []) or [])
        history = waterfall.get_level_history()
        if history is not None and history.size:
            valid = history[~np.isnan(history)]
            if valid.size:
                report.psd_min_db = float(np.min(valid))
                report.psd_max_db = float(np.max(valid))
    elif viewport_cols is not None and len(viewport_cols):
        valid = viewport_cols[~np.isnan(viewport_cols)]
        if valid.size:
            report.psd_min_db = float(np.min(valid))
            report.psd_max_db = float(np.max(valid))

    report.display_ok = evaluate_display_ok(report, min_frames=min_frames)
    return report


def export_display_snapshot(
    app: Any,
    host_or_ctx: HarnessRxHost | DisplayExportContext,
    export_dir: Path,
    *,
    min_frames: int = 1,
) -> HarnessExportReport:
    """Exporta SVG, PNG, NPZ y report.json desde la TUI (principal o harness)."""
    ctx = (
        host_or_ctx
        if isinstance(host_or_ctx, DisplayExportContext)
        else _context_from_host(host_or_ctx)
    )
    export_dir = Path(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}

    spectrum: SpectrumGraph | None = None
    waterfall: WaterfallTimeline | None = None
    try:
        spectrum = app.query_one("#spectrum", SpectrumGraph)
    except Exception:
        pass
    try:
        waterfall = app.query_one("#waterfall", WaterfallTimeline)
    except Exception:
        pass

    report = build_export_report(ctx, spectrum, waterfall, min_frames=min_frames)

    try:
        saved = app.save_screenshot(filename="ui.svg", path=str(export_dir))
        paths["ui_svg"] = str(saved)
    except Exception as exc:
        report.error = report.error or f"screenshot failed: {exc}"

    frame = getattr(spectrum, "_band_frame", None) if spectrum is not None else None
    viewport_cols = getattr(spectrum, "_viewport_cols", None) if spectrum is not None else None
    npz_path = export_dir / "frame.npz"
    np.savez(
        npz_path,
        band_cols=getattr(frame, "band_cols", np.array([])),
        viewport_cols=viewport_cols if viewport_cols is not None else np.array([]),
        center_hz=np.float64(getattr(frame, "center_hz", ctx.tuned_frequency_hz)),
        sample_rate=np.float64(getattr(frame, "sample_rate", ctx.sample_rate)),
        snr=np.float64(ctx.last_snr),
        timestamp=np.float64(getattr(frame, "timestamp", time.time())),
    )
    paths["frame_npz"] = str(npz_path)

    floors = getattr(spectrum, "_column_floors", None) if spectrum is not None else None
    ceilings = getattr(spectrum, "_column_ceilings", None) if spectrum is not None else None
    if spectrum is not None and viewport_cols is not None and floors is not None and ceilings is not None:
        spec_img = _rasterize_levels(
            np.asarray(viewport_cols, dtype=np.float64).reshape(1, -1),
            np.asarray(floors, dtype=np.float64),
            np.asarray(ceilings, dtype=np.float64),
        )
        spec_png = export_dir / "spectrum.png"
        if _save_png(spec_img, spec_png):
            paths["spectrum_png"] = str(spec_png)

    if waterfall is not None:
        history = waterfall.get_level_history()
        floors_w = getattr(waterfall, "_column_floors", None)
        ceilings_w = getattr(waterfall, "_column_ceilings", None)
        if history is not None and floors_w is not None and ceilings_w is not None:
            wf_img = _rasterize_levels(history, floors_w, ceilings_w)
            wf_png = export_dir / "waterfall.png"
            if _save_png(wf_img, wf_png):
                paths["waterfall_png"] = str(wf_png)

    report.export_paths = paths
    report.display_ok = evaluate_display_ok(report, min_frames=min_frames)
    report_path = export_dir / "report.json"
    report_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    paths["report_json"] = str(report_path)
    report.export_paths = paths
    return report
