"""
xyz-sdr | core/sdrplay_wizard.py
Snapshot ligero para el wizard de hardware SDRplay (TUI Fase 4).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from core.driver_runtime import bundled_platform, bundled_soapy_dll_dir, drivers_root, resolve_bundled_sdrplay_plugin
from core.soapy_runtime import assess_sdrplay_soapy_module, bootstrap_soapy, find_sdrplay_soapy_module
from core.sdrplay_enumerate import has_sdrplay_in_devices, recover_sdrplay_enumeration, sdrplay_find_ok
from core.sdrplay_service import check_sdrplay_service_running


@dataclass
class SdrplayWizardSnapshot:
    service_running: bool
    plugin_status: str
    plugin_path: str | None
    find_ok: bool
    device_labels: list[str]
    drivers_root: str
    bundled_soapy: str
    stream_mode: str
    stream_format: str
    sample_rate_env: str
    preflight_ok: bool | None
    recover_hint: str


def collect_sdrplay_wizard_snapshot(
    *,
    attempt_recover: bool = False,
    preflight_ok: bool | None = None,
) -> SdrplayWizardSnapshot:
    """Estado actual para la página Hardware → Diagnóstico SDRplay."""
    recover_hint = ""
    if attempt_recover and not sdrplay_find_ok():
        found, msg, _status = recover_sdrplay_enumeration(restart_if_missing=True)
        recover_hint = msg
        if not found:
            recover_hint = f"Sin RSP tras recuperación: {msg}"

    status = bootstrap_soapy(force=True)
    labels: list[str] = []
    for dev in status.devices:
        if str(dev.get("driver", "")).lower() == "sdrplay":
            label = str(dev.get("label", dev.get("name", "sdrplay"))).strip()
            if label:
                labels.append(label)

    plugin = status.sdrplay_plugin_module
    plugin_status = status.sdrplay_plugin_status
    if plugin_status == "missing" or not plugin:
        bundled = resolve_bundled_sdrplay_plugin()
        if bundled is not None:
            plugin = str(bundled)
            plugin_status = assess_sdrplay_soapy_module(plugin)
    if not plugin:
        plugin = find_sdrplay_soapy_module(status.pothos_root)
        plugin_status = assess_sdrplay_soapy_module(plugin)
    soapy_dir = bundled_soapy_dll_dir()
    find_ok = has_sdrplay_in_devices(status.devices) or sdrplay_find_ok(status=status)

    if not find_ok and not recover_hint:
        recover_hint = "Prueba: Reiniciar API o Restart-Service SDRplayAPIService"

    return SdrplayWizardSnapshot(
        service_running=check_sdrplay_service_running(),
        plugin_status=plugin_status,
        plugin_path=plugin,
        find_ok=find_ok,
        device_labels=labels,
        drivers_root=str(drivers_root()),
        bundled_soapy=str(soapy_dir) if soapy_dir else "(no staged)",
        stream_mode=os.environ.get("XYZ_SDR_SDRPLAY_STREAM_MODE", "(auto)"),
        stream_format=os.environ.get("XYZ_SDR_SDRPLAY_STREAM_FORMAT", "(auto)"),
        sample_rate_env=os.environ.get("XYZ_SDR_SDRPLAY_STREAM_SAMPLE_RATE", ""),
        preflight_ok=preflight_ok,
        recover_hint=recover_hint,
    )


def format_wizard_lines(snapshot: SdrplayWizardSnapshot, *, cached_sdrplay: int = 0) -> list[str]:
    svc = "RUNNING" if snapshot.service_running else "STOPPED"
    find = "OK" if snapshot.find_ok else "FAIL"
    if snapshot.device_labels:
        enum = snapshot.device_labels[0]
        if len(snapshot.device_labels) > 1:
            enum += f" (+{len(snapshot.device_labels) - 1})"
    else:
        enum = "ningún RSP ahora"
    plugin = snapshot.plugin_status
    if snapshot.plugin_path:
        plugin = f"{plugin} ({os.path.basename(snapshot.plugin_path)})"
    preflight = "—"
    if snapshot.preflight_ok is True:
        preflight = "OK"
    elif snapshot.preflight_ok is False:
        preflight = "FAIL / SEGFAULT"
    lines = [
        f"API: {svc}  |  enumerate: {find}  |  RX test: {preflight}",
        f"Plugin: {plugin}",
        f"RSP vivo: {enum}",
    ]
    if cached_sdrplay > 0 and not snapshot.find_ok:
        lines.append(
            f"Selector: {cached_sdrplay} SDR en caché de arranque "
            "(el listado no se actualiza solo; pulsa Actualizar)"
        )
    lines.append(f"Stream: {snapshot.stream_mode} / {snapshot.stream_format}")
    if snapshot.recover_hint:
        lines.append(snapshot.recover_hint[:72])
    return lines
