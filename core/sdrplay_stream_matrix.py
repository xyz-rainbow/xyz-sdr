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
    dll_sha256: dict[str, str] = field(default_factory=dict)
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
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        text = (res.stdout or "") + (res.stderr or "")
        match = re.search(r"sdrplay_api_api_version=([\d.]+)", text, re.IGNORECASE)
        return match.group(1) if match else ""
    except Exception:
        return ""


def _load_service_events(out_dir: Path) -> list[str]:
    path = out_dir / "service-events.txt"
    if not path.is_file():
        env_path = os.environ.get("XYZ_SDR_MATRIX_SERVICE_EVENTS", "").strip()
        if env_path and os.path.isfile(env_path):
            path = Path(env_path)
        else:
            return []
    try:
        return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return []


def collect_environment(*, pip_freeze_file: str = "var/log/pip-freeze.txt") -> dict[str, Any]:
    plugin = find_sdrplay_soapy_module()
    api_dll = find_sdrplay_api_dll()
    plugin_hash = _sha256_file(plugin)
    api_hash = _sha256_file(api_dll)
    return {
        "python_version": sys.version.replace("\n", " "),
        "python_version_short": platform.python_version(),
        "pip_freeze_file": pip_freeze_file,
        "plugin_path": plugin or "",
        "plugin_mtime": _file_mtime_iso(plugin),
        "plugin_sha256": plugin_hash,
        "sdrplay_api_dll_path": api_dll or "",
        "sdrplay_api_dll_sha256": api_hash,
        "dll_sha256": {
            "sdrPlaySupport.dll": plugin_hash,
            "sdrplay_api.dll": api_hash,
        },
        "sdrplay_api_api_version": _probe_api_version(),
    }


def _ensure_pip_freeze(out_dir: Path) -> str:
    target = out_dir / "pip-freeze.txt"
    if not target.is_file():
        try:
            res = subprocess.run(
                [sys.executable, "-m", "pip", "freeze"],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(res.stdout or "", encoding="utf-8")
        except Exception:
            pass
    try:
        return str(target.relative_to(project_root()))
    except ValueError:
        return str(target)


def _ensure_python_version_file(out_dir: Path) -> None:
    target = out_dir / "python-version.txt"
    if target.is_file():
        return
    try:
        res = subprocess.run(
            [sys.executable, "-V"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        line = (res.stderr or res.stdout or sys.version).strip()
        target.write_text(line + "\n" + sys.version + "\n", encoding="utf-8")
    except Exception:
        target.write_text(sys.version + "\n", encoding="utf-8")


def _collect_event_log_snippet(minutes: int = 3) -> list[str]:
    if os.name != "nt":
        return []
    try:
        ps = (
            f"$start=(Get-Date).AddMinutes(-{minutes}); "
            "Get-WinEvent -FilterHashtable @{LogName='Application','System'; StartTime=$start} -MaxEvents 25 "
            "| ForEach-Object { "
            "$_.TimeCreated.ToString('o') + ' [' + $_.LogName + '] ' + $_.ProviderName "
            "+ ' Id=' + $_.Id + ' ' + $_.Message.Substring(0,[Math]::Min(240,$_.Message.Length)) "
            "}"
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            check=False,
            timeout=45,
        )
        return [ln.strip() for ln in (res.stdout or "").splitlines() if ln.strip()][:25]
    except Exception:
        return []


def _find_recent_minidump(*, since: float, dumps_dir: Path) -> str:
    candidates: list[tuple[float, str]] = []
    search_roots = [
        dumps_dir,
        Path(os.environ.get("LOCALAPPDATA", "")) / "CrashDumps",
        Path(os.environ.get("LOCALAPPDATA", "")) / "xyz-sdr" / "dumps",
    ]
    for root in search_roots:
        if not root.is_dir():
            continue
        try:
            for path in root.rglob("*.dmp"):
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                if mtime >= since:
                    candidates.append((mtime, str(path.resolve())))
        except OSError:
            continue
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def build_matrix_cases() -> list[MatrixRow]:
    cases: list[MatrixRow] = []
    rates = (None, 500_000, 250_000, 2_000_000)
    for stream_mode in STREAM_MODES:
        for fmt in STREAM_FORMATS:
            for rate in rates:
                cases.append(MatrixRow(sample_rate=rate, format=fmt, stream_mode=stream_mode))
    return cases


def _apply_env_meta(row: MatrixRow, env_meta: dict[str, Any], service_events: list[str]) -> None:
    row.python_version = env_meta.get("python_version", "")
    row.pip_freeze_file = env_meta.get("pip_freeze_file", "")
    row.plugin_path = env_meta.get("plugin_path", "")
    row.plugin_mtime = env_meta.get("plugin_mtime", "")
    row.plugin_sha256 = env_meta.get("plugin_sha256", "")
    row.sdrplay_api_dll_path = env_meta.get("sdrplay_api_dll_path", "")
    row.sdrplay_api_dll_sha256 = env_meta.get("sdrplay_api_dll_sha256", "")
    row.dll_sha256 = dict(env_meta.get("dll_sha256") or {})
    row.sdrplay_api_api_version = env_meta.get("sdrplay_api_api_version", "")
    row.service_events = list(service_events)


def _run_case(
    row: MatrixRow,
    env_meta: dict[str, Any],
    *,
    timeout_s: float,
    service_events: list[str],
    dumps_dir: Path,
    run_started: float,
) -> MatrixRow:
    row.timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _apply_env_meta(row, env_meta, service_events)

    if row.format != "CF32":
        row.result = "SKIP"
        row.stderr = f"format {row.format} planned Fase 0.1"
        return row

    case_started = datetime.now(timezone.utc).timestamp()
    per_path = max(timeout_s / 2.0, 30.0)
    pre = run_preflight(row.stream_mode, per_path_timeout_s=per_path)

    row.exit_code = pre.returncode
    row.last_step = pre.last_step
    row.stdout = pre.stdout or pre.detail or ""
    row.stderr = pre.stderr or pre.detail or ""
    if not row.stderr and pre.detail:
        row.stderr = pre.detail

    if pre.ok:
        row.result = "OK"
    elif pre.segfault:
        row.result = "SEGFAULT"
        row.event_log_entries = _collect_event_log_snippet(minutes=2)
        dump = _find_recent_minidump(since=min(run_started, case_started - 5.0), dumps_dir=dumps_dir)
        if dump:
            row.minidump_path = dump
    elif pre.last_step == "timeout":
        row.result = "TIMEOUT"
    else:
        row.result = "FAIL"

    return row


def run_matrix(
    *,
    out_dir: Path | None = None,
    timeout_s: float = DEFAULT_PREFLIGHT_TIMEOUT,
    dry_run: bool = False,
) -> MatrixReport:
    log_dir = out_dir or (project_root() / "var" / "log")
    log_dir.mkdir(parents=True, exist_ok=True)
    dumps_dir = log_dir / "dumps"
    dumps_dir.mkdir(parents=True, exist_ok=True)

    pip_path = _ensure_pip_freeze(log_dir)
    _ensure_python_version_file(log_dir)
    env_meta = collect_environment(pip_freeze_file=pip_path)
    service_events = _load_service_events(log_dir) or [
        f"{datetime.now(timezone.utc).isoformat()} matrix_start (no service-events.txt)"
    ]
    run_started = datetime.now(timezone.utc).timestamp()

    cases = build_matrix_cases()
    rows: list[MatrixRow] = []

    if dry_run:
        for case in cases:
            case.result = "PENDING"
            case.timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            _apply_env_meta(case, env_meta, service_events)
            rows.append(case)
    else:
        for case in cases:
            rows.append(
                _run_case(
                    case,
                    env_meta,
                    timeout_s=timeout_s,
                    service_events=service_events,
                    dumps_dir=dumps_dir,
                    run_started=run_started,
                )
            )

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
    segfaults = [r for r in report.rows if r.result == "SEGFAULT"]
    if segfaults:
        lines.append(f"segfault_rows: {len(segfaults)} (event_log captured per row)")
        if segfaults[0].minidump_path:
            lines.append(f"minidump_example: {segfaults[0].minidump_path}")
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
