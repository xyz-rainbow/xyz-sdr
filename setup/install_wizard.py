"""Wizard de reparación/instalación completa (4 pasos)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from setup.env_state import probe_environment
from setup.install_actions import (
    InstallContext,
    install_pothos,
    install_python_env,
    install_sdrplay,
    report_path_configuration,
)
from setup.install_i18n import t
from setup.install_log import current_log_path, log_line
from setup.repo_update import ensure_repo_updated_for_wizard
from setup.windows_installers import refresh_windows_environment

WIZARD_STEPS = (
    ("wizard_step_update", "update"),
    ("wizard_step_drivers", "drivers"),
    ("wizard_step_python", "python"),
    ("wizard_step_verify", "verify"),
)


def run_repair_wizard(ctx: InstallContext, *, quiet: bool = False) -> int:
    """Flujo lineal: git → drivers → python → verify."""
    refresh_windows_environment()
    total = len(WIZARD_STEPS)
    ctx.say(f"\n=== {t(ctx.lang, 'wizard_title')} ===")
    log_line("Repair wizard started")

    for index, (title_key, key) in enumerate(WIZARD_STEPS, start=1):
        title = t(ctx.lang, title_key)
        ctx.say(f"\n--- {t(ctx.lang, 'wizard_progress').format(index, total, title)} ---")
        log_line(f"Wizard step {index}/{total}: {key}")

        if key == "update":
            ensure_repo_updated_for_wizard(ctx.lang, ctx.say)
            continue

        state = probe_environment(bootstrap_soapy=False)

        if key == "drivers":
            if not state.sdrplay_ok:
                install_sdrplay(ctx)
            else:
                log_line("SKIP sdrplay")
            state = probe_environment(bootstrap_soapy=False)
            if not state.pothos_installed:
                install_pothos(ctx)
            elif not state.path_in_process:
                report_path_configuration(ctx)
            else:
                log_line("SKIP pothos")
            continue

        if key == "python":
            state = probe_environment(bootstrap_soapy=False)
            if state.python_env_ready:
                log_line("SKIP python env")
            elif not install_python_env(ctx, offer_python_install=not quiet):
                ctx.say(f"  [ERROR] {t(ctx.lang, 'wizard_python_failed')}")
                return 1
            continue

        if key == "verify":
            from setup.check_env import run_check

            code = run_check(verbose=False, lang=ctx.lang)
            ctx.say(f"\n=== {t(ctx.lang, 'wizard_done')} ===")
            log_path = current_log_path()
            if log_path:
                ctx.say(f"  {t(ctx.lang, 'wizard_log').format(log_path)}")
            return code

    return 1


def offer_post_install_run(ctx: InstallContext) -> bool:
    state = probe_environment(bootstrap_soapy=True)
    if not state.env_ready:
        return False
    choice = input(f"\n  {t(ctx.lang, 'post_install_prompt')}").strip().lower()
    if choice in ("m", "menu"):
        return False
    return launch_app(ctx, sim=not state.has_devices)


def launch_app(ctx: InstallContext, *, sim: bool = False) -> bool:
    root = Path(__file__).resolve().parent.parent
    venv_py = root / ".venv" / "Scripts" / "python.exe"
    if not venv_py.is_file():
        venv_py = root / ".venv" / "bin" / "python"
    if not venv_py.is_file():
        ctx.say(f"  [ERROR] {t(ctx.lang, 'post_install_no_venv')}")
        return False

    state = probe_environment(bootstrap_soapy=True)
    use_sim = sim or (state.env_ready and not state.has_devices)
    cmd = [str(venv_py), str(root / "main.py")]
    if use_sim:
        cmd.append("--sim")
        ctx.say(f"  {t(ctx.lang, 'post_install_sim')}")

    ctx.say(f"  {t(ctx.lang, 'post_install_launch')}")
    log_line(f"Launch: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(root))
    return proc.returncode == 0
