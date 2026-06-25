"""
xyz-sdr | core/diagnose_sdrplay.py
Informe de diagnóstico SDRplay / Soapy (Fase 0 regresión).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from core.runtime_paths import project_root
from core.soapy_runtime import (
    _parse_sdrplay_find_stdout,
    assess_sdrplay_soapy_module,
    bootstrap_soapy,
    check_sdrplay_plugin,
    find_pothos_install,
    find_sdrplay_api_dll,
    find_sdrplay_soapy_module,
    soapy_plugin_search_dirs,
    user_soapy_plugin_dir,
    user_xyz_sdr_bin_dir,
    _soapy_util_executable,
)
from core.sdrplay_preflight import (
    per_path_timeout,
    resolve_preflight_timeout,
    run_preflight,
)
from core.sdrplay_repair import sdrplay_api_repair_recommendations, volk_warning_is_benign
from core.sdrplay_service import (
    check_sdrplay_service_running,
    ensure_sdrplay_service_running,
    is_native_crash_exit_code as _is_native_crash,
    restart_sdrplay_service,
    wait_for_sdrplay_service_running,
)


@dataclass
class DiagnoseReport:
    """Informe estructurado de diagnóstico SDRplay."""

    timestamp: str = ""
    pothos_root: str | None = None
    api_dll: str | None = None
    plugin_module: str | None = None
    plugin_status: str = "missing"
    plugin_search_dirs: list[str] = field(default_factory=list)
    soapy_plugin_path_env: str = ""
    user_plugin_dir: str = ""
    user_bin_dir: str = ""
    service_running: bool = False
    bootstrap_import_ok: bool = False
    bootstrap_devices: list[dict] = field(default_factory=list)
    find_stdout: str = ""
    find_ok: bool = False
    probe_stdout: str = ""
    probe_ok: bool = False
    probe_ok_degraded: bool = False
    probe_segfault: bool = False
    probe_skipped: bool = False
    stream_test_ok: bool = False
    stream_test_detail: str = ""
    stream_test_segfault: bool = False
    stream_test_last_step: str = ""
    stream_test_legacy_ok: bool = False
    stream_test_minimal_ok: bool = False
    stream_test_recommended_path: str = ""
    stream_test_timeout_s: float = 0.0
    service_restart_before_stream: str = ""
    service_restart_before_find: str = ""
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


def _file_info(path: str | None) -> str:
    if not path or not os.path.isfile(path):
        return "missing"
    try:
        stat = os.stat(path)
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        return f"{path} ({stat.st_size} bytes, mtime={mtime})"
    except OSError:
        return path or "missing"


def _probe_output_ok(text: str) -> bool:
    lowered = (text or "").lower()
    if "sdrplay_api_open()" in lowered or "sdrplay_api_fail" in lowered.replace(" ", ""):
        return False
    if "no available rsp devices" in lowered:
        return False
    compact = lowered.replace(" ", "")
    return "hardware=rsp" in compact


def _probe_status_label(report: DiagnoseReport) -> str:
    if report.probe_skipped:
        return "SKIPPED"
    if report.probe_ok:
        return "OK"
    if report.probe_ok_degraded:
        return "DEGRADED"
    if report.probe_segfault:
        return "SEGFAULT"
    return "FAIL"


def _run_stream_path_tests(stream_timeout: float | None = None) -> tuple[object, object]:
    """Ejecuta minimal y legacy; devuelve (minimal_result, legacy_result)."""
    per = per_path_timeout(resolve_preflight_timeout(stream_timeout))
    minimal = run_preflight("minimal", per_path_timeout_s=per)
    legacy = run_preflight("legacy", per_path_timeout_s=per)
    return minimal, legacy


def _restart_service_before_stream_test() -> tuple[bool, str]:
    """Reinicia API tras probe (segfault al cerrar puede dejar el servicio inestable)."""
    ok, msg = restart_sdrplay_service(stop_wait_s=10.0, start_wait_s=5.0)
    if not ok:
        ok, msg = ensure_sdrplay_service_running()
    if ok and wait_for_sdrplay_service_running(20.0):
        time.sleep(2.0)
        bootstrap_soapy(force=True)
        return True, msg
    return False, msg or "SDRplayAPIService no responde tras reinicio"


def _run_soapy_util(args: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess[str]:
    util = _soapy_util_executable()
    return subprocess.run(
        [util, *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        env=os.environ.copy(),
    )


def collect_diagnose_report(
    *,
    run_stream_test: bool = True,
    run_probe: bool = True,
    stream_timeout: float | None = None,
) -> DiagnoseReport:
    report = DiagnoseReport(timestamp=datetime.now().isoformat(timespec="seconds"))
    report.stream_test_timeout_s = resolve_preflight_timeout(stream_timeout)
    report.pothos_root = find_pothos_install()
    report.api_dll = find_sdrplay_api_dll()
    report.plugin_module = find_sdrplay_soapy_module(report.pothos_root)
    report.plugin_status = assess_sdrplay_soapy_module(report.plugin_module)
    report.plugin_search_dirs = soapy_plugin_search_dirs(report.pothos_root)
    report.user_plugin_dir = user_soapy_plugin_dir()
    report.user_bin_dir = user_xyz_sdr_bin_dir()
    report.service_running = check_sdrplay_service_running()

    status = bootstrap_soapy(force=True)
    report.soapy_plugin_path_env = os.environ.get("SOAPY_SDR_PLUGIN_PATH", "")
    report.bootstrap_import_ok = status.import_ok
    report.bootstrap_devices = [dict(d) for d in status.devices]

    if report.bootstrap_import_ok and not check_sdrplay_plugin():
        ok, msg = restart_sdrplay_service(stop_wait_s=10.0, start_wait_s=5.0)
        if not ok:
            ok, msg = ensure_sdrplay_service_running()
        if ok:
            time.sleep(2.0)
            bootstrap_soapy(force=True)
            report.service_restart_before_find = msg
            report.service_running = check_sdrplay_service_running()

    try:
        find_res = _run_soapy_util(["--find=driver=sdrplay"])
        report.find_stdout = (find_res.stdout or "") + (find_res.stderr or "")
        report.find_ok = _parse_sdrplay_find_stdout(find_res.stdout or "")
    except Exception as exc:
        report.find_stdout = str(exc)
        report.find_ok = False

    probe_ran = False
    if run_probe:
        probe_ran = True
        try:
            probe_res = _run_soapy_util(["--probe=driver=sdrplay"])
            report.probe_stdout = ((probe_res.stdout or "") + (probe_res.stderr or ""))[:4000]
            report.probe_segfault = _is_native_crash(probe_res.returncode)
            probe_identified = _probe_output_ok(report.probe_stdout)
            report.probe_ok = probe_res.returncode == 0 and probe_identified
            report.probe_ok_degraded = report.probe_segfault and probe_identified
        except Exception as exc:
            report.probe_stdout = str(exc)
            report.probe_ok = False
    else:
        report.probe_skipped = True

    if run_stream_test and report.bootstrap_import_ok:
        service_ready = report.service_running
        if probe_ran and (report.probe_segfault or report.probe_stdout.strip()):
            service_ready, restart_msg = _restart_service_before_stream_test()
            report.service_restart_before_stream = restart_msg
            report.service_running = check_sdrplay_service_running()

        if not service_ready or not report.service_running:
            report.stream_test_detail = (
                f"stream test skipped: SDRplayAPIService not ready "
                f"({report.service_restart_before_stream or 'not running'})"
            )
            report.stream_test_last_step = "service_not_ready"
        else:
            minimal_res, legacy_res = _run_stream_path_tests(stream_timeout)
            report.stream_test_legacy_ok = legacy_res.ok
            report.stream_test_minimal_ok = minimal_res.ok
            if minimal_res.ok:
                report.stream_test_recommended_path = "minimal"
                chosen = minimal_res
            elif legacy_res.ok:
                report.stream_test_recommended_path = "legacy"
                chosen = legacy_res
            else:
                report.stream_test_recommended_path = "none"
                chosen = minimal_res if minimal_res.segfault else legacy_res

            report.stream_test_ok = minimal_res.ok or legacy_res.ok
            report.stream_test_segfault = (
                legacy_res.segfault or minimal_res.segfault
            ) and not report.stream_test_ok
            report.stream_test_last_step = chosen.last_step
            detail_parts = [
                f"minimal: {'OK' if minimal_res.ok else ('SEGFAULT' if minimal_res.segfault else 'FAIL')} "
                f"step={minimal_res.last_step or '?'}",
                f"legacy: {'OK' if legacy_res.ok else ('SEGFAULT' if legacy_res.segfault else 'FAIL')} "
                f"step={legacy_res.last_step or '?'}",
                f"per_path_timeout_s: {per_path_timeout(report.stream_test_timeout_s):.0f}",
            ]
            if chosen.detail:
                detail_parts.append(chosen.detail[:800])
            report.stream_test_detail = "\n".join(detail_parts)

    report.service_running = check_sdrplay_service_running()

    _analyze_report(report)
    return report


def _analyze_report(report: DiagnoseReport) -> None:
    if report.plugin_status == "legacy":
        report.issues.append("Plugin Soapy sdrplay LEGACY detectado (incompatible con API v3.15+).")
        report.recommendations.append("Ejecuta: .\\setup\\install_soapy_sdrplay3.ps1")
    elif report.plugin_status == "missing":
        report.issues.append("No hay plugin Soapy sdrplay present.")
        report.recommendations.append("Ejecuta: .\\setup\\install_drivers.ps1 → opción 1")

    if not report.service_running:
        report.issues.append("SDRplayAPIService no está en ejecución.")
        report.recommendations.append(
            "PowerShell (admin): Start-Service SDRplayAPIService"
        )
        report.recommendations.append("Cierra SDRuno antes de iniciar/reiniciar el servicio.")

    find_lower = (report.find_stdout or "").lower()
    if not report.find_ok and "no available rsp" in find_lower:
        report.issues.append(
            "Soapy no encuentra RSP — SDRplayAPIService puede estar colgado aunque reporte Running."
        )
        report.recommendations.append(
            "Restart-Service SDRplayAPIService; Start-Sleep 10; .\\scripts\\diagnose_sdrplay.ps1 --no-probe"
        )

    if "sdrplay_api_open()" in find_lower and not report.service_running:
        report.issues.insert(
            0,
            "sdrplay_api_Open() falló porque SDRplayAPIService está detenido (no es fallo USB/plugin).",
        )

    pothos_root = report.pothos_root
    if pothos_root:
        mod_dir = os.path.join(pothos_root, "lib", "SoapySDR")
        for root, _dirs, files in os.walk(mod_dir) if os.path.isdir(mod_dir) else []:
            for name in files:
                if "sdrplay" in name.lower() and name.lower().endswith(".dll"):
                    full = os.path.join(root, name)
                    if assess_sdrplay_soapy_module(full) == "legacy":
                        report.issues.append(f"Pothos legacy module still present: {full}")
                        report.recommendations.append(
                            "Renombra o elimina el módulo legacy en Pothos; usa plugin en %LOCALAPPDATA%\\xyz-sdr\\"
                        )

    user_mod = os.path.join(report.user_plugin_dir, "sdrPlaySupport.dll")
    if os.path.isfile(user_mod) and report.plugin_status == "present":
        if report.soapy_plugin_path_env and report.user_plugin_dir not in report.soapy_plugin_path_env.split(os.pathsep)[0]:
            report.issues.append("SOAPY_SDR_PLUGIN_PATH no prioriza el plugin de usuario.")
            report.recommendations.append("Reinicia la app; bootstrap debe anteponer %LOCALAPPDATA%\\xyz-sdr\\SoapySDR\\modules0.8")

    if report.probe_ok_degraded:
        report.issues.append(
            "SoapySDRUtil --probe identificó el RSP1 pero terminó con segfault al cerrar "
            "(conocido en plugin sdrplay). La prueba definitiva es el stream test."
        )
        report.recommendations.append(
            "Si el stream test pasa, puedes usar xyz-sdr; si no, reinicia SDRplayAPIService y reintenta diagnose."
        )
    elif report.probe_segfault and not _probe_output_ok(report.probe_stdout):
        report.issues.append(
            "SoapySDRUtil --probe crasheó antes de identificar el dispositivo — plugin/API nativo inestable."
        )
        report.recommendations.extend(sdrplay_api_repair_recommendations(include_plugin=True))

    if report.stream_test_segfault:
        step = report.stream_test_last_step or "unknown"
        if step == "open":
            step_detail = (
                "setupStream/activateStream tras abrir el dispositivo "
                "(reinstalar API, no solo el plugin Soapy)"
            )
        else:
            step_detail = f"paso «{step}»"
        report.issues.append(
            f"Crash nativo en stream test ({step_detail}) — "
            "coincide con cierre abrupto de la TUI al pulsar INICIAR RX."
        )
        if report.find_ok and report.plugin_status == "present":
            report.issues.append(
                "Find OK + plugin present pero stream SEGFAULT: "
                "install_soapy_sdrplay3.ps1 no basta; reinstala SDRplay API v3.15 (sdrplay_api.dll / servicio)."
            )
        report.recommendations.extend(sdrplay_api_repair_recommendations())
        report.recommendations.append(
            "Si SDRuno tampoco abre el RSP1: otro puerto USB o cable; revisa var/log/xyz-sdr-*.log"
        )
    elif report.find_ok and not report.stream_test_ok:
        detail_l = (report.stream_test_detail or "").lower()
        if report.stream_test_last_step == "service_not_ready":
            report.issues.append(
                "Stream test omitido: SDRplayAPIService no quedó en ejecución tras el probe. "
                "Ejecuta Start-Service SDRplayAPIService y reintenta con --no-probe."
            )
            report.recommendations.append(
                "PowerShell (admin): Start-Service SDRplayAPIService; Start-Sleep 5; "
                ".\\scripts\\diagnose_sdrplay.ps1 --no-probe"
            )
        elif report.stream_test_last_step == "timeout":
            report.issues.append(
                "Stream test timeout — el API/plugin respondió demasiado lento. "
                "Cierra xyz-sdr/SDRuno, reinicia SDRplayAPIService o sube "
                "XYZ_SDR_PREFLIGHT_TIMEOUT (p. ej. 90)."
            )
            report.recommendations.append(
                "PowerShell: $env:XYZ_SDR_PREFLIGHT_TIMEOUT='90'; .\\scripts\\diagnose_sdrplay.ps1"
            )
        elif "servicenotresponding" in detail_l.replace("_", ""):
            report.issues.append(
                "Stream test falló: sdrplay_api_ServiceNotResponding — el servicio API quedó colgado "
                "tras probe/reinicio. Reinicia el servicio manualmente antes del stream test."
            )
            report.recommendations.append(
                "Restart-Service SDRplayAPIService; espera 10 s; "
                ".\\scripts\\diagnose_sdrplay.ps1 --no-probe"
            )
        else:
            report.issues.append(
                "Enumerate OK pero stream test falló — revisa permisos USB, servicio SDRplay o dispositivo en uso."
            )
            report.recommendations.append(
                "Cierra xyz-sdr y SDRuno antes de diagnose (el RSP solo admite un handle)."
            )

    combined_out = " ".join(
        filter(None, [report.find_stdout, report.probe_stdout, report.stream_test_detail])
    )
    if volk_warning_is_benign(combined_out) and not any(
        "volk" in issue.lower() for issue in report.issues
    ):
        report.recommendations.append(
            "Nota: aviso SoapyVOLK/volk_profile es solo rendimiento SIMD; no causa segfault SDRplay (puedes ignorarlo)."
        )


def format_diagnose_report(report: DiagnoseReport) -> str:
    probe_label = _probe_status_label(report)
    lines = [
        "=== xyz-sdr SDRplay diagnose ===",
        f"timestamp: {report.timestamp}",
        f"pothos_root: {report.pothos_root or 'missing'}",
        f"api_dll: {_file_info(report.api_dll)}",
        f"plugin_module: {_file_info(report.plugin_module)}",
        f"plugin_status: {report.plugin_status}",
            f"SDRplayAPIService running: {report.service_running}",
            f"service restart before find: {report.service_restart_before_find or '(none)'}",
            f"service restart before stream: {report.service_restart_before_stream or '(none)'}",
        f"SOAPY_SDR_PLUGIN_PATH: {report.soapy_plugin_path_env or '(empty)'}",
        f"user_plugin_dir: {report.user_plugin_dir}",
        f"user_bin_dir: {report.user_bin_dir}",
        "plugin_search_dirs:",
    ]
    for directory in report.plugin_search_dirs:
        lines.append(f"  - {directory}")
    lines.extend(
        [
            f"bootstrap import_ok: {report.bootstrap_import_ok}",
            f"bootstrap devices: {len(report.bootstrap_devices)}",
            f"SoapySDRUtil --find sdrplay: {'OK' if report.find_ok else 'FAIL'}",
            f"SoapySDRUtil --probe sdrplay: {probe_label}",
            f"stream test timeout total: {report.stream_test_timeout_s:.0f}s",
            f"Python stream test 500kHz: {'OK' if report.stream_test_ok else ('SEGFAULT' if report.stream_test_segfault else 'FAIL')}",
            f"stream test legacy: {'OK' if report.stream_test_legacy_ok else 'FAIL'}",
            f"stream test minimal: {'OK' if report.stream_test_minimal_ok else 'FAIL'}",
            f"stream test recommended path: {report.stream_test_recommended_path or '(none)'}",
            f"stream test last step: {report.stream_test_last_step or '(none)'}",
        ]
    )
    if report.find_stdout.strip():
        lines.append("--- find stdout (truncated) ---")
        lines.append(report.find_stdout.strip()[:1500])
    if report.probe_stdout.strip():
        lines.append("--- probe stdout (truncated) ---")
        lines.append(report.probe_stdout.strip()[:1500])
    if report.stream_test_detail.strip():
        lines.append("--- stream test (truncated) ---")
        lines.append(report.stream_test_detail.strip()[:1500])
    if report.issues:
        lines.append("--- ISSUES ---")
        lines.extend(f"  ! {issue}" for issue in report.issues)
    if report.recommendations:
        lines.append("--- RECOMMENDATIONS ---")
        lines.extend(f"  → {rec}" for rec in report.recommendations)
    return "\n".join(lines)


def write_diagnose_report(report: DiagnoseReport | None = None) -> Path:
    if report is None:
        report = collect_diagnose_report()
    text = format_diagnose_report(report)
    log_dir = project_root() / "var" / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    out_path = log_dir / f"diagnose-sdrplay-{datetime.now():%Y%m%d-%H%M%S}.txt"
    out_path.write_text(text, encoding="utf-8")
    return out_path


def _parse_stream_timeout_argv(argv: list[str]) -> float | None:
    for index, arg in enumerate(argv):
        if arg.startswith("--stream-timeout="):
            try:
                return float(arg.split("=", 1)[1])
            except ValueError:
                return None
        if arg == "--stream-timeout" and index + 1 < len(argv):
            try:
                return float(argv[index + 1])
            except ValueError:
                return None
    return None


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    no_stream = "--no-stream" in argv
    no_probe = "--no-probe" in argv
    stream_timeout = _parse_stream_timeout_argv(argv)
    report = collect_diagnose_report(
        run_stream_test=not no_stream,
        run_probe=not no_probe,
        stream_timeout=stream_timeout,
    )
    text = format_diagnose_report(report)
    print(text)
    out_path = write_diagnose_report(report)
    print(f"\n[OK] Informe guardado: {out_path}")
    return 1 if report.issues else 0


if __name__ == "__main__":
    sys.exit(main())
