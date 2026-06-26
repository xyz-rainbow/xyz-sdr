"""
xyz-sdr | setup/sdrplay_repair.py
Reparación integral: API SDRplay + servicio + plugin Soapy + enumeración.
"""

from __future__ import annotations

import time
from typing import Callable

from core.sdrplay_enumerate import describe_sdrplay_enumeration_failure, recover_sdrplay_enumeration
from core.sdrplay_usb import (
    CM_PROB_FAILED_INSTALL,
    probe_sdrplay_usb_with_retry,
    rescan_sdrplay_usb_devices,
)
from core.soapy_runtime import (
    bootstrap_soapy,
    check_sdrplay_api,
    check_sdrplay_plugin,
    find_pothos_install,
    is_sdrplay_api_fault,
    is_sdrplay_soapy_module_ok,
    sync_sdrplay_api_dll_to_pothos,
)
from setup.env_state import probe_environment
from setup.install_log import log_line


def _needs_api_reinstall(*, usb_issue: bool, api_ok: bool, api_fault: bool) -> bool:
    if not api_ok:
        return True
    if usb_issue:
        return True
    if api_fault:
        return True
    return False


def repair_sdrplay_driver_stack(
    ctx,
    *,
    run_api_installer: Callable[[], bool],
    install_soapy_plugin: Callable[[], bool],
    log: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """
    Secuencia completa de reparación SDRplay para el wizard/instalador.

    Returns:
        (rsp_enumerated, summary_message)
    """
    say = ctx.say

    usb = probe_sdrplay_usb_with_retry()
    state = probe_environment(bootstrap_soapy=False, inprocess_soapy=False)
    usb_issue = usb.present and not usb.ok
    api_fault = is_sdrplay_api_fault() if state.sdrplay_ok and is_sdrplay_soapy_module_ok() else False

    if usb_issue:
        if usb.problem_code == CM_PROB_FAILED_INSTALL:
            say("  [!!] Driver USB del RSP sin instalar (código 28) — reinstalando API SDRplay…")
        else:
            say(f"  [!!] RSP USB con error del sistema (código {usb.problem_code}) — reinstalando API…")
        log_line(f"sdrplay.repair usb_issue code={usb.problem_code}")
    elif api_fault:
        say("  [!!] SDRplay API instalada pero no responde — reinstalando API…")
        log_line("sdrplay.repair api_fault detected")

    if _needs_api_reinstall(usb_issue=usb_issue, api_ok=state.sdrplay_ok, api_fault=api_fault):
        say("  [>>] Instalando/reparando SDRplay API v3.15…")
        if not run_api_installer():
            return False, "No se pudo instalar la API SDRplay"
        time.sleep(2.0)
        say("  [>>] Reescaneando dispositivos USB…")
        if rescan_sdrplay_usb_devices():
            say("  [OK] Escaneo PnP completado")
            log_line("sdrplay.repair pnputil scan ok")
        else:
            say("  [>>] pnputil /scan-devices no disponible — desenchufa y vuelve a conectar el RSP")
        time.sleep(2.0)
        usb = probe_sdrplay_usb_with_retry(attempts=4, delay_s=1.0)
        state = probe_environment(bootstrap_soapy=False, inprocess_soapy=False)
        if not state.sdrplay_ok:
            return False, "API SDRplay no detectada tras el instalador"
        if usb.present and not usb.ok:
            say(
                "  [!!] Tras reinstalar la API el RSP sigue con error USB — "
                "desenchufa el RSP 10 s, vuelve a conectar y ejecuta reparar de nuevo"
            )

    from core.sdrplay_service import restart_sdrplay_service, stop_sdrplay_service

    say("  [>>] Reiniciando SDRplay API / servicio (limpieza)…")
    ok_stop, stop_msg = stop_sdrplay_service(wait_s=10.0)
    if ok_stop:
        say(f"  [OK] {stop_msg}")
    else:
        say(f"  [>>] {stop_msg}")
    time.sleep(1.0)
    ok_restart, restart_msg = restart_sdrplay_service(stop_wait_s=3.0, start_wait_s=12.0)
    say(f"  [{'OK' if ok_restart else '!!'}] {restart_msg}")
    if log:
        log(f"sdrplay.repair service_restart ok={ok_restart} {restart_msg!r}")
    time.sleep(2.0)

    api_dll = sync_sdrplay_api_dll_to_pothos(find_pothos_install())
    if api_dll:
        say("  [OK] sdrplay_api.dll sincronizada al runtime Soapy")
        log_line("sdrplay.repair api_dll synced")
    bootstrap_soapy(force=True)

    say("  [>>] Comprobando plugin Soapy SDRplay…")
    plugin_ok = install_soapy_plugin()
    if not plugin_ok:
        say("  [!!] No se pudo instalar/verificar el plugin SoapySDRPlay3")
        log_line("sdrplay.repair soapy_plugin_failed")
        if is_sdrplay_api_fault():
            detail = describe_sdrplay_enumeration_failure()
            say(f"  [!!] {detail}")
            return False, detail

    say("  [>>] Enumerando RSP…")
    found, msg, _status = recover_sdrplay_enumeration(restart_if_missing=True, log=log)
    say(f"  [{'OK' if found else '!!'}] {msg}")
    if found:
        return True, msg

    detail = describe_sdrplay_enumeration_failure()
    if detail != msg:
        say(f"  [!!] {detail}")
    return False, detail
