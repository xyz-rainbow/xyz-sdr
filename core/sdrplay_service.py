"""
xyz-sdr | core/sdrplay_service.py
Control del servicio Windows SDRplay API (reinicio tras crash nativo).
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Callable

logger = logging.getLogger(__name__)

SDRPLAY_SERVICE_NAMES = ("SDRplayAPIService", "sdrplay-api")

# STATUS_ACCESS_VIOLATION y otros códigos de salida Windows por crash nativo.
NATIVE_CRASH_EXIT_CODES = frozenset({3221225477, -1073741819, 3221225725, -1073741571})

# Marcadores de sesión anterior que indican reinicio recomendado del servicio.
_CRASH_MARKER_KINDS = frozenset(
    {
        "abnormal",
        "native_crash",
        "startup_error",
    }
)


def is_native_crash_exit_code(code: int | None) -> bool:
    return code in NATIVE_CRASH_EXIT_CODES


def resolve_sdrplay_service_name() -> str | None:
    """Nombre del servicio SDRplay si está registrado."""
    if os.name != "nt":
        return None
    for service_name in SDRPLAY_SERVICE_NAMES:
        try:
            res = subprocess.run(
                ["sc", "query", service_name],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if res.returncode == 0:
                return service_name
        except Exception:
            continue
    return None


def check_sdrplay_service_running() -> bool:
    """True si el servicio SDRplay API está en ejecución."""
    if os.name != "nt":
        return True
    service_name = resolve_sdrplay_service_name()
    if not service_name:
        return False
    try:
        res = subprocess.run(
            ["sc", "query", service_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return res.returncode == 0 and "RUNNING" in (res.stdout or "")
    except Exception:
        return False


def wait_for_sdrplay_service_running(timeout_s: float = 20.0) -> bool:
    """Espera hasta que el servicio reporte RUNNING (o timeout)."""
    deadline = time.monotonic() + max(timeout_s, 0.0)
    while time.monotonic() < deadline:
        if check_sdrplay_service_running():
            return True
        time.sleep(0.5)
    return False


def ensure_sdrplay_service_running(
    *,
    start_wait_s: float = 5.0,
) -> tuple[bool, str]:
    """Inicia el servicio si está parado; no hace stop."""
    if os.name != "nt":
        return True, "N/A (no Windows)"

    if check_sdrplay_service_running():
        return True, "Servicio SDRplay API ya en ejecución"

    service_name = resolve_sdrplay_service_name()
    if not service_name:
        return False, "Servicio SDRplay API no encontrado"

    try:
        start = subprocess.run(
            ["sc", "start", service_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        start_out = ((start.stdout or "") + (start.stderr or "")).strip()
        if start.returncode != 0 and "1056" not in start_out:
            return False, f"No se pudo iniciar {service_name}: {start_out or start.returncode}"

        if wait_for_sdrplay_service_running(start_wait_s + 15.0):
            return True, f"Servicio {service_name} iniciado"
        return False, f"{service_name} no reporta RUNNING tras sc start"
    except subprocess.TimeoutExpired:
        return False, f"Timeout iniciando {service_name}"
    except Exception as exc:
        return False, f"Error iniciando {service_name}: {exc}"


def restart_sdrplay_service(
    *,
    stop_wait_s: float = 8.0,
    start_wait_s: float = 5.0,
) -> tuple[bool, str]:
    """
    Reinicia SDRplayAPIService (Windows).

    Returns:
        (ok, message) — ok False si no hay servicio o falla sc/powershell.
    """
    if os.name != "nt":
        return False, "Reinicio de servicio SDRplay solo en Windows"

    service_name = resolve_sdrplay_service_name()
    if not service_name:
        return False, "Servicio SDRplay API no encontrado"

    try:
        stop = subprocess.run(
            ["sc", "stop", service_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if stop.returncode != 0 and "1062" not in (stop.stderr or "") + (stop.stdout or ""):
            # 1062 = servicio no iniciado
            logger.debug("sc stop %s: %s %s", service_name, stop.stdout, stop.stderr)

        deadline = time.monotonic() + stop_wait_s
        while time.monotonic() < deadline:
            if not check_sdrplay_service_running():
                break
            time.sleep(0.4)

        start = subprocess.run(
            ["sc", "start", service_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        start_out = ((start.stdout or "") + (start.stderr or "")).strip()
        if start.returncode != 0:
            # 1056 = ya en ejecución (p. ej. tras instalador SDRplay)
            if "1056" in start_out and check_sdrplay_service_running():
                return True, f"Servicio {service_name} en ejecución"
            return False, f"No se pudo iniciar {service_name}: {start_out or start.returncode}"

        if wait_for_sdrplay_service_running(start_wait_s + 15.0):
            time.sleep(1.0)
            return True, f"Servicio {service_name} reiniciado"
        return False, f"{service_name} iniciado pero no reporta RUNNING"
    except subprocess.TimeoutExpired:
        return False, f"Timeout reiniciando {service_name}"
    except Exception as exc:
        return False, f"Error reiniciando {service_name}: {exc}"


def previous_session_needs_service_restart(marker: dict | None) -> bool:
    """True si la sesión anterior terminó mal y conviene reiniciar el servicio."""
    if not marker:
        return False
    kind = str(marker.get("kind", "")).strip()
    if kind in _CRASH_MARKER_KINDS:
        return True
    exit_code = marker.get("exit_code")
    if isinstance(exit_code, int) and is_native_crash_exit_code(exit_code):
        return True
    if isinstance(exit_code, str) and exit_code.lstrip("-").isdigit():
        return is_native_crash_exit_code(int(exit_code))
    return False


def maybe_restart_sdrplay_service_after_crash(
    previous_marker: dict | None,
    *,
    log: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """
    Reinicia el servicio si la sesión anterior fue un crash (p. ej. segfault Soapy).

    Returns:
        (restarted, message)
    """
    if os.name != "nt":
        return False, ""
    if not previous_session_needs_service_restart(previous_marker):
        return False, ""

    kind = (previous_marker or {}).get("kind", "?")
    if log:
        log(f"sdrplay_service restart after previous session kind={kind!r}")

    ok, message = restart_sdrplay_service()
    if log:
        log(f"sdrplay_service restart ok={ok} msg={message!r}")
    if ok:
        logger.info(message)
    else:
        logger.warning("Reinicio SDRplayAPIService falló: %s", message)
    return ok, message
