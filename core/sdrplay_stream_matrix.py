"""xyz-sdr | core/sdrplay_stream_matrix.py — matriz Soapy SDRplay RX (subprocesos)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from core.runtime_paths import project_root
from core.sdrplay_preflight import DEFAULT_PREFLIGHT_TIMEOUT, run_preflight
from core.soapy_runtime import find_sdrplay_api_dll, find_sdrplay_soapy_module

MatrixResult = Literal["OK", "SEGFAULT", "FAIL", "TIMEOUT", "SKIP", "PENDING"]
STREAM_FORMATS = ("CF32", "CS16")
STREAM_MODES = ("minimal", "legacy")


@dataclass
class MatrixRow:
    sample_rate: int | None
    format: str
    stream_mode: str
    kwargs: dict[str, Any] = field(default_factory=dict)
    version: str = ""
    plugin_mtime: str = ""
    plugin_path: str = ""
    plugin_sha256: str = ""
    sdrplay_api_dll_path: str = ""
    sdrplay_api_dll_sha256: str = ""
    sdrplay_api_api_version: str = ""
    python_version: str = ""
    pip_freeze_file: str = ""
    result: MatrixResult = "PENDING"
    exit_code: int | None = None
    last_step: str = ""
    stdout: str = ""
    stderr: str = ""
    minidump_path: str = ""
    event_log_entries: list[str] = field(default_factory=list)
    service_events: list[str] = field(default_factory=list)
    timestamp: str = ""


@dataclass
class MatrixReport:
    generated_at: str
    hostname: str
    rows: list[MatrixRow]
    environment: dict[str, Any] = field(default_factory=dict)
    best_row_index: int | None = None


def _sha256_file(path: str | None) -> str:
    if not path or not os.path.isfile(path):
        return ""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_mtime_iso(path: str | None) -> str:
    if not path or not os.path.isfile(path):
        return ""
    try:
        ts = os.path.getmtime(path)
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except OSError:
        return ""


def _probe_api_version() -> str:
    try:
        from core.soapy_runtime import _soapy_util_executable
        res = subprocess.run(
            [_soapy_util_executable(), "--probe=driver=sdrplay"],
            capture_output=True, text=True, check=False, timeout=20,
        )
        text = (res.stdout or "") + (res.stderr or "")
        match = re.search(r"sdrplay_api_api_version=([\d.]+)", text, re.IGNORECASE)
        return match.group(1) if match else ""
    except Exception:
        return ""


def collect_environment(*, pip_freeze_file: str = "var/log/pip-freeze.txt") -> dict[str, Any]:
    plugin = find_sdrplay_soapy_module()
    api_dll = find_sdrplay_api_dll()
    return {
        "python_version": platform.python_version(),
        "pip_freeze_file": pip_freeze_file,
        "plugin_path": plugin or "",
        "plugin_mtime": _file_mtime_iso(plugin),
        "plugin_sha256": _sha256_file(plugin),
        "sdrplay_api_dll_path": api_dll or "",
        "sdrplay_api_dll_sha256": _sha256_file(api_dll),
        "sdrplay_api_api_version": _probe_api_version(),
    }


def _ensure_pip_freeze(out_dir: Path) -> str:
    target = out_dir / "pip-freeze.txt"
    if not target.is_file():
        try:
            res = subprocess.run(
                [sys.executable, "-m", "pip", "freeze"],
                capture_output=True, text=True, check=False, timeout=60,
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(res.stdout or "", encoding="utf-8")
        except Exception:
            pass
    try:
        return str(target.relative_to(project_root()))
    except ValueError:
        return str(target)


def _collect_event_log_snippet(minutes: int = 5) -> list[str]:
    if os.name != "nt":
        return []
    try:
        ps = (
            f"$start=(Get-Date).AddMinutes(-{minutes}); "
            "Get-WinEvent -FilterHashtable @{LogName='Application','System'; StartTime=$start} -MaxEvents 15 "
            "| ForEach-Object { $_.TimeCreated.ToString('o') + ' ' + $_.ProviderName + ' ' + $_.Id }"
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, check=False, timeout=30,
        )
        return [ln.strip() for ln in (res.stdout or "").splitlines() if ln.strip()][:15]
    except Exception:
        return []


def build_matrix_cases() -> list[MatrixRow]:
    cases: list[MatrixRow] = []
    rates = (None, 500_000, 250_000, 2_000_000)
    for stream_mode in STREAM_MODES:
        for fmt in STREAM_FORMATS:
            for rate in rates:
                cases.append(MatrixRow(sample_rate=rate, format=fmt, stream_mode=stream_mode))
    return cases


def _run_case(row: MatrixRow, env_meta: dict[str, Any], *, timeout_s: float, service_events: list[str]) -> MatrixRow:
    row.timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row.python_version = env_meta.get("python_version", "")
    row.pip_freeze_file = env_meta.get("pip_freeze_file", "")
    row.plugin_path = env_meta.get("plugin_path", "")
    row.plugin_mtime = env_meta.get("plugin_mtime", "")
    row.plugin_sha256 = env_meta.get("plugin_sha256", "")
    row.sdrplay_api_dll_path = env_meta.get("sdrplay_api_dll_path", "")
    row.sdrplay_api_dll_sha256 = env_meta.get("sdrplay_api_dll_sha256", "")
    row.sdrplay_api_api_version = env_meta.get("sdrplay_api_api_version", "")
    row.service_events = list(service_events)
    if row.format != "CF32":
        row.result = "SKIP"
        row.stderr = f"format {row.format} planned Fase 0.1"
        return row
    per_path = max(timeout_s / 2.0, 30.0)
    pre = run_preflight(row.stream_mode, per_path_timeout_s=per_path)
    row.exit_code = pre.returncode
    row.last_step = pre.last_step
    detail = pre.detail or ""
    row.stdout = detail
    row.stderr = detail
    if pre.ok:
        row.result = "OK"
    elif pre.segfault:
        row.result = "SEGFAULT"
    elif pre.last_step == "timeout":
        row.result = "TIMEOUT"
    else:
        row.result = "FAIL"
    return row


def run_matrix(*, out_dir: Path | None = None, timeout_s: float = DEFAULT_PREFLIGHT_TIMEOUT, dry_run: bool = False) -> MatrixReport:
    log_dir = out_dir or (project_root() / "var" / "log")
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "dumps").mkdir(parents=True, exist_ok=True)
    pip_path = _ensure_pip_freeze(log_dir)
    env_meta = collect_environment(pip_freeze_file=pip_path)
    service_events = [f"{datetime.now(timezone.utc).isoformat()} matrix_start"]
    event_snippet = _collect_event_log_snippet()
    cases = build_matrix_cases()
    rows: list[MatrixRow] = []
    if dry_run:
        for case in cases:
            case.result = "PENDING"
            case.timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            rows.append(case)
    else:
        for case in cases:
            row = _run_case(case, env_meta, timeout_s=timeout_s, service_events=service_events)
            if event_snippet and row.result == "SEGFAULT":
                row.event_log_entries = event_snippet
            rows.append(row)
    best_idx = next((i for i, r in enumerate(rows) if r.result == "OK"), None)
    return MatrixReport(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        hostname=platform.node(),
        rows=rows,
        environment=env_meta,
        best_row_index=best_idx,
    )


def write_matrix_report(report: MatrixReport, out_dir: Path | None = None) -> Path:
    log_dir = out_dir or (project_root() / "var" / "log")
    log_dir.mkdir(parents=True, exist_ok=True)
    out_path = log_dir / f"sdrplay-matrix-{datetime.now():%Y%m%d-%H%M%S}.json"
    payload = {
        "generated_at": report.generated_at,
        "hostname": report.hostname,
        "environment": report.environment,
        "best_row_index": report.best_row_index,
        "rows": [asdict(row) for row in report.rows],
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def format_matrix_summary(report: MatrixReport) -> str:
    counts: dict[str, int] = {}
    for row in report.rows:
        counts[row.result] = counts.get(row.result, 0) + 1
    lines = [
        "=== xyz-sdr SDRplay stream matrix ===",
        f"generated_at: {report.generated_at}",
        f"hostname: {report.hostname}",
        f"rows: {len(report.rows)}",
        "results: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
    ]
    if report.best_row_index is not None:
        b = report.rows[report.best_row_index]
        lines.append(f"best: index={report.best_row_index} mode={b.stream_mode} rate={b.sample_rate}")
    else:
        lines.append("best: (none OK)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SDRplay Soapy stream matrix")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--timeout", type=float, default=DEFAULT_PREFLIGHT_TIMEOUT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    report = run_matrix(out_dir=args.out_dir, timeout_s=args.timeout, dry_run=args.dry_run)
    print(format_matrix_summary(report))
    out_path = write_matrix_report(report, args.out_dir)
    print(f"\n[OK] Informe: {out_path}")
    return 0 if report.best_row_index is not None else 1


if __name__ == "__main__":
    sys.exit(main())
