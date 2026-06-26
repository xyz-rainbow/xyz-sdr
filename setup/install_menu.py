"""UI del instalador Express + Avanzado."""

from __future__ import annotations

import os
import sys
import time
from typing import Callable

from setup.env_state import EnvironmentState, probe_environment
from setup.install_actions import (
    InstallContext,
    install_pothos,
    install_python_env,
    install_sdrplay,
    install_soapy_sdrplay3,
    run_repo_update_action,
)
from setup.install_guidance import format_action, drivers_row_status, hardware_row_status, python_row_status
from setup.install_i18n import t
from setup.install_log import current_log_path
from setup.install_wizard import offer_post_install_run, run_repair_wizard
from setup.windows_installers import refresh_windows_environment

C_LIME = "\033[38;5;118m"
C_PINK = "\033[38;5;207m"
C_CYAN = "\033[38;5;81m"
C_ORANGE = "\033[38;5;202m"
C_RED = "\033[38;5;196m"
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_GRAY = "\033[90m"
C_PURPLE = "\033[38;5;141m"

MENU_EXIT = "0"
MENU_REPAIR = "1"
MENU_RUN = "2"
MENU_DIAG = "3"
MENU_ADVANCED = "A"


def print_banner() -> None:
    os.system("cls" if os.name == "nt" else "clear")
    print(f"{C_RED}  ██████╗  ██╗  ██╗ ██╗   ██╗ ███████╗            ███████╗ ██████╗  ██████╗  ██████╗ {C_RESET}")
    print(f"{C_ORANGE}  ██╔═══╝  ╚██╗██╔╝ ╚██╗ ██╔╝ ╚══███╔╝ █████████╗ ██╔════╝ ██╔══██╗ ██╔══██╗ ╚═══██║ {C_RESET}")
    print(f"{C_LIME}  ██║       ╚███╔╝   ╚████╔╝     ███╔╝ ╚════════╝ ███████╗ ██║  ██║ ██████╔╝     ██║ {C_RESET}")
    print(f"{C_CYAN}  ██║       ██╔██╗    ╚██╔╝     ███╔╝  █████████╗ ╚════██║ ██║  ██║ ██╔══██╗     ██║ {C_RESET}")
    print(f"{C_PURPLE}  ██████╗  ██╔╝ ██╗    ██║     ███████╗            ███████║ ██████╔╝ ██║  ██║ ██████║ {C_RESET}")
    print(f"{C_PINK}  ╚═════╝  ╚═╝  ╚═╝    ╚═╝     ╚══════╝            ╚══════╝ ╚═════╝  ╚═╝  ╚═╝ ╚═════╝ {C_RESET}")
    print(f"{C_CYAN} ─────────────────────────────────────────────────────────────────────────────────────────{C_RESET}")


def _menu_line(number: str, label: str, *, highlight: bool = False, suffix: str = "") -> None:
    mark = f"{C_LIME}►{C_RESET} " if highlight else "  "
    extra = f" {suffix}" if suffix else ""
    print(f"{mark} {C_PINK}[{number}]{C_RESET} {label}{extra}")


def _status_icon(ok: bool | None) -> str:
    if ok is True:
        return f"{C_LIME}✓{C_RESET}"
    if ok is False:
        return f"{C_RED}✗{C_RESET}"
    return f"{C_ORANGE}⚠{C_RESET}"


def print_express_interface(
    lang: str,
    *,
    prefetched_state: EnvironmentState | None = None,
    skip_banner: bool = False,
) -> EnvironmentState:
    if not skip_banner:
        print_banner()
    refresh_windows_environment()
    if prefetched_state is not None:
        state = prefetched_state
    else:
        state = probe_environment(bootstrap_soapy=True, quiet_soapy=True, inprocess_soapy=False)
    action, _, reason = format_action(state, lang)

    level = state.readiness_level()
    if level == "hardware":
        headline = t(lang, "readiness_hardware")
        color = C_LIME
    elif level == "env":
        if state.sdrplay_ok and not state.has_sdrplay_devices:
            headline = t(lang, "readiness_env_no_rsp")
            color = C_ORANGE
        else:
            headline = t(lang, "readiness_env")
            color = C_LIME
    else:
        headline = t(lang, "readiness_pending")
        color = C_ORANGE

    print(f" {C_BOLD}{t(lang, 'status_summary')}:{C_RESET} {color}{headline}{C_RESET}")
    print(f"  {_status_icon(state.drivers_ready)} {t(lang, 'status_row_drivers')}: {drivers_row_status(state, lang)}")
    print(f"  {_status_icon(state.python_env_ready)} {t(lang, 'status_row_python')}: {python_row_status(state, lang)}")
    print(f"  {_status_icon(state.has_target_hardware if state.env_ready else None)} {t(lang, 'status_row_hardware')}: {hardware_row_status(state, lang)}")
    if state.env_ready and state.sdrplay_ok and not state.has_sdrplay_devices:
        if state.sdrplay_usb_issue:
            print(f"  {C_ORANGE}→ {t(lang, 'status_hint_usb_repair')}{C_RESET}")
        elif "sdrplay_enumeration" in state.blockers:
            print(f"  {C_ORANGE}→ {t(lang, 'status_hint_rsp_repair')}{C_RESET}")
    print(f"\n {C_BOLD}{t(lang, 'next_step_label')}:{C_RESET} {reason}")
    print(f"{C_CYAN} ─────────────────────────────────────────────────────────────────────────────────────────{C_RESET}")
    print(f" {C_BOLD}{t(lang, 'menu_express_title')}:{C_RESET}")

    can_run = state.env_ready
    rec = action.menu_highlight
    _menu_line(MENU_REPAIR, t(lang, "menu_repair_all"), highlight=rec == MENU_REPAIR)
    _menu_line(
        MENU_RUN,
        t(lang, "menu_run_app"),
        highlight=rec == MENU_RUN,
        suffix=f"{C_GRAY}({t(lang, 'menu_run_disabled')}){C_RESET}" if not can_run else "",
    )
    _menu_line(MENU_DIAG, t(lang, "menu_diag_short"), highlight=rec == MENU_DIAG)
    _menu_line(MENU_ADVANCED, t(lang, "menu_advanced"))
    _menu_line(MENU_EXIT, t(lang, "menu_opt_exit"))
    print(f"{C_CYAN} ─────────────────────────────────────────────────────────────────────────────────────────{C_RESET}")
    return state


def _pause(lang: str) -> None:
    input(f"\n{t(lang, 'press_enter_menu')}")


def _invalid(lang: str) -> None:
    print(f"\n{C_RED}[ERROR] {t(lang, 'invalid_option')}{C_RESET}")
    time.sleep(0.6)


def _run_advanced_menu(
    lang: str,
    ctx: InstallContext,
    *,
    set_lang: Callable[[str], None],
    temp_dir: str,
) -> None:
    from setup.install_actions import report_path_configuration

    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print(f"\n{C_CYAN}─── {t(lang, 'menu_advanced_title').upper()} ───{C_RESET}\n")
        _menu_line("1", t(lang, "menu_opt_sdrplay"))
        _menu_line("2", t(lang, "menu_opt_pothos"))
        _menu_line("3", t(lang, "menu_opt_py"))
        _menu_line("4", t(lang, "menu_opt_soapy_sdrplay3"))
        _menu_line("5", t(lang, "menu_diag_full"))
        _menu_line("6", t(lang, "menu_opt_update"))
        _menu_line("7", t(lang, "menu_opt_lang"))
        _menu_line("0", t(lang, "menu_advanced_back"))
        opc = input(f"\n {C_BOLD}{t(lang, 'select_option')}{C_RESET}").strip()
        state = probe_environment(bootstrap_soapy=False)

        if opc == MENU_EXIT:
            return
        if opc == "1":
            if state.sdrplay_ok:
                print(f"\n{C_LIME}[OK] {t(lang, 'already_installed_skip')}{C_RESET}")
            else:
                install_sdrplay(ctx)
            _pause(lang)
        elif opc == "2":
            if state.pothos_installed:
                print(f"\n{C_LIME}[OK] {t(lang, 'already_installed_skip')}{C_RESET}")
                if not state.path_in_process:
                    report_path_configuration(ctx)
            else:
                install_pothos(ctx)
            _pause(lang)
        elif opc == "3":
            if state.python_env_ready:
                print(f"\n{C_LIME}[OK] {t(lang, 'already_installed_skip')}{C_RESET}")
            else:
                install_python_env(ctx)
            _pause(lang)
        elif opc == "4":
            install_soapy_sdrplay3(ctx, force=True)
            _pause(lang)
        elif opc == "5":
            from setup.check_env import run_check
            run_check(verbose=True, lang=lang)
            _pause(lang)
        elif opc == "6":
            run_repo_update_action(ctx)
            _pause(lang)
        elif opc == "7":
            set_lang("en" if lang == "es" else "es")
            lang = "en" if lang == "es" else "es"
            ctx = InstallContext(lang=lang, say=ctx.say, confirm=ctx.confirm, temp_dir=temp_dir)
        else:
            _invalid(lang)


def run_express_menu(
    lang: str,
    ctx: InstallContext,
    *,
    set_lang: Callable[[str], None],
    temp_dir: str,
    exit_fn: Callable[[], None],
    initial_state: EnvironmentState | None = None,
) -> None:
    first_menu = initial_state is not None
    while True:
        prefetched = initial_state if first_menu else None
        print_express_interface(
            lang,
            prefetched_state=prefetched,
            skip_banner=first_menu,
        )
        first_menu = False
        initial_state = None
        opc = input(f" {C_BOLD}{t(lang, 'select_option')}{C_RESET}").strip().upper()
        if opc == MENU_EXIT:
            exit_fn()

        state = probe_environment(bootstrap_soapy=True, quiet_soapy=True, inprocess_soapy=False)

        if opc == MENU_REPAIR:
            code = run_repair_wizard(ctx)
            if code == 0:
                offer_post_install_run(ctx)
            log_path = current_log_path()
            if log_path:
                print(f"\n  {t(lang, 'wizard_log').format(log_path)}")
            _pause(lang)
        elif opc == MENU_RUN:
            if not state.env_ready:
                print(f"\n{C_ORANGE}{t(lang, 'menu_run_need_repair')}{C_RESET}")
                _pause(lang)
                continue
            from setup.install_wizard import launch_app
            launch_app(ctx, sim=not state.has_target_hardware)
            _pause(lang)
        elif opc == MENU_DIAG:
            from setup.check_env import run_check
            run_check(verbose=False, lang=lang)
            _pause(lang)
        elif opc == MENU_ADVANCED:
            _run_advanced_menu(lang, ctx, set_lang=set_lang, temp_dir=temp_dir)
        else:
            _invalid(lang)


def run_resumed_repair(lang: str, ctx: InstallContext) -> None:
    print_banner()
    print(f"  {t(lang, 'update_resumed_wizard')}")
    code = run_repair_wizard(ctx)
    if code == 0:
        offer_post_install_run(ctx)
    log_path = current_log_path()
    if log_path:
        print(f"\n  {t(lang, 'wizard_log').format(log_path)}")
    os.environ.pop("XYZ_SDR_INSTALL_SKIP_UPDATE", None)
    _pause(lang)
