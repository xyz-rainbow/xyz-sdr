"""
xyz-sdr | core/sdrplay_install_guard.py
Libera SDRplay API / Soapy antes de reinstalar drivers (evita DLL bloqueadas).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Callable

_BLOCKING_PROCESS_NAMES = frozenset(
    {
        "python.exe",
        "pythonw.exe",
        "python3.exe",
        "sdruno.exe",
        "soapysdrutil.exe",
    }
)

# Solo la app en ejecución carga sdrplay_api.dll de forma persistente.
_PYTHON_KILL_MARKERS = (
    "main.py",
)

# Nunca matar el instalador ni sus subcomandos (evita suicidio del setup).
_PYTHON_PROTECTED_MARKERS = (
    "install_drivers",
    "install_sdrplay_api",
    "setup.install_drivers",
    "setup.install_sdrplay_api",
    "check_env",
    "pytest",
)


@dataclass(frozen=True)
class BlockingProcess:
    pid: int
    name: str
    command_line: str

    @property
    def summary(self) -> str:
        cmd = (self.command_line or self.name).strip()
        if len(cmd) > 96:
            cmd = cmd[:93] + "..."
        return f"{self.name} (pid={self.pid}) {cmd}"


def _parse_process_rows(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def _normalize_cmdline(cmd: str) -> str:
    return (cmd or "").lower().replace("\\", "/")


def _python_is_installer(cmd: str) -> bool:
    lowered = _normalize_cmdline(cmd)
    return any(marker in lowered for marker in _PYTHON_PROTECTED_MARKERS)


def _python_blocks_api_install(cmd: str) -> bool:
    """True solo para procesos Python que cargan el runtime SDR (p. ej. main.py)."""
    lowered = _normalize_cmdline(cmd)
    if _python_is_installer(lowered):
        return False
    return any(marker in lowered for marker in _PYTHON_KILL_MARKERS)


def _collect_protected_pids(root_pid: int | None = None) -> set[int]:
    """PID del instalador, ancestros y descendientes — nunca deben recibir taskkill."""
    if os.name != "nt":
        return {root_pid or os.getpid()}

    root = int(root_pid if root_pid is not None else os.getpid())
    script = (
        f"$root = {root}; "
        "$all = Get-CimInstance Win32_Process | "
        "Select-Object ProcessId, ParentProcessId; "
        "$byId = @{}; foreach ($p in $all) { $byId[[int]$p.ProcessId] = [int]$p.ParentProcessId }; "
        "$protected = [System.Collections.Generic.HashSet[int]]::new(); "
        "$walk = $root; while ($walk -gt 0) { "
        "[void]$protected.Add($walk); "
        "if (-not $byId.ContainsKey($walk)) { break }; $walk = $byId[$walk] }; "
        "$stack = [System.Collections.Generic.Stack[int]]::new(); $stack.Push($root); "
        "while ($stack.Count -gt 0) { "
        "$pid = $stack.Pop(); "
        "foreach ($child in ($all | Where-Object { [int]$_.ParentProcessId -eq $pid })) { "
        "$cid = [int]$child.ProcessId; "
        "if (-not $protected.Contains($cid)) { [void]$protected.Add($cid); $stack.Push($cid) } } }; "
        "$protected | ConvertTo-Json -Compress"
    )
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=12.0,
        )
        if res.returncode != 0 or not (res.stdout or "").strip():
            return {root}
        payload = json.loads(res.stdout.strip())
        if isinstance(payload, list):
            return {int(x) for x in payload if int(x) > 0}
        if isinstance(payload, (int, float)):
            return {int(payload)}
    except Exception:
        pass
    return {root}


def list_blocking_processes(*, skip_pid: int | None = None) -> list[BlockingProcess]:
    """Procesos externos que bloquean la reinstalación de SDRplay API."""
    if os.name != "nt":
        return []

    protected = _collect_protected_pids(skip_pid)

    script = (
        "Get-CimInstance Win32_Process | "
        f"Where-Object {{ $_.Name -in @({','.join(repr(n) for n in sorted(_BLOCKING_PROCESS_NAMES))}) }} | "
        "Select-Object ProcessId, Name, CommandLine | ConvertTo-Json -Compress"
    )
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=12.0,
        )
        if res.returncode != 0 or not (res.stdout or "").strip():
            return []
        payload = json.loads(res.stdout.strip())
    except Exception:
        return []

    found: list[BlockingProcess] = []
    for row in _parse_process_rows(payload):
        try:
            pid = int(row.get("ProcessId") or 0)
        except (TypeError, ValueError):
            continue
        if pid <= 0 or pid in protected:
            continue
        name = str(row.get("Name") or "").strip()
        if name.lower() not in _BLOCKING_PROCESS_NAMES:
            continue
        cmd = str(row.get("CommandLine") or "")
        lowered_name = name.lower()
        if lowered_name in ("sdruno.exe", "soapysdrutil.exe"):
            found.append(BlockingProcess(pid=pid, name=name, command_line=cmd))
            continue
        if lowered_name.endswith(".exe") and _python_blocks_api_install(cmd):
            found.append(BlockingProcess(pid=pid, name=name, command_line=cmd))
    return found


def _terminate_process(pid: int, *, tree: bool = False) -> bool:
    if os.name != "nt":
        return False
    args = ["taskkill", "/PID", str(pid), "/F"]
    if tree:
        args.append("/T")
    try:
        res = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=15.0,
        )
        return res.returncode == 0
    except Exception:
        return False


def reset_soapy_bootstrap() -> None:
    """Limpia caché Soapy en este intérprete (no descarga DLL nativas en Windows)."""
    import gc
    import sys

    from core.soapy_runtime import clear_soapy_bootstrap_cache

    clear_soapy_bootstrap_cache()
    for key in list(sys.modules):
        if key == "SoapySDR" or key.startswith("SoapySDR."):
            del sys.modules[key]
    gc.collect()


def prepare_for_sdrplay_api_install(
    say: Callable[[str], None] | None = None,
    *,
    lang: str = "es",
) -> tuple[bool, str]:
    """
    Detiene servicio, cierra procesos que bloquean la API y limpia bootstrap local.

    Debe llamarse antes del instalador oficial SDRplay API.
    """
    from core.sdrplay_service import stop_sdrplay_service
    from setup.install_i18n import t

    _say = say or (lambda _m: None)

    blockers = list_blocking_processes(skip_pid=os.getpid())
    if blockers:
        _say(f"  {t(lang, 'sdrplay_guard_closing_apps')}")
        for proc in blockers:
            _say(f"  [>>] {t(lang, 'sdrplay_guard_stop').format(proc.summary)}")
            use_tree = proc.name.lower() in ("sdruno.exe", "soapysdrutil.exe")
            if not _terminate_process(proc.pid, tree=use_tree):
                _say(f"  [!!] {t(lang, 'sdrplay_guard_stop_failed').format(proc.pid)}")
                return False, t(lang, "sdrplay_guard_blockers_remain")
        time.sleep(1.5)
        blockers = list_blocking_processes(skip_pid=os.getpid())
        if blockers:
            return False, t(lang, "sdrplay_guard_blockers_remain")

    _say(f"  {t(lang, 'sdrplay_guard_stopping_service')}")
    ok_stop, stop_msg = stop_sdrplay_service(wait_s=8.0)
    if not ok_stop:
        _say(f"  [!!] {stop_msg}")
    else:
        _say(f"  [OK] {stop_msg}")

    reset_soapy_bootstrap()
    time.sleep(1.0)
    return True, t(lang, "sdrplay_guard_ready")


def finalize_after_sdrplay_api_install(
    say: Callable[[str], None] | None = None,
    *,
    lang: str = "es",
) -> tuple[bool, str]:
    """Reinicia servicio tras instalar API y limpia caché Soapy local."""
    from core.sdrplay_service import restart_sdrplay_service
    from setup.install_i18n import t

    _say = say or (lambda _m: None)
    reset_soapy_bootstrap()
    ok, msg = restart_sdrplay_service(stop_wait_s=3.0, start_wait_s=8.0)
    if ok:
        _say(f"  [OK] {msg}")
    else:
        _say(f"  [>>] {msg}")
    time.sleep(1.5)
    return ok, msg if ok else t(lang, "sdrplay_guard_service_restart_failed")
