"""xyz-sdr | core/sdrplay_forensics.py — minidumps y Event Viewer tras segfault SDRplay."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from core.sdrplay_wer import default_dumps_dir, wer_status

_CRASH_KEYWORDS = re.compile(r"python|sdrplay|sdrPlay|Soapy|sdrPlaySupport", re.I)


def _wer_registry_roots() -> list[Path]:
    roots: list[Path] = []
    status = wer_status()
    folder = str(status.get("dump_folder") or "").strip()
    if folder:
        roots.append(Path(folder))
    return roots


def minidump_search_roots(*, dumps_dir: Path | None = None) -> list[Path]:
    """Directorios donde WER puede escribir .dmp de python.exe."""
    base = dumps_dir or default_dumps_dir()
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    roots: list[Path] = [
        base,
        *_wer_registry_roots(),
        local / "CrashDumps",
        local / "xyz-sdr" / "dumps",
    ]
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        if not root:
            continue
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def _iter_dump_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    found: list[Path] = []
    try:
        for path in root.iterdir():
            if not path.is_file() or path.suffix.lower() != ".dmp":
                continue
            name = path.name.lower()
            if name.startswith(("python", "sdrplay", "soapysdr")):
                found.append(path)
        for path in root.rglob("*.dmp"):
            if path not in found:
                found.append(path)
    except OSError:
        pass
    return found


def _wer_report_archive_root() -> Path:
    program_data = os.environ.get("ProgramData", r"C:\ProgramData")
    return Path(program_data) / "Microsoft" / "Windows" / "WER" / "ReportArchive"


def find_wer_report_artifacts(*, since: float) -> list[str]:
    """Copia Report.wer / .dmp recientes de WER ReportArchive (AppCrash_*)."""
    root = _wer_report_archive_root()
    if not root.is_dir():
        return []
    keywords = ("python", "sdrplay", "soapysdr")
    candidates: list[tuple[float, Path]] = []
    try:
        for entry in root.iterdir():
            if not entry.is_dir():
                continue
            name = entry.name.lower()
            if not name.startswith("appcrash_"):
                continue
            if not any(k in name for k in keywords):
                continue
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue
            if mtime >= since:
                candidates.append((mtime, entry))
    except OSError:
        return []

    candidates.sort(key=lambda item: item[0], reverse=True)
    staged: list[str] = []
    dest_root = default_dumps_dir() / "wer-reports"
    dest_root.mkdir(parents=True, exist_ok=True)
    for _mtime, folder in candidates[:5]:
        for pattern in ("*.dmp", "Report.wer", "*.txt"):
            for path in folder.glob(pattern):
                try:
                    if path.stat().st_mtime < since:
                        continue
                except OSError:
                    continue
                dest = dest_root / f"{folder.name}-{path.name}"
                try:
                    shutil.copy2(path, dest)
                    staged.append(str(dest.resolve()))
                except OSError:
                    staged.append(str(path.resolve()))
    return staged


def find_latest_wer_report_fallback(*, limit: int = 2) -> list[str]:
    """Últimos Report.wer de python/sdrplay (aunque sean anteriores al crash)."""
    root = _wer_report_archive_root()
    if not root.is_dir():
        return []
    keywords = ("python", "sdrplay", "soapysdr")
    candidates: list[tuple[float, Path]] = []
    try:
        for entry in root.iterdir():
            if not entry.is_dir() or not entry.name.lower().startswith("appcrash_"):
                continue
            if not any(k in entry.name.lower() for k in keywords):
                continue
            try:
                candidates.append((entry.stat().st_mtime, entry))
            except OSError:
                continue
    except OSError:
        return []
    candidates.sort(key=lambda item: item[0], reverse=True)
    staged: list[str] = []
    dest_root = default_dumps_dir() / "wer-reports"
    dest_root.mkdir(parents=True, exist_ok=True)
    for _mtime, folder in candidates[:limit]:
        report = folder / "Report.wer"
        if not report.is_file():
            continue
        dest = dest_root / f"historical-{folder.name}-Report.wer"
        try:
            shutil.copy2(report, dest)
            staged.append(str(dest.resolve()))
        except OSError:
            staged.append(str(report.resolve()))
    return staged


def find_recent_minidump(
    *,
    since: float,
    dumps_dir: Path | None = None,
    poll_seconds: float = 20.0,
    poll_interval: float = 1.0,
) -> str:
    """
    Busca el .dmp más reciente de python tras un segfault.

    WER escribe de forma asíncrona; se hace polling hasta *poll_seconds*.
    """
    deadline = time.time() + max(poll_seconds, 0.0)
    best = ""
    best_mtime = since
    roots = minidump_search_roots(dumps_dir=dumps_dir)

    while True:
        for root in roots:
            for path in _iter_dump_files(root):
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                if mtime >= since and mtime >= best_mtime:
                    best_mtime = mtime
                    best = str(path.resolve())
        if best:
            return best
        if time.time() >= deadline:
            break
        time.sleep(max(poll_interval, 0.25))
    return ""


def stage_minidump_for_report(
    source: str,
    *,
    dest_dir: Path,
    tag: str = "segfault",
) -> str:
    """Copia el .dmp al directorio de artefactos del repo (para zip/matrix JSON)."""
    src = Path(source)
    if not src.is_file():
        return ""
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = dest_dir / f"python-{tag}-{stamp}{src.suffix}"
    try:
        shutil.copy2(src, dest)
        return str(dest.resolve())
    except OSError:
        return source


def collect_event_log_after_crash(
    *,
    minutes: int = 5,
    since: float | None = None,
) -> tuple[list[str], str]:
    """
    Eventos Application/System recientes relacionados con python/sdrplay.

    Returns:
        (entradas, nota de error o vacío)
    """
    if os.name != "nt":
        return [], "event log: not Windows"

    entries, err = _collect_event_log_powershell(minutes=minutes)
    raw_entries = list(entries)
    if since is not None:
        entries = _filter_entries_since(entries, since=since)
    if entries:
        return entries[:25], err
    if raw_entries and since is not None:
        return [f"historical: {line}" for line in raw_entries[:8]], (
            err or "no Application events in crash window; included recent historical WER entries"
        )

    entries = _collect_event_log_wevtutil(minutes=minutes)
    raw_wevt = list(entries)
    if since is not None:
        entries = _filter_entries_since(entries, since=since)
    if entries:
        return entries[:25], err
    if raw_wevt and since is not None:
        return [f"historical: {line}" for line in raw_wevt[:8]], (
            err or "no Application events in crash window; included recent historical WER entries"
        )
    if entries:
        return entries[:25], err

    if err:
        return [], err
    return [], "event log: no matching Application/System events in window"


def _filter_entries_since(entries: list[str], *, since: float) -> list[str]:
    """Mantiene entradas con timestamp >= since (tolerancia 15 s)."""
    kept: list[str] = []
    for line in entries:
        ts: float | None = None
        if len(line) >= 19 and line[4] == "-" and line[10] == "T":
            try:
                ts = datetime.fromisoformat(line[:19]).replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                ts = None
        if ts is None:
            match = re.search(r"Date:\s*(\d{4}-\d{2}-\d{2}T[\d:.]+)", line)
            if match:
                try:
                    raw = match.group(1).split(".")[0]
                    ts = datetime.fromisoformat(raw).replace(tzinfo=timezone.utc).timestamp()
                except ValueError:
                    ts = None
        if ts is not None and ts >= since - 15.0:
            kept.append(line)
    return kept


def _collect_event_log_powershell(*, minutes: int) -> tuple[list[str], str]:
    ps = rf"""
$ErrorActionPreference = 'SilentlyContinue'
$start = (Get-Date).AddMinutes(-{minutes})
$out = New-Object System.Collections.Generic.List[string]
$patterns = 'python','sdrplay','sdrPlay','Soapy','sdrPlaySupport'
foreach ($id in 1000,1001,1002) {{
  Get-WinEvent -FilterHashtable @{{LogName='Application'; Id=$id; StartTime=$start}} -MaxEvents 30 |
    ForEach-Object {{
      $msg = ($_.Message -replace '\s+',' ').Trim()
      $hit = $false
      foreach ($p in $patterns) {{ if ($msg -match $p) {{ $hit = $true; break }} }}
      if ($hit) {{
        $snippet = if ($msg.Length -gt 300) {{ $msg.Substring(0,300) }} else {{ $msg }}
        [void]$out.Add($_.TimeCreated.ToString('o') + ' [Application] Id=' + $_.Id + ' ' + $snippet)
      }}
    }}
}}
if ($out.Count -lt 5) {{
  Get-WinEvent -FilterHashtable @{{LogName='Application'; Level=2; StartTime=$start}} -MaxEvents 20 |
    ForEach-Object {{
      $msg = ($_.Message -replace '\s+',' ').Trim()
      $hit = $false
      foreach ($p in $patterns) {{ if ($msg -match $p) {{ $hit = $true; break }} }}
      if ($hit) {{
        $snippet = if ($msg.Length -gt 300) {{ $msg.Substring(0,300) }} else {{ $msg }}
        [void]$out.Add($_.TimeCreated.ToString('o') + ' [Application] L=Error Id=' + $_.Id + ' ' + $snippet)
      }}
    }}
}}
$out | Select-Object -First 25
"""
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except Exception as exc:
        return [], f"event log powershell: {exc}"

    stderr = (res.stderr or "").strip()
    lines = [ln.strip() for ln in (res.stdout or "").splitlines() if ln.strip()]
    if lines:
        return lines, stderr
    if stderr:
        return [], stderr
    if res.returncode != 0:
        return [], f"event log powershell exit {res.returncode}"
    return [], ""


def _collect_event_log_wevtutil(*, minutes: int) -> list[str]:
    """Fallback sin FilterHashtable (algunas ediciones Windows)."""
    try:
        res = subprocess.run(
            [
                "wevtutil",
                "qe",
                "Application",
                "/q:*[System[(EventID=1000 or EventID=1001)]]",
                "/f:text",
                "/c:30",
                "/rd:true",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=45,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return []

    block: list[str] = []
    entries: list[str] = []
    for line in (res.stdout or "").splitlines():
        if line.strip() == "" and block:
            blob = " ".join(block)
            if _CRASH_KEYWORDS.search(blob):
                entries.append(blob[:320])
            block = []
            continue
        block.append(line.strip())
    if block:
        blob = " ".join(block)
        if _CRASH_KEYWORDS.search(blob):
            entries.append(blob[:320])
    return entries[:25]


def capture_post_segfault_evidence(
    *,
    since: float,
    dumps_dir: Path,
    poll_seconds: float = 20.0,
    event_log_minutes: int = 5,
    stage_dumps: bool = True,
) -> dict[str, str | list[str]]:
    """
    Tras un segfault en subproceso: minidump + Event Viewer + metadatos WER.
    """
    raw_dump = ""
    wer_artifacts: list[str] = []
    deadline = time.time() + max(poll_seconds, 0.0)
    while True:
        raw_dump = find_recent_minidump(
            since=since,
            dumps_dir=dumps_dir,
            poll_seconds=0,
        )
        wer_artifacts = find_wer_report_artifacts(since=since - 30.0)
        if raw_dump or wer_artifacts:
            break
        if time.time() >= deadline:
            break
        time.sleep(1.0)
    historical_wer = False
    if not raw_dump and not wer_artifacts:
        wer_artifacts = find_latest_wer_report_fallback(limit=2)
        historical_wer = bool(wer_artifacts)
    staged = ""
    if raw_dump and stage_dumps:
        staged = stage_minidump_for_report(raw_dump, dest_dir=dumps_dir) or raw_dump
    elif wer_artifacts and stage_dumps:
        staged = wer_artifacts[0]

    events, event_note = collect_event_log_after_crash(minutes=event_log_minutes, since=since)
    wer = wer_status(dumps_dir=dumps_dir)

    return {
        "minidump_path": staged or raw_dump,
        "minidump_source": raw_dump,
        "wer_report_artifacts": wer_artifacts,
        "wer_report_historical": historical_wer,
        "event_log_entries": events,
        "event_log_note": event_note,
        "wer_configured": bool(wer.get("configured")),
        "wer_dump_folder": str(wer.get("dump_folder") or ""),
        "wer_dump_count": int(wer.get("dump_count") or 0),
    }
