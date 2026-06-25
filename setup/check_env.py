#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verifica que todos los componentes necesarios estén instalados correctamente."""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime_paths import configure_pycache_prefix

configure_pycache_prefix(ROOT)


def ok(msg: str) -> None:
    print(f"  \033[92m[OK]\033[0m {msg}")


def warn(msg: str) -> None:
    print(f"  \033[93m[!!]\033[0m {msg}")


def fail(msg: str) -> None:
    print(f"  \033[91m[XX]\033[0m {msg}")


def step(msg: str) -> None:
    print(f"\n\033[96m[>>] {msg}\033[0m")


def run_check(*, verbose: bool = True, lang: str = "es") -> int:
    from core.soapy_runtime import (
        _soapy_pip_supported,
        bootstrap_soapy,
        find_pothos_install,
        format_hardware_help,
        is_python_64bit,
    )
    from core.python_runtime import _query_python_version, is_version_soapy_compatible, project_venv_python
    from setup.env_state import probe_environment
    from setup.windows_installers import refresh_windows_environment

    refresh_windows_environment()

    if not verbose:
        state = probe_environment(bootstrap_soapy=True)
        from setup.install_guidance import format_action
        from setup.install_i18n import t as tr

        _, _, reason = format_action(state, lang)
        print(f"\n{tr(lang, 'status_summary')}: {state.readiness_level()}")
        print(f"  {tr(lang, 'next_step_label')}: {reason}")
        if state.env_ready:
            print(f"\n  [OK] {tr(lang, 'check_short_ok')}")
            if not state.has_devices:
                print(f"  [!!] {tr(lang, 'status_row_no_device')}")
        else:
            print(f"\n  [XX] {tr(lang, 'check_short_fail')}")
            for blocker in state.install_blockers:
                print(f"    - {blocker}")
        print(f"\n  {tr(lang, 'check_short_hint')}\n")
        return 0 if state.env_ready else 1

    errors: list[str] = []
    venv_py = project_venv_python()
    if venv_py:
        checked = _query_python_version(str(venv_py))
        v = checked if checked else sys.version_info[:3]
        python_label = f"{venv_py} ({v[0]}.{v[1]}.{v[2]})"
    else:
        v = sys.version_info[:3]
        python_label = f"{v[0]}.{v[1]}.{v[2]}"

    step("Python")
    if is_version_soapy_compatible((v[0], v[1])):
        ok(f"Python {python_label}")
    else:
        fail(f"Python incompatible con SoapySDR. Tienes: {v[0]}.{v[1]}.{v[2]}")
        errors.append("python_version")

    if is_python_64bit():
        ok("Arquitectura: 64-bit (amd64)")
    else:
        fail("Se requiere Python 64-bit para PothosSDR/SoapySDR.")
        errors.append("python_bitness")

    if v[0] == 3 and v[1] >= 13:
        warn(
            f"Python {v[0]}.{v[1]}: no hay wheel SoapySDR en pip. "
            "Usa el .venv del proyecto (install_drivers → [1] Reparar)."
        )
    elif v[1] == 9:
        ok("Versión compatible con bindings Pothos 3.9")
    elif not _soapy_pip_supported():
        warn(f"Python {v[0]}.{v[1]} puede no tener soporte SoapySDR en pip.")
    else:
        ok("Versión compatible con pip SoapySDR o bindings Pothos 3.9")

    step("Entorno .venv")
    if venv_py:
        ok(f".venv detectado: {venv_py}")
        if os.path.normcase(str(venv_py)) != os.path.normcase(sys.executable):
            warn(f"Ejecutando check con {sys.executable}; el proyecto usa {venv_py}")
            warn("Preferido: .\\scripts\\run.ps1 --check")
    else:
        fail(".venv no encontrado. install_drivers → [1] Reparar")
        errors.append("venv")

    state = probe_environment(bootstrap_soapy=bool(venv_py))

    step("PothosSDR")
    pothos = find_pothos_install()
    if pothos:
        ok(f"Instalación detectada: {pothos}")
        if state.path_in_process:
            ok("PATH activo en esta terminal")
        elif state.path_in_registry:
            warn("PATH en registro pero no activo aquí; install_drivers → [1] Reparar")
        else:
            fail("Pothos instalado pero PATH no configurado")
            errors.append("pothos_path")
    else:
        fail("PothosSDR no encontrado. install_drivers → [1] Reparar")
        errors.append("pothos")

    step("SDRplay API v3")
    if state.sdrplay_ok:
        ok("SDRplay API detectada")
    else:
        fail("SDRplay API no detectada. install_drivers → [1] Reparar")
        errors.append("sdrplay_api")

    step("SoapySDR (Python)")
    status = None
    if state.soapy_import_ok:
        ok("SoapySDR importado correctamente")
        if state.venv_ok and venv_py:
            from core.soapy_runtime import get_pothos_site_packages_for_version

            pothos_sp = get_pothos_site_packages_for_version(v[0], v[1])
            if pothos_sp:
                ok(f"Bindings: {pothos_sp}")
            status = bootstrap_soapy(force=True) if os.path.normcase(sys.executable) == os.path.normcase(str(venv_py)) else None
            if status and status.pothos_bin:
                ok(f"DLL path: {status.pothos_bin}")
        if state.has_devices and state.device_count:
            ok(f"Dispositivos encontrados: {state.device_count}")
            if state.venv_ok and venv_py and os.path.normcase(sys.executable) != os.path.normcase(str(venv_py)):
                from setup.env_state import probe_soapy_in_python

                _, devices = probe_soapy_in_python(str(venv_py))
                for device in devices:
                    print(f"    → driver={device.get('driver', '?')} label={device.get('label', '?')}")
            elif status and status.devices:
                for device in status.devices:
                    print(f"    → driver={device.get('driver', '?')} label={device.get('label', '?')}")
        else:
            warn("Ningún dispositivo SDR detectado (¿conectado? ¿SDRuno cerrado?)")
    else:
        status = bootstrap_soapy(force=True) if state.venv_ok and os.path.normcase(sys.executable) == os.path.normcase(str(venv_py or "")) else None
        fail("SoapySDR no importa en Python.")
        if status:
            help_text = format_hardware_help(status)
            for line in help_text.splitlines():
                print(f"    {line}")
        errors.append("soapysdr")

    step("SoapySDR plugin sdrplay")
    if state.sdrplay_plugin_ok:
        ok("SoapySDRUtil --find=driver=sdrplay OK")
    else:
        from core.soapy_runtime import (
            assess_sdrplay_soapy_module,
            bootstrap_soapy,
            check_sdrplay_service_running,
            find_sdrplay_soapy_module,
        )

        plugin_status = status or bootstrap_soapy(force=True)
        module_path = plugin_status.sdrplay_plugin_module or find_sdrplay_soapy_module()
        module_state = plugin_status.sdrplay_plugin_status or assess_sdrplay_soapy_module(module_path)
        if module_state == "legacy":
            warn(
                "Módulo Soapy sdrplay de Pothos 2021 (sdrPlaySupport.dll) — incompatible con API v3.15+."
            )
            warn("Compila SoapySDRPlay3: .\\setup\\install_drivers.ps1 → [1] Reparar todo")
        elif module_path:
            warn(
                f"Módulo Soapy sdrplay en disco ({os.path.basename(module_path)}) "
                "pero no enumera dispositivo."
            )
            warn("¿RSP conectado? Cierra SDRuno y reinicia SDRplayAPIService.")
        else:
            warn("Módulo Soapy sdrplay no encontrado en PothosSDR/lib/SoapySDR/modules*.")
            warn("Compila SoapySDRPlay3: .\\setup\\install_drivers.ps1 → [1] Reparar todo")
        if plugin_status.sdrplay_api_bin and "arm64" in plugin_status.sdrplay_api_bin.lower():
            warn(f"API SDRplay en ruta arm64 ({plugin_status.sdrplay_api_bin}) — se requiere x64.")
        if state.sdrplay_ok and not check_sdrplay_service_running():
            warn("Servicio SDRplayAPIService detenido — inícialo o reinícialo.")
        warn("Comprueba USB y ejecuta: SoapySDRUtil --find=driver=sdrplay")

    step("SDRplay RX preflight")
    skip_preflight = os.environ.get("XYZ_SDR_SKIP_RX_PREFLIGHT", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if skip_preflight:
        warn("sdrplay_rx_preflight: SKIP (XYZ_SDR_SKIP_RX_PREFLIGHT)")
    elif state.sdrplay_plugin_ok and state.sdrplay_ok and state.has_devices:
        from core.sdrplay_preflight import preflight_status_label, resolve_preflight_timeout, run_preflight_best

        try:
            preflight_result = run_preflight_best(timeout=resolve_preflight_timeout())
            label = preflight_status_label(preflight_result)
            if preflight_result.ok:
                ok(
                    f"sdrplay_rx_preflight: {label} "
                    f"(path={preflight_result.path}, step={preflight_result.last_step})"
                )
            elif preflight_result.segfault:
                fail(
                    f"sdrplay_rx_preflight: {label} "
                    f"(path={preflight_result.path}, step={preflight_result.last_step})"
                )
                errors.append("sdrplay_rx_preflight")
            else:
                warn(
                    f"sdrplay_rx_preflight: {label} "
                    f"(path={preflight_result.path}, step={preflight_result.last_step})"
                )
        except Exception as exc:
            warn(f"sdrplay_rx_preflight: SKIP ({exc})")
    elif state.sdrplay_plugin_ok and state.sdrplay_ok:
        warn("sdrplay_rx_preflight: SKIP (sin dispositivo SDR enumerado)")
    else:
        warn("sdrplay_rx_preflight: SKIP (plugin o API no listos)")

    step("Librerías Python")
    if state.python_libs_ok:
        for lib in ("numpy", "scipy", "sounddevice", "textual", "rich"):
            ok(lib)
    elif state.venv_ok:
        for lib in state.python_libs_missing:
            fail(f"{lib} — no instalado en .venv")
            errors.append(lib)
    else:
        fail("Sin .venv no se pueden verificar dependencias")
        errors.append("python_libs")

    print("\n" + "=" * 50)
    if not errors:
        print("\033[92m  [OK] Todo listo. Ejecuta: .\\scripts\\run.ps1 --list-dev\033[0m")
    else:
        print(f"\033[91m  [FAIL] {len(errors)} problema(s) encontrado(s):\033[0m")
        for item in errors:
            print(f"    - {item}")
        print("\n  Ejecuta: .\\setup\\install_drivers.ps1 → [1] Instalar o reparar todo")
        print("  Si PATH falla en otra terminal, ábrela de nuevo tras reparar drivers.")
    print("=" * 50 + "\n")
    return 0 if not errors else 1


if __name__ == "__main__":
    import argparse

    _parser = argparse.ArgumentParser()
    _parser.add_argument("--verbose", action="store_true")
    _args, _ = _parser.parse_known_args()
    sys.exit(run_check(verbose=_args.verbose))
