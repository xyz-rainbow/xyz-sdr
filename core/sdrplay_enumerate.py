"""
xyz-sdr | core/sdrplay_enumerate.py
Recuperación de enumeración SDRplay (servicio API colgado / RSP invisible).
"""

from __future__ import annotations

import time
from typing import Callable

from core.soapy_runtime import (
    SoapyStatus,
    bootstrap_soapy,
    check_sdrplay_api,
    check_sdrplay_plugin,
)


def _driver_name(dev: dict) -> str:
    return str(dev.get("driver", "")).strip().lower()


def has_sdrplay_in_devices(devices: list[dict]) -> bool:
    return any(_driver_name(dev) == "sdrplay" for dev in devices)


def sdrplay_find_ok(*, status: SoapyStatus | None = None) -> bool:
    """True si enumerate o SoapySDRUtil --find ven el RSP."""
    if status is None:
        status = bootstrap_soapy(force=True)
    if has_sdrplay_in_devices(status.devices):
        return True
    return check_sdrplay_plugin()


_QUICK_RETRY_DELAYS = (0.5, 1.0, 1.5)


def _quick_enumerate_retries(status: SoapyStatus) -> SoapyStatus:
    """Reintentos ligeros antes de reiniciar SDRplayAPIService."""
    for delay in _QUICK_RETRY_DELAYS:
        if sdrplay_find_ok(status=status):
            return status
        time.sleep(delay)
        status = bootstrap_soapy(force=True)
    return status


def recover_sdrplay_enumeration(
    *,
    restart_if_missing: bool = True,
    log: Callable[[str], None] | None = None,
) -> tuple[bool, str, SoapyStatus]:
    """
    Fuerza bootstrap y, si hace falta, reinicia SDRplayAPIService para que el RSP aparezca.

    Returns:
        (found, message, latest_bootstrap_status)
    """
    status = bootstrap_soapy(force=True)
    if sdrplay_find_ok(status=status):
        return True, "SDRplay enumerado", status

    status = _quick_enumerate_retries(status)
    if sdrplay_find_ok(status=status):
        return True, "SDRplay visible tras reintento", status

    if not restart_if_missing:
        return False, "SDRplay no visible en enumerate/find", status

    if not check_sdrplay_api():
        return False, "SDRplay API no instalada (sdrplay_api.dll)", status

    from core.sdrplay_service import (
        check_sdrplay_service_running,
        ensure_sdrplay_service_running,
        restart_sdrplay_service,
    )

    if not check_sdrplay_service_running():
        ok, msg = ensure_sdrplay_service_running()
        if log:
            log(f"sdrplay.enumerate ensure_service ok={ok} {msg!r}")
        if ok:
            time.sleep(2.0)
            status = bootstrap_soapy(force=True)
            if sdrplay_find_ok(status=status):
                return True, f"SDRplay visible tras iniciar servicio ({msg})", status

    ok, msg = restart_sdrplay_service(stop_wait_s=5.0, start_wait_s=5.0)
    if log:
        log(f"sdrplay.enumerate restart ok={ok} {msg!r}")
    if not ok:
        return False, msg or "No se pudo reiniciar SDRplayAPIService", status

    time.sleep(2.0)
    status = bootstrap_soapy(force=True)
    if sdrplay_find_ok(status=status):
        return True, f"SDRplay visible tras reinicio de servicio ({msg})", status
    return False, "SDRplay sigue sin enumerar tras reiniciar SDRplayAPIService", status
