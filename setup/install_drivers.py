"""
xyz-sdr | setup/install_drivers.py
Entrypoint del instalador — menú Express, CLI headless.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Callable

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, "..")) if script_dir else os.getcwd()
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if script_dir:
    os.chdir(project_root)

from pathlib import Path

from core.console_utf8 import configure_console_encoding, register_windows_console_restore, restore_terminal_after_tui
from core.runtime_paths import configure_pycache_prefix

configure_pycache_prefix(Path(project_root))
configure_console_encoding()
register_windows_console_restore()

if os.name == "nt":
    os.system("")
    os.environ.setdefault("UHD_LOG_LEVEL", "off")

from setup.env_state import probe_environment
from setup.install_i18n import detect_system_language, t
from setup.install_log import get_install_logger, log_line
from setup.install_menu import run_express_menu, run_resumed_repair
from setup.install_actions import InstallContext
from setup.install_wizard import run_repair_wizard
from setup.windows_installers import refresh_windows_environment

C_PINK = "\033[38;5;207m"
C_RESET = "\033[0m"

CURRENT_LANG = detect_system_language()


def _lang() -> str:
    return CURRENT_LANG


def _set_lang(lang: str) -> None:
    global CURRENT_LANG
    CURRENT_LANG = lang


def _say(message: str) -> None:
    print(message)
    log_line(message)


def _confirm(prompt: str) -> bool:
    answer = input(prompt).strip().lower()
    return answer in ("s", "si", "y", "yes")


def _ctx(temp_dir: str) -> InstallContext:
    return InstallContext(lang=_lang(), say=_say, confirm=_confirm, temp_dir=temp_dir)


def _make_exit_installer(*, use_splash: bool) -> Callable[[], None]:
    def _exit_installer() -> None:
        if use_splash:
            from setup.install_splash import run_installer_closing_splash

            run_installer_closing_splash()
        else:
            print(
                f"\n{C_PINK}Saliendo de la instalación. ¡Buen código! / "
                f"Exiting installer. Happy coding!{C_RESET}\n"
            )
        restore_terminal_after_tui()
        sys.exit(0)

    return _exit_installer


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="xyz-sdr installer")
    parser.add_argument("--menu", action="store_true", help="Interactive menu (default)")
    parser.add_argument("--repair", action="store_true", help="Run repair wizard headless")
    parser.add_argument("--check", action="store_true", help="Run environment check")
    parser.add_argument("--quiet", action="store_true", help="No prompts (with --repair)")
    parser.add_argument("--verbose", action="store_true", help="Full diagnostics (with --check)")
    parser.add_argument("--require-hardware", action="store_true", help="Exit 2 if no SDR device")
    parser.add_argument("--no-splash", action="store_true", help="Skip installer splash/outro animations")
    return parser


def _exit_code_for_state(*, require_hardware: bool = False) -> int:
    refresh_windows_environment()
    state = probe_environment(bootstrap_soapy=True, quiet_soapy=True, inprocess_soapy=False)
    if state.env_ready:
        if require_hardware and not state.has_target_hardware:
            return 2
        return 0
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    get_install_logger()
    refresh_windows_environment()
    temp_dir = os.environ.get("TEMP", os.environ.get("TMP", "/tmp"))
    use_splash = not args.no_splash

    if args.check:
        from setup.check_env import run_check
        return run_check(verbose=args.verbose, lang=_lang())

    if args.repair:
        ctx = _ctx(temp_dir)
        if args.quiet:
            ctx = InstallContext(
                lang=ctx.lang,
                say=ctx.say,
                confirm=lambda _p: True,
                temp_dir=ctx.temp_dir,
            )
        code = run_repair_wizard(ctx, quiet=args.quiet)
        if code != 0:
            return code
        return _exit_code_for_state(require_hardware=args.require_hardware)

    resume = os.environ.pop("XYZ_SDR_INSTALL_RESUME", None)
    if resume in ("repair", "wizard"):
        run_resumed_repair(_lang(), _ctx(temp_dir))
        return 0

    initial_state = None
    if use_splash:
        from setup.install_splash import run_installer_opening_splash

        initial_state = run_installer_opening_splash(_lang())

    run_express_menu(
        _lang(),
        _ctx(temp_dir),
        set_lang=_set_lang,
        temp_dir=temp_dir,
        exit_fn=_make_exit_installer(use_splash=use_splash),
        initial_state=initial_state,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        if "--no-splash" not in sys.argv:
            try:
                from setup.install_splash import run_installer_closing_splash

                run_installer_closing_splash()
            except Exception:
                print(
                    f"\n\n{C_PINK}Saliendo de la instalación. ¡Buen código! / "
                    f"Exiting installer. Happy coding!{C_RESET}\n"
                )
        else:
            print(
                f"\n\n{C_PINK}Saliendo de la instalación. ¡Buen código! / "
                f"Exiting installer. Happy coding!{C_RESET}\n"
            )
        restore_terminal_after_tui()
        sys.exit(130)
