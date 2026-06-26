"""Acciones de instalación (orquestación sin UI de menú)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable

from setup.env_state import path_contains_pothos
from setup.install_i18n import t
from setup.install_log import log_line
from setup.repo_update import run_repo_update
from setup.windows_installers import (
    POTHOS_INSTALLER_URL,
    SDRPLAY_INSTALLER_URL,
    configure_path,
    download_file,
    run_exe_installer,
)
from setup.bundled_installers import acquire_sdrplay_installer


@dataclass
class InstallContext:
    lang: str
    say: Callable[[str], None]
    confirm: Callable[[str], bool]
    temp_dir: str


def report_path_configuration(ctx: InstallContext) -> None:
    ctx.say(f"\n  → {t(ctx.lang, 'path_label')}...")
    success, info = configure_path()
    if success:
        if info:
            for entry in info:
                if str(entry).startswith("PYTHONPATH:"):
                    msg = t(ctx.lang, "path_pythonpath_success").format(entry.split(":", 1)[1])
                else:
                    msg = t(ctx.lang, "path_success").format(entry)
                ctx.say(f"  [SUCCESS] {msg}")
        else:
            ctx.say(f"  [SUCCESS] {t(ctx.lang, 'path_already')}")
        if path_contains_pothos(os.environ.get("PATH", "")):
            ctx.say(f"  {t(ctx.lang, 'path_applied_session')}")
        else:
            ctx.say(f"  {t(ctx.lang, 'path_restart_hint')}")
    else:
        ctx.say(f"  [ERROR] {t(ctx.lang, 'path_fail').format(info)}")


def report_install_error(ctx: InstallContext, exc: Exception) -> None:
    if isinstance(exc, PermissionError):
        ctx.say(f"\n[CANCELLED] {t(ctx.lang, 'install_elevation_cancelled')}")
        ctx.say(f"  {t(ctx.lang, 'install_elevation_hint')}")
        return
    ctx.say(f"\n[ERROR] {t(ctx.lang, 'install_fail')}: {exc}")
    if os.name == "nt" and getattr(exc, "winerror", None) == 740:
        ctx.say(f"  {t(ctx.lang, 'install_elevation_hint')}")


def _installer_python() -> str:
    from core.python_runtime import project_venv_python

    venv_py = project_venv_python()
    if venv_py is not None and venv_py.is_file():
        return str(venv_py)
    return sys.executable


def _run_sdrplay_api_installer_body(ctx: InstallContext) -> bool:
    """Ejecuta el instalador oficial (sin preparación de procesos)."""
    path = acquire_sdrplay_installer(ctx.temp_dir, lang=ctx.lang, on_message=ctx.say)
    if not path:
        ctx.say(f"\n[ERROR] {t(ctx.lang, 'install_fail')}")
        ctx.say(f"\n  Manual: {SDRPLAY_INSTALLER_URL}")
        return False

    ctx.say(f"  {t(ctx.lang, 'running_installer')}")
    ctx.say("  [>>] Acepta UAC si aparece; completa el asistente SDRplay API.")
    try:
        run_exe_installer(path)
        from core.soapy_runtime import check_sdrplay_api

        if not check_sdrplay_api():
            ctx.say("  [!!] Instalador ejecutado pero la API SDRplay no se detecta en disco.")
            ctx.say("  [>>] Completa el asistente o reinstala desde sdrplay.com/downloads")
            return False
        ctx.say(f"\n[SUCCESS] {t(ctx.lang, 'install_success')}")
        return True
    except Exception as exc:
        report_install_error(ctx, exc)
        return False


def run_sdrplay_api_installer(ctx: InstallContext, *, isolated: bool = False) -> bool:
    """Obtiene e instala SDRplay API v3.15 (bundled → local → URL)."""
    from core.runtime_paths import project_root
    from core.sdrplay_install_guard import (
        finalize_after_sdrplay_api_install,
        prepare_for_sdrplay_api_install,
    )

    if isolated:
        return _run_sdrplay_api_installer_body(ctx)

    ok_prep, prep_msg = prepare_for_sdrplay_api_install(ctx.say, lang=ctx.lang)
    if not ok_prep:
        ctx.say(f"  [!!] {prep_msg}")
        return False

    root = project_root()
    py = _installer_python()
    log_line(f"SDRplay API isolated install via {py}")
    proc = subprocess.run(
        [py, "-m", "setup.install_sdrplay_api", "--isolated"],
        cwd=str(root),
        env=os.environ.copy(),
        check=False,
    )
    if proc.returncode != 0:
        ctx.say(f"  [!!] {t(ctx.lang, 'sdrplay_guard_install_failed')}")
        return False

    ok_final, final_msg = finalize_after_sdrplay_api_install(ctx.say, lang=ctx.lang)
    if not ok_final:
        ctx.say(f"  [>>] {final_msg}")
    time.sleep(1.0)
    return True


def install_sdrplay(ctx: InstallContext) -> bool:
    return run_sdrplay_api_installer(ctx)


def install_pothos(ctx: InstallContext) -> None:
    path = os.path.join(ctx.temp_dir, "PothosSDR_installer.exe")
    if download_file(POTHOS_INSTALLER_URL, path, "PothosSDR", lang=ctx.lang, on_message=ctx.say):
        ctx.say(f"  {t(ctx.lang, 'running_installer')}")
        try:
            run_exe_installer(path)
            ctx.say(f"\n[SUCCESS] {t(ctx.lang, 'install_success')}")
            report_path_configuration(ctx)
        except Exception as exc:
            report_install_error(ctx, exc)
    else:
        ctx.say(f"\n[ERROR] {t(ctx.lang, 'install_fail')}")
        ctx.say(f"\n  Manual: {POTHOS_INSTALLER_URL}")
    path = os.path.join(ctx.temp_dir, "PothosSDR_installer.exe")
    if download_file(POTHOS_INSTALLER_URL, path, "PothosSDR", lang=ctx.lang, on_message=ctx.say):
        ctx.say(f"  {t(ctx.lang, 'running_installer')}")
        try:
            run_exe_installer(path)
            ctx.say(f"\n[SUCCESS] {t(ctx.lang, 'install_success')}")
            report_path_configuration(ctx)
        except Exception as exc:
            report_install_error(ctx, exc)
    else:
        ctx.say(f"\n[ERROR] {t(ctx.lang, 'install_fail')}")
        ctx.say(f"\n  Manual: {POTHOS_INSTALLER_URL}")


def _ensure_uv(ctx: InstallContext) -> None:
    from core.uv_runtime import ensure_uv, uv_available

    ctx.say(f"  {t(ctx.lang, 'py_checking_uv')}")
    if not uv_available(sys.executable):
        ctx.say(f"  {t(ctx.lang, 'py_installing_uv')}")
    uv_cmd = ensure_uv(sys.executable)
    ctx.say(f"  [OK] {t(ctx.lang, 'py_uv_ready').format(' '.join(uv_cmd))}")


def resolve_soapy_python(ctx: InstallContext, *, offer_install: bool):
    from core.python_runtime import (
        find_best_soapy_python,
        provision_compatible_python_verbose,
        provision_fail_i18n_key,
        provision_manual_i18n_key,
        provision_prompt_i18n_key,
        provision_running_i18n_key,
    )

    best = find_best_soapy_python()
    if best or not offer_install:
        return best
    if not ctx.confirm(t(ctx.lang, provision_prompt_i18n_key())):
        return None

    ctx.say(f"  {t(ctx.lang, provision_running_i18n_key())}")

    def _log(message: str) -> None:
        ctx.say(f"  {message}")

    result = provision_compatible_python_verbose(log=_log, temp_dir=ctx.temp_dir)
    if result.candidate:
        ctx.say(f"  [OK] {result.candidate.label()}")
        return result.candidate

    ctx.say(f"  [ERROR] {t(ctx.lang, provision_fail_i18n_key())}")
    if result.detail:
        ctx.say(f"  {result.detail[:220]}")
    ctx.say(f"  {t(ctx.lang, provision_manual_i18n_key())}")
    return None


def install_python_env(ctx: InstallContext, *, offer_python_install: bool = True) -> bool:
    from core.python_runtime import ensure_project_venv_with_deps, find_best_soapy_python, project_venv_python

    try:
        _ensure_uv(ctx)
    except Exception as exc:
        ctx.say(f"  [!!] {t(ctx.lang, 'py_uv_fail').format(exc)}")
        return False

    ctx.say(f"  {t(ctx.lang, 'py_venv_auto')}")
    venv_py = project_venv_python()
    best = find_best_soapy_python()
    if not best and not venv_py:
        best = resolve_soapy_python(ctx, offer_install=offer_python_install)
        if not best and not project_venv_python():
            return False

    try:
        label = best.label() if best else ".venv"
        ctx.say(f"  {t(ctx.lang, 'py_venv_creating').format(label)}")
        py = ensure_project_venv_with_deps()
        ctx.say(f"  [SUCCESS] {t(ctx.lang, 'py_venv_ready').format(py)}")
        ctx.say(f"\n[SUCCESS] {t(ctx.lang, 'py_success')}")
        ctx.say(f"  {t(ctx.lang, 'py_venv_hint')}")
        return True
    except Exception as exc:
        ctx.say(f"\n[ERROR] {t(ctx.lang, 'py_fail')}: {exc}")
        return False


def install_soapy_sdrplay3(ctx: InstallContext, *, force: bool = False) -> bool:
    from setup.soapy_sdrplay3 import install_soapy_sdrplay3_if_needed

    return install_soapy_sdrplay3_if_needed(
        ctx.temp_dir,
        say=ctx.say,
        confirm=ctx.confirm,
        force=force,
    )


def run_diagnostics(ctx: InstallContext, *, verbose: bool = True) -> int:
    if verbose:
        ctx.say(f"  {t(ctx.lang, 'diag_running')}")
    from setup.check_env import run_check
    return run_check(verbose=verbose, lang=ctx.lang)


def repair_all(ctx: InstallContext, *, quiet: bool = False) -> int:
    from setup.install_wizard import run_repair_wizard
    return run_repair_wizard(ctx, quiet=quiet)


def run_full_setup(ctx: InstallContext) -> int:
    """Alias de repair_all (compatibilidad)."""
    return repair_all(ctx)


def run_repo_update_action(ctx: InstallContext) -> None:
    result = run_repo_update(ctx.lang, ctx.say, interactive=True)
    if result.updated and result.needs_installer_restart:
        from setup.repo_update import restart_installer

        restart_installer()