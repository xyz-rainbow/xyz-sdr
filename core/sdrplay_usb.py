"""
xyz-sdr | core/sdrplay_usb.py
Estado USB del RSP SDRplay en Windows (VID_1DF7).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass

SDRPLAY_USB_VID = "1DF7"
CM_PROB_FAILED_INSTALL = 28

_USB_PROBLEM_LABELS = {
    CM_PROB_FAILED_INSTALL: "driver_not_installed",
}


@dataclass(frozen=True)
class SdrplayUsbStatus:
    present: bool = False
    ok: bool = True
    problem_code: int | None = None
    problem_label: str | None = None
    instance_id: str | None = None


def _parse_pnp_rows(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def _normalize_problem_code(raw: object) -> int | None:
    if raw in (None, "", 0):
        return None
    if isinstance(raw, int):
        return raw if raw != 0 else None
    text = str(raw).strip()
    if not text:
        return None
    if text.isdigit():
        value = int(text)
        return value if value != 0 else None
    lowered = text.lower()
    if "failed_install" in lowered:
        return CM_PROB_FAILED_INSTALL
    return None


def _row_problem_code(row: dict) -> int | None:
    for key in ("ProblemCode", "ConfigManagerErrorCode", "problem_code"):
        code = _normalize_problem_code(row.get(key))
        if code is not None:
            return code
    return None


def probe_sdrplay_usb(*, timeout: float = 8.0) -> SdrplayUsbStatus:
    """Detecta RSP conectado por USB y errores de driver en Windows."""
    if os.name != "nt":
        return SdrplayUsbStatus()

    # Sin -PresentOnly: dispositivos con código 28 a veces no aparecen como "present".
    script = (
        "$rows = Get-PnpDevice | "
        f"Where-Object {{ $_.InstanceId -match 'VID_{SDRPLAY_USB_VID}' }} | "
        "ForEach-Object { "
        "[PSCustomObject]@{ "
        "Status = [string]$_.Status; "
        "ProblemCode = if ($null -eq $_.ConfigManagerErrorCode) { 0 } "
        "else { [int]$_.ConfigManagerErrorCode }; "
        "InstanceId = [string]$_.InstanceId "
        "} }; "
        "$rows | ConvertTo-Json -Compress"
    )
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        if res.returncode != 0 or not (res.stdout or "").strip():
            return SdrplayUsbStatus()
        payload = json.loads(res.stdout.strip())
    except Exception:
        return SdrplayUsbStatus()

    rows = _parse_pnp_rows(payload)
    if not rows:
        return SdrplayUsbStatus()

    problem_row = next((row for row in rows if _row_problem_code(row) is not None), rows[0])
    status = str(problem_row.get("Status") or "").strip()
    problem_code = _row_problem_code(problem_row)
    ok = status.upper() == "OK" and problem_code is None
    label = _USB_PROBLEM_LABELS.get(problem_code) if problem_code else None
    return SdrplayUsbStatus(
        present=True,
        ok=ok,
        problem_code=problem_code,
        problem_label=label,
        instance_id=str(problem_row.get("InstanceId") or "") or None,
    )


def probe_sdrplay_usb_with_retry(*, attempts: int = 3, delay_s: float = 0.6) -> SdrplayUsbStatus:
    """Reintenta la sonda USB (el enumerador PnP puede tardar tras reiniciar servicios)."""
    last = SdrplayUsbStatus()
    tries = max(1, attempts)
    for index in range(tries):
        last = probe_sdrplay_usb()
        if last.present:
            return last
        if index + 1 < tries:
            time.sleep(max(delay_s, 0.0))
    return last


def rescan_sdrplay_usb_devices(*, timeout: float = 45.0) -> bool:
    """Fuerza reescaneo PnP tras reinstalar la API (útil con driver USB código 28)."""
    if os.name != "nt":
        return False
    try:
        res = subprocess.run(
            ["pnputil", "/scan-devices"],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        return res.returncode == 0
    except Exception:
        return False
